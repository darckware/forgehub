"""Read access to ForgeRouter's own agent registry.

ForgeRouter (the ecosystem's exclusive LLM gateway) issues and tracks one
API key per connected agent in its own database -- `forgerouter_postgres`
(port 5432) -> database `forgerouter` -> schema `ai_router`, table
`agents` (see /root/.hermes/foundation/36_governance/POSTGRESQL_TOPOLOGY.md
and FORGEROUTER_DOCUMENTATION.md §ai_router.agents). That key is already
written into each agent's own runtime config (`config_path`/`config_key`
columns record where -- a Hermes profile's config.yaml for the
Hermes-profile agents, `.env` files for the external runtimes), which is
exactly what backs Agent's `forgerouter_api_key_encrypted` column. This
module is the read side of POST /api/v1/agents/sync/forgerouter-keys
(app/api/routes/agent.py): pull straight from ai_router.agents instead of
re-deriving per-runtime file-parsing logic for every runtime (unlike
hermes_sync.read_profile_forgerouter_api_key, which only covers
Hermes-profile agents by reading their config.yaml directly).

Read-only, same trust boundary as api/routes/database.py's existing
dedicated `forgerouter_postgres`/`forgerouter` connection (settings.db_url_for)
-- this module just narrows that to one query.
"""
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings


@dataclass(frozen=True)
class ForgeRouterAgentKey:
    name: str
    api_key: str


@dataclass(frozen=True)
class ForgeRouterActivityEvent:
    """One row of `ai_router.route_events` -- a single LLM completion call
    ForgeRouter routed for an agent, not a tool-call-level log (ForgeRouter
    doesn't record which individual tool -- web search, bash, etc. -- a
    call used, only the routing `required_capability` tier it needed:
    text/code/tool_call/vision). Still real, per-request telemetry (unlike
    ForgeHub's own dispatch_status, which only changes at message
    granularity), so it's the only honest source for "is this agent
    actively calling an LLM right now" between dispatch and completion."""

    request_id: str
    agent_name: str | None
    required_capability: str
    demand: str | None
    status: str
    created_at: datetime
    prompt_preview: str | None
    cost: float | None


async def _read_ai_router_agents(kind: str) -> list[ForgeRouterAgentKey]:
    url = settings.db_url_for(
        settings.FORGEROUTER_POSTGRES_HOST, settings.FORGEROUTER_POSTGRES_PORT, "forgerouter",
        user=settings.FORGEROUTER_POSTGRES_USER,
        password=settings.FORGEROUTER_POSTGRES_PASSWORD or settings.POSTGRES_PASSWORD,
    )
    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        """
                        SELECT name, api_key FROM ai_router.agents
                        WHERE kind = :kind AND enabled IS TRUE AND api_key IS NOT NULL AND api_key != ''
                        ORDER BY name
                        """
                    ),
                    {"kind": kind},
                )
            ).fetchall()
            return [ForgeRouterAgentKey(name=r[0], api_key=r[1]) for r in rows]
    finally:
        await engine.dispose()


async def read_forgerouter_agent_keys() -> list[ForgeRouterAgentKey]:
    """Every enabled, agent-kind row in ai_router.agents with a non-empty
    key. Excludes kind='service' rows (e.g. Hindsight) -- those aren't
    agents ForgeHub's own registry ever models a ForgeRouter key for (see
    read_forgerouter_service_keys below for that set instead)."""
    return await _read_ai_router_agents("agent")


async def read_forgerouter_service_keys() -> list[ForgeRouterAgentKey]:
    """Every enabled, service-kind row in ai_router.agents (e.g.
    "Hindsight", and whatever else gets registered there directly) with a
    non-empty key. Backs Settings' "Default agent for project API keys"
    picker (ProjectsForgeRouterCard's per-project prompt on the Dashboard)
    -- 2026-07-29, Marcelo: "eu adicionei agente do tipo serviço no
    forgerouter, filtra somente esses". Deliberately the mirror-image
    filter of read_forgerouter_agent_keys above (kind='service', not
    'agent'): a service has no corresponding ForgeHub Agent row to import
    a key into, so it's looked up by name straight against this table
    instead of through Agent.forgerouter_api_key_encrypted."""
    return await _read_ai_router_agents("service")


async def read_recent_forgerouter_activity(since_seconds: int = 120, limit: int = 200) -> list[ForgeRouterActivityEvent]:
    """Route events from the last `since_seconds` -- backs the Agent
    Activity board's live "agent is actively calling an LLM" pulse (2026-08-
    17, Marcelo: "eu tenho no forgerouter" -- pointing out that per-request
    telemetry already exists there, after ForgeHub's own dispatch_status was
    shown to only ever answer "dispatched/running/completed/failed" with no
    finer signal). Joined to `ai_router.agents` for a display name; a null
    `agent_name` means the request wasn't attributed to a registered agent
    (a raw/anonymous call) and the caller should treat it as unmapped rather
    than guessing."""
    url = settings.db_url_for(
        settings.FORGEROUTER_POSTGRES_HOST, settings.FORGEROUTER_POSTGRES_PORT, "forgerouter",
        user=settings.FORGEROUTER_POSTGRES_USER,
        password=settings.FORGEROUTER_POSTGRES_PASSWORD or settings.POSTGRES_PASSWORD,
    )
    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        """
                        SELECT re.request_id, a.name, re.required_capability, re.demand,
                               re.status, re.created_at, re.prompt_preview, re.cost
                        FROM ai_router.route_events re
                        LEFT JOIN ai_router.agents a ON a.agent_id = re.agent_id
                        WHERE re.created_at > now() - make_interval(secs => :since_seconds)
                        ORDER BY re.created_at DESC
                        LIMIT :limit
                        """
                    ),
                    {"since_seconds": since_seconds, "limit": limit},
                )
            ).fetchall()
            return [
                ForgeRouterActivityEvent(
                    request_id=str(r[0]),
                    agent_name=r[1],
                    required_capability=r[2],
                    demand=r[3],
                    status=r[4],
                    created_at=r[5],
                    prompt_preview=r[6],
                    cost=float(r[7]) if r[7] is not None else None,
                )
                for r in rows
            ]
    finally:
        await engine.dispose()


@dataclass(frozen=True)
class ForgeRouterUsage:
    """LLM usage per agent: last hour's tokens/calls and today's cost (America/Sao_Paulo day)."""

    agent_name: str | None
    calls_last_hour: int
    tokens_last_hour: int
    cost_today: float


async def read_forgerouter_usage() -> list[ForgeRouterUsage]:
    """One row per agent (plus a null-name row for unattributed calls) -- backs the Agent
    Activity pulse (2026-09-28). Aggregated in SQL so the live stream never pulls rows."""
    url = settings.db_url_for(
        settings.FORGEROUTER_POSTGRES_HOST, settings.FORGEROUTER_POSTGRES_PORT, "forgerouter",
        user=settings.FORGEROUTER_POSTGRES_USER,
        password=settings.FORGEROUTER_POSTGRES_PASSWORD or settings.POSTGRES_PASSWORD,
    )
    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        """
                        SELECT a.name,
                               count(*) FILTER (WHERE re.created_at > now() - interval '1 hour'),
                               coalesce(sum(re.total_tokens) FILTER (
                                   WHERE re.created_at > now() - interval '1 hour'), 0),
                               coalesce(sum(re.cost) FILTER (WHERE re.created_at >= t.day_start), 0)
                        FROM ai_router.route_events re
                        LEFT JOIN ai_router.agents a ON a.agent_id = re.agent_id
                        CROSS JOIN (SELECT date_trunc('day', now() AT TIME ZONE 'America/Sao_Paulo')
                                           AT TIME ZONE 'America/Sao_Paulo' AS day_start) t
                        WHERE re.created_at >= least(t.day_start, now() - interval '1 hour')
                        GROUP BY a.name
                        """
                    )
                )
            ).fetchall()
            return [
                ForgeRouterUsage(
                    agent_name=r[0], calls_last_hour=int(r[1] or 0),
                    tokens_last_hour=int(r[2] or 0), cost_today=float(r[3] or 0),
                )
                for r in rows
            ]
    finally:
        await engine.dispose()


@dataclass(frozen=True)
class ForgeRouterHealth:
    """Per agent: recent provider errors and today's usage against its own recent days.

    ``*_prev_avg`` is the mean over the 7 days before today (America/Sao_Paulo), counting
    days with no calls as zero -- an agent that barely ran last week has a low baseline.
    """

    agent_name: str | None
    errors_recent: int
    last_error_type: str | None
    last_error_at: datetime | None
    tokens_today: int
    tokens_prev_avg: float
    cost_today: float
    cost_prev_avg: float


async def read_forgerouter_health(error_window_minutes: int = 15) -> list[ForgeRouterHealth]:
    """Backs the Agent Activity alerts (phase 5): provider errors and usage out of pattern.
    Aggregated in SQL; one short read."""
    url = settings.db_url_for(
        settings.FORGEROUTER_POSTGRES_HOST, settings.FORGEROUTER_POSTGRES_PORT, "forgerouter",
        user=settings.FORGEROUTER_POSTGRES_USER,
        password=settings.FORGEROUTER_POSTGRES_PASSWORD or settings.POSTGRES_PASSWORD,
    )
    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        """
                        WITH t AS (
                            SELECT date_trunc('day', now() AT TIME ZONE 'America/Sao_Paulo')
                                   AT TIME ZONE 'America/Sao_Paulo' AS day_start
                        ),
                        recent_errors AS (
                            SELECT re.agent_id, re.error_type, re.status, re.created_at
                            FROM ai_router.route_events re
                            WHERE re.status <> 'success'
                              AND re.created_at > now() - make_interval(mins => :error_window)
                        )
                        SELECT a.name,
                               (SELECT count(*) FROM recent_errors e WHERE e.agent_id IS NOT DISTINCT FROM re_agg.agent_id),
                               (SELECT coalesce(e.error_type, e.status) FROM recent_errors e
                                 WHERE e.agent_id IS NOT DISTINCT FROM re_agg.agent_id
                                 ORDER BY e.created_at DESC LIMIT 1),
                               (SELECT max(e.created_at) FROM recent_errors e
                                 WHERE e.agent_id IS NOT DISTINCT FROM re_agg.agent_id),
                               re_agg.tokens_today, re_agg.tokens_prev / 7.0,
                               re_agg.cost_today, re_agg.cost_prev / 7.0
                        FROM (
                            SELECT re.agent_id,
                                   coalesce(sum(re.total_tokens) FILTER (WHERE re.created_at >= t.day_start), 0) AS tokens_today,
                                   coalesce(sum(re.total_tokens) FILTER (WHERE re.created_at < t.day_start), 0) AS tokens_prev,
                                   coalesce(sum(re.cost) FILTER (WHERE re.created_at >= t.day_start), 0) AS cost_today,
                                   coalesce(sum(re.cost) FILTER (WHERE re.created_at < t.day_start), 0) AS cost_prev
                            FROM ai_router.route_events re CROSS JOIN t
                            WHERE re.created_at >= t.day_start - interval '7 days'
                            GROUP BY re.agent_id
                        ) re_agg
                        LEFT JOIN ai_router.agents a ON a.agent_id = re_agg.agent_id
                        """
                    ),
                    {"error_window": error_window_minutes},
                )
            ).fetchall()
            return [
                ForgeRouterHealth(
                    agent_name=r[0], errors_recent=int(r[1] or 0), last_error_type=r[2],
                    last_error_at=r[3], tokens_today=int(r[4] or 0),
                    tokens_prev_avg=float(r[5] or 0), cost_today=float(r[6] or 0),
                    cost_prev_avg=float(r[7] or 0),
                )
                for r in rows
            ]
    finally:
        await engine.dispose()

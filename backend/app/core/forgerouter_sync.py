"""Read access to ForgeRouter's own agent registry.

ForgeRouter (the ecosystem's exclusive LLM gateway) issues and tracks one
API key per connected agent in its own database -- `forgerouter_postgres`
(port 5432) -> database `forgerouter` -> schema `ai_router`, table
`agents` (see /root/.hermes/foundation/governance/POSTGRESQL_TOPOLOGY.md
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

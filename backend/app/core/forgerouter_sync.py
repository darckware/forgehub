"""Read access to ForgeRouter's own agent registry.

ForgeRouter (the ecosystem's exclusive LLM gateway) issues and tracks one
API key per connected agent in its own database -- `foundation_postgres`
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
generic `foundation_postgres`/`forgerouter` connection (settings.db_url_for)
-- this module just narrows that to one query.
"""
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings


@dataclass(frozen=True)
class ForgeRouterAgentKey:
    name: str
    api_key: str


async def _read_ai_router_agents(kind: str) -> list[ForgeRouterAgentKey]:
    url = settings.db_url_for(
        settings.FOUNDATION_POSTGRES_HOST, settings.FOUNDATION_POSTGRES_PORT, "forgerouter"
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

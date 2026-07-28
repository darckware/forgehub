"""Shared "apply a catalog server to a target" logic for the MCP catalog
(db/models/mcp_catalog.py) -- used by mcp_catalog.py's own routes (explicit
assignment, and re-applying every eligible agent when a server's
`apply_to_all_agents` flips to True) and by agent.py's create/sync routes
(applying every `apply_to_all_agents` server to a brand new or newly-typed
agent, so "global" genuinely means "including agents registered later").

Kept as its own module (not inside api/routes/mcp_catalog.py) specifically
so api/routes/agent.py can import it without an api-routes-importing-
api-routes cycle.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import agent_mcp
from app.db.models.agent import Agent
from app.db.models.mcp_catalog import McpCatalogAssignment, McpCatalogServer


async def _get_or_create_assignment(
    db: AsyncSession, catalog_server_id: uuid.UUID, target_type: str, target_id: uuid.UUID
) -> McpCatalogAssignment:
    result = await db.execute(
        select(McpCatalogAssignment).where(
            McpCatalogAssignment.catalog_server_id == catalog_server_id,
            McpCatalogAssignment.target_type == target_type,
            McpCatalogAssignment.target_id == target_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = McpCatalogAssignment(
            catalog_server_id=catalog_server_id, target_type=target_type, target_id=target_id
        )
        db.add(row)
    return row


def agent_is_mcp_eligible(agent: Agent) -> bool:
    """Mirrors api/routes/agent.py's `_require_mcp_target` gate, without
    raising -- a global catalog server silently skips an ineligible agent
    (no runtime, or no resolvable home) rather than erroring the whole
    apply pass over one agent."""
    fmt = agent_mcp.format_for(agent.runtime_type)
    if fmt is None:
        return False
    host_path = agent_mcp.config_host_path(agent.effective_home_path, fmt)
    return bool(host_path)


async def apply_catalog_server_to_agent(
    db: AsyncSession, server: McpCatalogServer, agent: Agent
) -> McpCatalogAssignment:
    """Write `server` into `agent`'s own runtime config file (via the same
    agent_mcp engine /mcp already uses) and record the outcome on the
    assignment row. Never raises -- a write failure is recorded in
    `last_sync_error`, not propagated, so one bad agent doesn't abort a
    whole "apply to all" pass."""
    assignment = await _get_or_create_assignment(db, server.id, "agent", agent.id)
    fmt = agent_mcp.format_for(agent.runtime_type)
    host_path = agent_mcp.config_host_path(agent.effective_home_path, fmt) if fmt else None
    if fmt is None or not host_path:
        assignment.last_sync_error = (
            f"Agent {agent.name} has no runtime that loads MCP servers "
            f"(runtime_type={agent.runtime_type!r})."
        )
        return assignment
    try:
        agent_mcp.write_server(
            host_path,
            fmt,
            server.name,
            agent_mcp.McpServerInfo(
                name=server.name,
                command=server.command,
                args=server.args or [],
                env=server.env or {},
                url=server.url,
                enabled=True,
            ),
        )
    except agent_mcp.McpConfigError as exc:
        assignment.last_sync_error = str(exc)
        return assignment
    assignment.enabled = True
    assignment.last_synced_at = datetime.now(timezone.utc)
    assignment.last_sync_error = None
    return assignment


async def apply_global_servers_to_agent(db: AsyncSession, agent: Agent) -> list[McpCatalogAssignment]:
    """Every `apply_to_all_agents=True` catalog server, applied to one agent
    -- called when that agent is newly created or newly given a runtime_type
    (see api/routes/agent.py's create_agent/sync_agent_runtimes), so "global"
    reaches agents registered after the flag was set, not just the ones that
    existed at the time."""
    if not agent_is_mcp_eligible(agent):
        return []
    result = await db.execute(select(McpCatalogServer).where(McpCatalogServer.apply_to_all_agents.is_(True)))
    servers = list(result.scalars().all())
    return [await apply_catalog_server_to_agent(db, server, agent) for server in servers]


async def apply_global_server_to_all_agents(
    db: AsyncSession, server: McpCatalogServer
) -> list[McpCatalogAssignment]:
    """The other direction: a server's `apply_to_all_agents` just flipped to
    True -- apply it to every currently-eligible active agent immediately
    (future agents are covered by apply_global_servers_to_agent above)."""
    result = await db.execute(select(Agent).where(Agent.is_active.is_(True)))
    agents = list(result.scalars().all())
    return [
        await apply_catalog_server_to_agent(db, server, agent)
        for agent in agents
        if agent_is_mcp_eligible(agent)
    ]

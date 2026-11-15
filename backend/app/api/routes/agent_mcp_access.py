"""Agentes e MCP do ForgeHub: which servers each agent gets and how its two sensitive actions run
(Marcelo, 2026-11-15: "uma lista dos agentes e uma coluna com os mcp do forgehub para associar aos
agentes"; plan D4; business rules MCP-005 and MCP-023). Admin only.

``GET /api/v1/mcp-access`` lists every active registered agent with its saved row (or, without one,
its function's defaults, marked ``saved: false``). ``PUT /api/v1/mcp-access/{agent_id}`` saves one
agent; ``expected_updated_at`` refuses a stale screen (409). Every save is an AuditEvent with the
change. The sensitive-action modes take effect at once (the middleware reads this table); the servers
are applied to the agents' configurations by the migration waves (plan, Fase 3).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_mcp_actions import CORE_SERVER, OPTIONAL_SERVERS, PERSONAL_SERVER, function_defaults
from app.core.deps import get_current_admin
from app.db.base import get_db
from app.db.models.agent import Agent
from app.db.models.agent_mcp_access import AgentMcpAccess
from app.db.models.governance import AuditEvent
from app.db.models.user import User

router = APIRouter(prefix="/api/v1/mcp-access", tags=["agent-mcp-access"])

Mode = Literal["direct", "approval"]
# Who may get Marcelo's personal tools: the same allowlist personal_contacts enforces (default: maia).
PERSONAL_AGENTS = frozenset({"maia"})


class AgentMcpAccessOut(BaseModel):
    agent_id: uuid.UUID
    name: str
    profile_slug: str | None
    department: str | None
    runtime_type: str | None
    core_server: str = CORE_SERVER
    servers: list[str]
    restart_mode: Mode
    query_mode: Mode
    personal_allowed: bool
    saved: bool
    suggested: dict
    updated_by: str | None = None
    updated_at: datetime | None = None


class AgentMcpAccessCatalog(BaseModel):
    core_server: str = CORE_SERVER
    servers: list[str] = list(OPTIONAL_SERVERS)
    agents: list[AgentMcpAccessOut]


class AgentMcpAccessIn(BaseModel):
    servers: list[str] = Field(default_factory=list)
    restart_mode: Mode
    query_mode: Mode
    expected_updated_at: datetime | None = None


def _out(agent: Agent, access: AgentMcpAccess | None) -> AgentMcpAccessOut:
    suggested = function_defaults(agent.department)
    personal = (agent.profile_slug or "") in PERSONAL_AGENTS
    source = access or None
    servers = list(source.servers) if source else [s for s in suggested["servers"] if s != PERSONAL_SERVER or personal]
    return AgentMcpAccessOut(
        agent_id=agent.id, name=agent.name, profile_slug=agent.profile_slug, department=agent.department,
        runtime_type=agent.runtime_type, servers=servers,
        restart_mode=source.restart_mode if source else suggested["restart_mode"],
        query_mode=source.query_mode if source else suggested["query_mode"],
        personal_allowed=personal, saved=source is not None, suggested=suggested,
        updated_by=source.updated_by if source else None, updated_at=source.updated_at if source else None,
    )


@router.get("", response_model=AgentMcpAccessCatalog)
async def list_mcp_access(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_admin)):
    agents = (await db.execute(
        select(Agent).where(Agent.is_active.is_(True), Agent.status == "active").order_by(Agent.name)
    )).scalars().all()
    rows = {row.agent_id: row for row in (await db.execute(select(AgentMcpAccess))).scalars()}
    return AgentMcpAccessCatalog(agents=[_out(agent, rows.get(agent.id)) for agent in agents])


@router.put("/{agent_id}", response_model=AgentMcpAccessOut)
async def save_mcp_access(
    agent_id: uuid.UUID, payload: AgentMcpAccessIn,
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    agent = await db.get(Agent, agent_id)
    if agent is None or not agent.is_active or agent.status != "active":
        raise HTTPException(404, "Active agent not found")
    unknown = sorted(set(payload.servers) - set(OPTIONAL_SERVERS))
    if unknown:
        raise HTTPException(422, {"code": "UNKNOWN_MCP_SERVER", "servers": unknown})
    if PERSONAL_SERVER in payload.servers and (agent.profile_slug or "") not in PERSONAL_AGENTS:
        raise HTTPException(422, {"code": "PERSONAL_NOT_ALLOWED",
                                  "message": "Only the Maia gets Marcelo's personal tools."})
    access = await db.get(AgentMcpAccess, agent_id)
    if access is not None and payload.expected_updated_at is not None and access.updated_at != payload.expected_updated_at:
        raise HTTPException(409, {"code": "MCP_ACCESS_CHANGED", "message": "Changed since loaded; reload the screen."})
    servers = [s for s in OPTIONAL_SERVERS if s in set(payload.servers)]
    before = None if access is None else {
        "servers": list(access.servers), "restart_mode": access.restart_mode, "query_mode": access.query_mode}
    after = {"servers": servers, "restart_mode": payload.restart_mode, "query_mode": payload.query_mode}
    if access is None:
        access = AgentMcpAccess(agent_id=agent_id)
        db.add(access)
    access.servers = servers
    access.restart_mode = payload.restart_mode
    access.query_mode = payload.query_mode
    access.updated_by = admin.username
    db.add(AuditEvent(entity_type="agent_mcp_access", entity_id=agent_id, event_type="agent_mcp_access_saved",
                      actor=admin.username, payload={"agent": agent.profile_slug, "before": before, "after": after}))
    await db.commit()
    await db.refresh(access)
    return _out(agent, access)

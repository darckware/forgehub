"""Which agents may open the screens, and the audit of what they did there."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_session import AUDIT_ENTITY, EVENT_OPENED
from app.core.deps import get_current_admin
from app.db.base import get_db
from app.db.models.agent import Agent, AgentServiceCredential
from app.db.models.governance import AuditEvent
from app.db.models.user import User

router = APIRouter(prefix="/api/v1/agent-access", tags=["agent-access"])


class AgentAccessRow(BaseModel):
    id: uuid.UUID
    name: str
    slug: str | None
    enabled: bool
    has_credential: bool
    last_session_at: datetime | None


class AgentAccessUpdate(BaseModel):
    enabled: bool


class AccessEvent(BaseModel):
    id: uuid.UUID
    agent: str
    event: str
    occurred_at: datetime
    details: dict[str, Any]


@router.get("", response_model=list[AgentAccessRow])
async def list_agent_access(
    _admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
) -> list[AgentAccessRow]:
    agents = (await db.execute(
        select(Agent).where(Agent.is_active.is_(True)).order_by(Agent.name)
    )).scalars().all()
    with_credential = set((await db.execute(
        select(AgentServiceCredential.agent_id).where(AgentServiceCredential.revoked_at.is_(None))
    )).scalars())
    last_sessions = dict((await db.execute(
        select(AuditEvent.entity_id, func.max(AuditEvent.created_at))
        .where(AuditEvent.entity_type == AUDIT_ENTITY, AuditEvent.event_type == EVENT_OPENED)
        .group_by(AuditEvent.entity_id)
    )).all())
    return [AgentAccessRow(id=a.id, name=a.name, slug=a.profile_slug, enabled=a.screen_access_enabled,
                           has_credential=a.id in with_credential, last_session_at=last_sessions.get(a.id))
            for a in agents]


@router.put("/{agent_id}", response_model=AgentAccessRow)
async def update_agent_access(
    agent_id: uuid.UUID, payload: AgentAccessUpdate,
    admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db),
) -> AgentAccessRow:
    """Turning an agent off ends its open sessions on their next request."""
    agent = await db.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(404, "Agent not found")
    agent.screen_access_enabled = payload.enabled
    db.add(AuditEvent(entity_type=AUDIT_ENTITY, entity_id=agent.id, event_type="access_changed",
                      actor=admin.username, payload={"enabled": payload.enabled}))
    await db.commit()
    rows = await list_agent_access(admin, db)
    return next(row for row in rows if row.id == agent_id)


@router.get("/audit", response_model=list[AccessEvent])
async def list_access_audit(
    agent_id: uuid.UUID | None = None,
    event: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> list[AccessEvent]:
    query = select(AuditEvent).where(AuditEvent.entity_type == AUDIT_ENTITY)
    if agent_id:
        query = query.where(AuditEvent.entity_id == agent_id)
    if event:
        query = query.where(AuditEvent.event_type == event)
    rows = (await db.execute(query.order_by(AuditEvent.created_at.desc()).limit(limit))).scalars().all()
    return [AccessEvent(id=row.id, agent=row.actor, event=row.event_type, occurred_at=row.created_at,
                        details=row.payload or {}) for row in rows]

"""Executor availability (Plano Integrado M0.8, cycle spec §3.3, §7).

- ``GET /api/v1/agents/{id}/availability``  current unavailability, if any
- ``PUT /api/v1/agents/{id}/availability``  set_agent_unavailable (until=None clears)

Marcelo (admin) or an agent holding ``mission.orchestrate`` (an orchestrator),
always with a reason; idempotent by key. The usage-limit patterns write the
same row on their own (``core/agent_availability.py``).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.mission_cycle import AvailabilityIn, AvailabilityOut
from app.core.command_receipts import (
    begin_command,
    enforce_command_limits,
    limit_command_body,
    record_command,
    request_hash,
)
from app.core.deps import ActorPrincipal, authorize_action, get_actor_principal
from app.core.mission import mission_error
from app.core.mission_cycle import utcnow
from app.db.base import get_db
from app.db.models.agent import Agent
from app.db.models.governance import AuditEvent
from app.db.models.mission_cycle import AgentAvailability

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


def _out(agent_id: uuid.UUID, row: AgentAvailability | None) -> AvailabilityOut:
    if row is None or row.unavailable_until <= utcnow():
        return AvailabilityOut(agent_id=agent_id)
    return AvailabilityOut(agent_id=agent_id, unavailable_until=row.unavailable_until, reason=row.reason,
                           recorded_by=row.recorded_by)


async def _authorize(db: AsyncSession, principal: ActorPrincipal) -> tuple[str, object]:
    if principal.principal_type == "user":
        if not principal.is_admin:
            raise mission_error(403, "MARCELO_ONLY", "Only an administrator or an orchestrator sets availability")
        return "admin", None
    try:
        return await authorize_action(db, principal, "mission.orchestrate")
    except HTTPException as exc:
        if exc.status_code != 403:
            raise
        raise mission_error(403, "DELEGATION_REQUIRED", "No active delegation permits mission.orchestrate",
                            action="mission.orchestrate") from exc


@router.get("/{agent_id}/availability", response_model=AvailabilityOut)
async def get_agent_availability(
    agent_id: uuid.UUID,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
) -> AvailabilityOut:
    if await db.get(Agent, agent_id) is None:
        raise mission_error(404, "AGENT_NOT_FOUND", "Agent not found")
    return _out(agent_id, await db.get(AgentAvailability, agent_id))


@router.put("/{agent_id}/availability", response_model=AvailabilityOut,
            dependencies=[Depends(limit_command_body)])
async def set_agent_availability(
    agent_id: uuid.UUID,
    payload: AvailabilityIn,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
):
    enforce_command_limits(principal)
    source, delegation = await _authorize(db, principal)
    command = "agent.set_availability"
    body_hash = request_hash(command, {"agent_id": str(agent_id), **payload.model_dump(mode="json")})
    replay = await begin_command(db, principal, payload.idempotency_key, command, body_hash)
    if replay is not None:
        return replay
    if await db.get(Agent, agent_id) is None:
        raise mission_error(404, "AGENT_NOT_FOUND", "Agent not found")
    if payload.until is not None and payload.until.tzinfo is None:
        raise mission_error(422, "UNTIL_NOT_ZONED", "until must carry a timezone")
    row = (await db.execute(select(AgentAvailability).where(AgentAvailability.agent_id == agent_id)
                            .with_for_update())).scalar_one_or_none()
    before = row.unavailable_until.isoformat() if row is not None else None
    if payload.until is None:
        if row is not None:
            await db.delete(row)
            row = None
    elif row is None:
        row = AgentAvailability(agent_id=agent_id, unavailable_until=payload.until, reason=payload.reason.strip(),
                                recorded_by=principal.display_name)
        db.add(row)
    else:
        row.unavailable_until, row.reason = payload.until, payload.reason.strip()
        row.recorded_by, row.source_demand_id = principal.display_name, None
    db.add(AuditEvent(entity_type="agent", entity_id=agent_id, event_type="agent_availability_set",
                      actor=principal.display_name,
                      payload={"before": before, "until": payload.until.isoformat() if payload.until else None,
                               "reason": payload.reason, "principal_type": principal.principal_type,
                               "authority_source": source,
                               "delegation_id": str(delegation.id) if delegation is not None else None}))
    await db.flush()
    out = _out(agent_id, row)
    record_command(db, principal, payload.idempotency_key, command, body_hash, 200, out.model_dump(mode="json"),
                   target_type="agent", target_id=agent_id)
    await db.commit()
    return JSONResponse(status_code=200, content=out.model_dump(mode="json"))

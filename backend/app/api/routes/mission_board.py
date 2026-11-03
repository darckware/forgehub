"""Mission executions screen routes (Plano Integrado M0.7).

Contract: docs/architecture/MISSION_EXECUTIONS_SCREEN_SPEC.md §3.2, §8, §10.
Read-only; every action on the screen calls its own guarded route
(``POST /tasks/{id}/dispatch``, ``POST /missions/{p}/tasks/{t}:assign|
:request-review|:return``, ``POST /missions/{p}:transition``,
``POST /missions/{p}/review-items/{id}:decide``), and the ``allowed_actions``
here are a dry run of those same guards (core/mission_board.py).

- ``GET /api/v1/missions``                          mission summaries + contested agents (§8)
- ``GET /api/v1/missions/{project_id}/executions``  the board (§4)
- ``GET /api/v1/missions/{project_id}/timeline``    decisions and transitions

Who reads: an admin, a person with the ``product`` module (read only, §10),
or an agent that is the mission's orchestrator or an active member (any
other agent gets 404, no existence leak).
"""
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.mission import _load
from app.core.deps import ActorPrincipal, get_actor_principal
from app.core import mission_board
from app.core.mission_plan import mission_scope_tasks
from app.db.base import get_db
from app.db.models.agent import Agent
from app.db.models.governance import AuditEvent
from app.db.models.mission import MISSION_STATES
from app.db.models.task import TaskExecution

router = APIRouter(prefix="/api/v1/missions", tags=["missions"])

# Payload keys the timeline may show; idempotency keys, hashes and ids stay out.
TIMELINE_KEYS = ("reason", "from_state", "to", "role", "description", "status", "decision", "agent_id",
                 "previous_status", "authority_source", "principal_type", "stage", "to_stage")


def _task_number(event: AuditEvent, numbers: dict[uuid.UUID, int]) -> int | None:
    if event.entity_id in numbers:
        return numbers[event.entity_id]
    try:
        return numbers.get(uuid.UUID(str((event.payload or {}).get("task_id"))))
    except ValueError:
        return None


@router.get("")
async def list_missions(
    state: str | None = Query(default=None, max_length=300, description="comma-separated states"),
    orchestrator_id: uuid.UUID | None = None,
    agent_id: uuid.UUID | None = None,
    has_conflicts: bool | None = None,
    has_uncertain: bool | None = None,
    q: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await mission_board.assert_can_list(db, principal)
    states = {s.strip() for s in state.split(",") if s.strip()} if state else set()
    states &= set(MISSION_STATES)
    summaries = []
    for project, mission in await mission_board.visible_missions(db, principal):
        if states and mission.state not in states:
            continue
        if orchestrator_id and mission.orchestrator_agent_id != orchestrator_id:
            continue
        if q and q.strip().lower() not in project.name.lower():
            continue
        board = await mission_board.build_board(db, project, mission, principal, check_git=False,
                                                include_planning=False)
        summary = mission_board.summarize(board, await mission_board.last_decision(db, project.id))
        if agent_id and str(agent_id) not in summary["_agents"] and not any(
            t["reviewer"] and t["reviewer"]["agent_id"] == str(agent_id) for t in board["tasks"]
        ):
            continue
        if has_conflicts and not summary["conflicts"]:
            continue
        if has_uncertain and not summary["uncertain"]:
            continue
        summaries.append(summary)
    summaries.sort(key=lambda s: (mission_board.STATE_GROUP.get(s["state"], 9), s["priority"],
                                  s["deadline_at"] or "9999"))
    agent_ids = {a for s in summaries for a in s["_waiting_agents"]}
    names = {str(a.id): a.name for a in (await db.execute(select(Agent).where(
        Agent.id.in_([uuid.UUID(a) for a in agent_ids])))).scalars()} if agent_ids else {}
    contested = mission_board.contested_agents(summaries, names)
    total = len(summaries)
    start = (page - 1) * page_size
    items = [{k: v for k, v in s.items() if not k.startswith("_")} for s in summaries[start:start + page_size]]
    return {"items": items, "total": total, "page": page, "page_size": page_size, "contested_agents": contested}


@router.get("/{project_id}/executions")
async def get_mission_executions(
    project_id: uuid.UUID,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    project, mission = await _load(db, project_id)
    await mission_board.assert_can_read_board(db, principal, mission)
    return await mission_board.build_board(db, project, mission, principal)


@router.get("/{project_id}/timeline")
async def get_mission_timeline(
    project_id: uuid.UUID,
    before: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    task_id: uuid.UUID | None = None,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    _project, mission = await _load(db, project_id)
    await mission_board.assert_can_read_board(db, principal, mission)
    scope = await mission_scope_tasks(db, project_id)
    task_ids = [task_id] if task_id is not None and task_id in scope else ([] if task_id else list(scope))
    execution_ids = list((await db.execute(select(TaskExecution.id).where(
        TaskExecution.task_id.in_(task_ids)))).scalars()) if task_ids else []
    clauses = [(AuditEvent.entity_type == "project_task") & AuditEvent.entity_id.in_(task_ids)] if task_ids else []
    if execution_ids:
        clauses.append((AuditEvent.entity_type == "task_execution") & AuditEvent.entity_id.in_(execution_ids))
    if task_id is None:
        clauses.append((AuditEvent.entity_type == "mission") & (AuditEvent.entity_id == project_id))
    if not clauses:
        return {"items": [], "next_before": None}
    stmt = select(AuditEvent).where(or_(*clauses))
    if before is not None:
        stmt = stmt.where(AuditEvent.created_at < before)
    rows = list((await db.execute(stmt.order_by(AuditEvent.created_at.desc()).limit(limit))).scalars())
    numbers = {t.id: t.number for t in scope.values()}
    items = [{
        "id": str(e.id), "entity_type": e.entity_type, "entity_id": str(e.entity_id), "event_type": e.event_type,
        "actor": e.actor, "at": e.created_at.isoformat(),
        "task_number": _task_number(e, numbers),
        "payload": {k: v for k, v in (e.payload or {}).items() if k in TIMELINE_KEYS},
    } for e in rows]
    return {"items": items, "next_before": rows[-1].created_at.isoformat() if len(rows) == limit else None}

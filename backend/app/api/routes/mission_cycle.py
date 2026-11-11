"""Orchestrator decision cycle routes (Plano Integrado M0.8).

Contract: docs/architecture/MISSION_ORCHESTRATOR_CYCLE_SPEC.md §2.3, §3, §4,
§5, §6.3, §7.

- ``GET  /api/v1/missions/{id}/cycle``                       get_mission_cycle
- ``POST /api/v1/missions/{id}/decisions``                   one decision of the cycle
- ``GET  /api/v1/missions/{id}/decisions``                   the decision timeline
- ``POST /api/v1/missions/{id}/decisions/{did}:undo``        Marcelo undoes one
- ``POST /api/v1/missions/{id}/cycle:lock|:unlock``          Marcelo locks the cycle
- ``POST /api/v1/missions/{id}/tasks/{tid}:lock-cycle|:unlock-cycle``
- ``POST /api/v1/missions/{id}/skill-proposals``             propose_skill_change
- ``POST|DELETE /api/v1/missions/{id}/dependencies[/{did}]`` §6.3

``POST /decisions`` is the only way the cycle acts, and it acts only by
calling the existing guarded route functions (dispatch, assign, request
review, return, reprocess, transition, the completion guard): never a
shortcut. Every attempt -- applied, deferred or refused by a guard, with the
guard's code -- is a ``mission_decisions`` row with its reason, and an
applied/deferred one also an ``AuditEvent(entity_type="mission")``. The row is
added before the effect, so it commits in the same transaction as the effect
(a refusal rolls both back and records the refused row on its own).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import mission_task as mt
from app.api.routes.mission import _load
from app.api.schemas.mission import MissionTransitionIn, ReviewRequestIn, TaskAssignIn, TaskReturnIn
from app.api.schemas.mission_cycle import (
    CycleLockIn,
    CycleLockOut,
    CycleOut,
    CycleUnlockIn,
    DecisionIn,
    DecisionOut,
    MissionDependencyIn,
    MissionDependencyOut,
    SkillProposalIn,
    SkillProposalOut,
    UndoIn,
)
from app.core.agent_availability import classify_infra_failure
from app.core.command_receipts import (begin_command, enforce_command_limits, limit_command_body,
                                       record_command, request_hash, require_mission_tools)
from app.core.deps import ActorPrincipal, authorize_action, get_actor_principal
from app.core.mission import mission_error
from app.core.mission_cycle import (
    INTEGRATION_REF_PREFIX,
    assert_cycle_unlocked,
    build_cycle,
    mission_routine,
    latest_context_version,
    open_cycle_run,
    open_locks,
    write_context_version,
)
from app.db.base import get_db
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent
from app.db.models.mission import MissionDecision, ProjectMission
from app.db.models.mission_cycle import MissionCycleLock, MissionDependency, MissionSkillProposal
from app.db.models.operations import AgentQuestion, AgentRoutineRun
from app.db.models.orchestration import TaskExecutionReview
from app.db.models.project import Project
from app.db.models.task import ProjectTask, TaskAssignment, TaskExecution

router = APIRouter(prefix="/api/v1/missions", tags=["missions"])

from app.core.task_recovery import router as task_recovery_router
router.include_router(task_recovery_router)

ORCHESTRATE_ACTION = "mission.orchestrate"
COMMAND_DEPENDENCIES = [Depends(require_mission_tools), Depends(limit_command_body)]
LOCAL_TZ = ZoneInfo("America/Sao_Paulo")


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _authorize_cycle(
    db: AsyncSession, principal: ActorPrincipal, mission: ProjectMission,
) -> tuple[str, Any]:
    """Marcelo (admin) or the mission's orchestrator with mission.orchestrate."""
    if principal.principal_type == "user":
        if not principal.is_admin:
            raise mission_error(403, "MISSION_ADMIN_ONLY", "Only an administrator acts on a mission in M0")
        return "admin", None
    if principal.principal_id != mission.orchestrator_agent_id:
        if await mt._active_membership(db, mission.project_id, principal.principal_id):
            raise mission_error(403, "ORCHESTRATOR_ONLY", "Only the mission's orchestrator runs its cycle")
        raise mission_error(404, "MISSION_NOT_FOUND", "Mission not found")
    try:
        return await authorize_action(db, principal, ORCHESTRATE_ACTION, project_id=mission.project_id)
    except HTTPException as exc:
        if exc.status_code != 403:
            raise
        raise mission_error(403, "DELEGATION_REQUIRED", f"No active delegation permits {ORCHESTRATE_ACTION} here",
                            action=ORCHESTRATE_ACTION) from exc


def _require_admin(principal: ActorPrincipal) -> None:
    if principal.principal_type != "user" or not principal.is_admin:
        raise mission_error(403, "MARCELO_ONLY", "Only Marcelo (an administrator) does this in M0")


def _decision_out(row: MissionDecision) -> DecisionOut:
    return DecisionOut.model_validate(row)


async def _cycle_run(db: AsyncSession, mission: ProjectMission, cycle_id: uuid.UUID | None) -> AgentRoutineRun | None:
    if cycle_id is None:
        return None
    routine = await mission_routine(db, mission.project_id)
    run = await db.get(AgentRoutineRun, cycle_id)
    if routine is None or run is None or run.routine_id != routine.id:
        raise mission_error(422, "CYCLE_NOT_FOUND", "cycle_id is not a cycle run of this mission")
    return run


# ---------------------------------------------------------------------------
# get_mission_cycle (§2.3)
# ---------------------------------------------------------------------------
@router.get("/{project_id}/cycle", response_model=CycleOut)
async def get_mission_cycle(
    project_id: uuid.UUID,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
) -> CycleOut:
    """The board and the deterministic proposals. Locked: still answers, with
    every proposal `allowed=false` and `locked` set."""
    _project, mission = await _load(db, project_id)
    await _authorize_cycle(db, principal, mission)
    routine = await mission_routine(db, project_id)
    run = await open_cycle_run(db, routine) if routine is not None else None
    if run is None and routine is not None:
        run = (await db.execute(select(AgentRoutineRun).where(AgentRoutineRun.routine_id == routine.id)
                                .order_by(AgentRoutineRun.occurrence_at.desc()).limit(1))).scalar_one_or_none()
    cycle = await build_cycle(db, mission)
    return CycleOut(project_id=project_id, cycle_id=run.id if run else None, **cycle)


@router.get("/{project_id}/decisions", response_model=list[DecisionOut])
async def list_mission_decisions(
    project_id: uuid.UUID,
    limit: int = 200,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
) -> list[DecisionOut]:
    _project, mission = await _load(db, project_id)
    await _authorize_cycle(db, principal, mission)
    rows = (await db.execute(select(MissionDecision).where(MissionDecision.mission_project_id == project_id)
                             .order_by(MissionDecision.created_at.desc()).limit(max(1, min(limit, 500))))).scalars()
    return [_decision_out(r) for r in rows]


# ---------------------------------------------------------------------------
# One decision (§2.3 item 2, §3, §4)
# ---------------------------------------------------------------------------
def _detail(exc: HTTPException) -> dict[str, Any]:
    if isinstance(exc.detail, dict):
        return dict(exc.detail)
    text = str(exc.detail)
    code = text.split(":", 1)[0] if ":" in text and text.split(":", 1)[0].isupper() else "GUARD_REFUSED"
    return {"code": code, "message": text}


async def _record_refused(db: AsyncSession, decision_id: uuid.UUID, fields: dict[str, Any], code: str) -> None:
    """The attempt is recorded even when a guard refused it. If the effect had
    already committed the row (e.g. a reservation that then failed), it turns
    refused; otherwise a refused row is inserted on its own."""
    existing = await db.get(MissionDecision, decision_id)
    if existing is not None and existing.status == "pending" and existing.action in {"dispatch", "schedule"}:
        from app.db.models.command_receipt import AgentCommandReceipt
        inner = await db.scalar(select(AgentCommandReceipt).where(
            AgentCommandReceipt.principal_type == fields["actor_type"],
            AgentCommandReceipt.principal_id == fields["actor_id"],
            AgentCommandReceipt.idempotency_key == f"cycle:{fields['idempotency_key']}",
            AgentCommandReceipt.command == "task.dispatch",
        ))
        demand = await db.get(AgentDemand, inner.target_id) if inner and inner.target_type == "agent_demand" else None
        if demand is not None and demand.agent_run_id:
            existing.facts = {**(existing.facts or {}), "recovery_reason": code[:60]}
            await db.commit()
            return
    if existing is not None:
        existing.status, existing.refusal_code = "refused", code[:60]
    else:
        db.add(MissionDecision(id=decision_id, **{**fields, "status": "refused", "refusal_code": code[:60]}))
    await db.commit()


@router.post("/{project_id}/decisions", response_model=DecisionOut, status_code=status.HTTP_201_CREATED,
             dependencies=COMMAND_DEPENDENCIES)
async def decide(
    project_id: uuid.UUID,
    payload: DecisionIn,
    authorization: str | None = Header(default=None),
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
):
    enforce_command_limits(principal)
    _project, mission = await _load(db, project_id)
    source, delegation = await _authorize_cycle(db, principal, mission)
    body_hash = request_hash("mission.decide", {"project_id": project_id, **payload.model_dump(mode="json")})
    receipt = await begin_command(db, principal, payload.idempotency_key, "mission.decide", body_hash)
    if receipt is not None:
        return receipt
    replay = (await db.execute(select(MissionDecision).where(
        MissionDecision.actor_type == principal.principal_type, MissionDecision.actor_id == principal.principal_id,
        MissionDecision.idempotency_key == payload.idempotency_key))).scalar_one_or_none()
    if replay is not None:
        if (replay.action != payload.action or replay.mission_project_id != project_id
                or (replay.facts or {}).get("request_hash") != body_hash):
            raise mission_error(409, "IDEMPOTENCY_KEY_REUSED", "This key was used for another decision")
        if replay.status == "pending" or (replay.status == "applied" and "context_version" not in (replay.facts or {})):
            effect = await _recover_dispatch_effect(db, replay, payload, principal)
            out = await _complete_decision(db, replay, effect, project_id, payload, principal, source, body_hash)
            return JSONResponse(status_code=200, content=out.model_dump(mode="json"),
                                headers={"Idempotent-Replay": "true"})
        return JSONResponse(status_code=200, content=_decision_out(replay).model_dump(mode="json"),
                            headers={"Idempotent-Replay": "true"})
    # A different idempotency key must not consume the same context version.
    # External starts commit a pending decision with their reservation, so a
    # later command can see that fence without holding a lock across the start.
    _project, mission = await _load(db, project_id, lock=True)
    source, delegation = await _authorize_cycle(db, principal, mission)
    pending = await db.scalar(select(MissionDecision.id).where(
        MissionDecision.mission_project_id == project_id, MissionDecision.status == "pending").limit(1))
    if pending is not None:
        raise mission_error(409, "MISSION_DECISION_IN_FLIGHT", "Recover the pending decision before making another",
                            decision_id=str(pending))
    if principal.principal_type == "agent" and payload.expected_context_version is None:
        raise mission_error(409, "CONTEXT_VERSION_REQUIRED",
                            "Read get_mission_cycle and pass expected_context_version for a new agent decision")
    if payload.expected_context_version is not None:
        current_context = await latest_context_version(db, project_id)
        current_version = current_context.version if current_context else 0
        if current_version != payload.expected_context_version:
            raise mission_error(409, "CONTEXT_VERSION_STALE", "Read the current mission context before deciding",
                                expected=payload.expected_context_version, current=current_version)
    if mission.autonomy_level != "N0":
        raise mission_error(409, "AUTONOMY_NOT_N0", "Onda 1 runs every mission at N0")
    await assert_cycle_unlocked(db, mission, principal, payload.task_id)
    run = await _cycle_run(db, mission, payload.cycle_id)
    task: ProjectTask | None = None
    task_project_id: uuid.UUID | None = None
    if payload.task_id is not None:
        task, task_project_id = await mt._scope_task(db, mission, payload.task_id)

    facts: dict[str, Any] = {"request_hash": body_hash}
    if payload.proposal_id:
        cycle = await build_cycle(db, mission)
        proposal = next((p for p in cycle["proposals"] if p["proposal_id"] == payload.proposal_id), None)
        if proposal is None:
            raise mission_error(409, "PROPOSAL_NOT_CURRENT",
                                "The proposal is not in the current cycle; read get_mission_cycle again")
        if proposal["action"] != payload.action and payload.action != "defer":
            raise mission_error(422, "PROPOSAL_ACTION_MISMATCH", "The decision's action differs from the proposal's",
                                proposal_action=proposal["action"])
        facts = {**facts, "proposal_id": proposal["proposal_id"], "reason_code": proposal["reason_code"],
                 **proposal["reason_facts"]}

    fields = dict(
        mission_project_id=project_id, cycle_id=run.id if run else None, action=payload.action,
        task_id=task.id if task else None, reason=payload.reason.strip(), facts=facts,
        autonomy_level=mission.autonomy_level, actor_type=principal.principal_type,
        actor_id=principal.principal_id, actor_name=principal.display_name, authority_source=source,
        delegation_id=delegation.id if delegation is not None else None,
        idempotency_key=payload.idempotency_key,
    )
    decision_id = uuid.uuid4()
    db.add(MissionDecision(id=decision_id, status="pending", **fields))
    await db.flush()
    try:
        effect = await _apply(db, payload, principal, mission, task, task_project_id, run, authorization)
    except HTTPException as exc:
        await db.rollback()
        detail = _detail(exc)
        await _record_refused(db, decision_id, fields, detail.get("code") or "GUARD_REFUSED")
        raise HTTPException(exc.status_code, detail={**detail, "decision_id": str(decision_id)}) from exc

    decision = await db.get(MissionDecision, decision_id, populate_existing=True)
    return await _complete_decision(db, decision, effect, project_id, payload, principal, source, body_hash)


async def _complete_decision(db, decision, effect, project_id, payload, principal, source, body_hash):
    decision.status = "deferred" if payload.action == "defer" else "applied"
    decision.facts = {**(decision.facts or {}), **effect.pop("facts", {})}
    for key, value in effect.items():
        setattr(decision, key, value)
    mission = await db.get(ProjectMission, project_id, populate_existing=True)
    db.add(AuditEvent(
        entity_type="mission", entity_id=project_id, event_type=f"mission_decision_{payload.action}",
        actor=principal.display_name,
        payload={"decision_id": str(decision.id), "reason": decision.reason, "status": decision.status,
                 "principal_type": principal.principal_type, "principal_id": str(principal.principal_id),
                 "authority_source": source, "cycle_id": str(decision.cycle_id) if decision.cycle_id else None,
                 "task_id": str(decision.task_id) if decision.task_id else None,
                 "demand_id": str(decision.demand_id) if decision.demand_id else None},
    ))
    await db.flush()
    pack = await write_context_version(db, mission, f"decision {payload.action}: {decision.reason}",
                                       actor_type=principal.principal_type, actor_id=principal.principal_id)
    decision.facts = {**decision.facts, "context_version": pack.version}
    record_command(db, principal, payload.idempotency_key, "mission.decide", body_hash, 201,
                   _decision_out(decision), target_type="mission", target_id=project_id)
    await db.commit()
    await db.refresh(decision)
    from app.core.dispatch_signal import wake_scheduled_dispatch
    wake_scheduled_dispatch()
    return _decision_out(decision)


async def _recover_dispatch_effect(db, decision, payload, principal):
    """Recover committed dispatch identity without invoking any execution route."""
    from app.db.models.command_receipt import AgentCommandReceipt

    if payload.action not in {"dispatch", "schedule"}:
        raise mission_error(409, "DECISION_RECOVERY_REQUIRED", "Reconcile the recorded action before retrying")
    inner = await db.scalar(select(AgentCommandReceipt).where(
        AgentCommandReceipt.principal_type == principal.principal_type,
        AgentCommandReceipt.principal_id == principal.principal_id,
        AgentCommandReceipt.idempotency_key == _inner_key(payload),
        AgentCommandReceipt.command == "task.dispatch",
    ))
    demand = await db.get(AgentDemand, inner.target_id) if inner and inner.target_type == "agent_demand" else None
    if (demand is None or decision.task_id is None or demand.origin_type != "task"
            or demand.origin_id != decision.task_id
            or (inner.response_body or {}).get("demand_id") != str(demand.id)):
        raise mission_error(409, "DECISION_RECOVERY_REQUIRED", "The committed dispatch identity is unavailable")
    return {"demand_id": demand.id, "facts": {
        "scheduled_at": demand.scheduled_at.isoformat() if payload.action == "schedule" and demand.scheduled_at else None,
        "demand_number": demand.number, "recovered_from_receipt": str(inner.id),
        "context_version_id": str(demand.mission_context_version_id) if demand.mission_context_version_id else None,
    }}


def _inner_key(payload: DecisionIn) -> str:
    return f"cycle:{payload.idempotency_key}"


def _require(value: Any, name: str) -> Any:
    if value is None:
        raise mission_error(422, "PARAM_REQUIRED", f"params.{name} is required for this action", param=name)
    return value


def _require_task(task: ProjectTask | None) -> ProjectTask:
    if task is None:
        raise mission_error(422, "TASK_REQUIRED", "task_id is required for this action")
    return task


async def _apply(
    db: AsyncSession, payload: DecisionIn, principal: ActorPrincipal, mission: ProjectMission,
    task: ProjectTask | None, task_project_id: uuid.UUID | None, run: AgentRoutineRun | None,
    authorization: str | None,
) -> dict[str, Any]:
    """Run the action through the existing guarded route functions; return
    what the decision row should record."""
    from app.api.routes.task import _dispatch_task_by_id
    from app.api.schemas.task import TaskInboxDispatchIn

    params = payload.params
    action = payload.action
    project_id = mission.project_id

    if action in ("dispatch", "schedule"):
        task = _require_task(task)
        scheduled_at = None
        if action == "schedule":
            scheduled_at = _require(params.scheduled_at, "scheduled_at")
            if scheduled_at.tzinfo is None or scheduled_at <= _now():
                raise mission_error(422, "SCHEDULE_NOT_IN_FUTURE", "scheduled_at must be a future, zoned time")
        authority = await mt._authorize(db, principal, mission, mt.ASSIGN_ACTION, task_project_id, task.id)
        out = await _dispatch_task_by_id(
            task.id, TaskInboxDispatchIn(scheduled_at=scheduled_at, command_text=params.command_text,
                                         idempotency_key=_inner_key(payload)),
            db, principal=principal, actor=principal.display_name, authority=authority,
        )
        demand = await db.get(AgentDemand, out.demand_id)
        return {"demand_id": out.demand_id, "facts": {
            "scheduled_at": scheduled_at.isoformat() if scheduled_at else None, "demand_number": out.demand_number,
            "context_version_id": str(demand.mission_context_version_id) if demand and demand.mission_context_version_id
            else None}}

    if action == "reassign":
        task = _require_task(task)
        agent_id = _require(params.agent_id, "agent_id")
        previous = await db.scalar(select(TaskAssignment.agent_id).where(
            TaskAssignment.task_id == task.id, TaskAssignment.status == "active")
            .order_by(TaskAssignment.created_at.desc()).limit(1))
        out = await mt._assign_task(project_id, task.id, TaskAssignIn(
            agent_id=agent_id, reason=payload.reason, idempotency_key=_inner_key(payload)), principal, db, commit=False)
        return {"facts": {"previous_agent_id": str(previous) if previous else None, "agent_id": str(agent_id),
                          "assignment_id": str(out.assignment_id)}}

    if action == "request_review":
        task = _require_task(task)
        execution_id = _require(params.execution_id, "execution_id")
        reviewer = _require(params.reviewer_agent_id, "reviewer_agent_id")
        replaced = None
        if params.replace_review_id is not None:
            replaced = await _fail_infra_review(db, task, params.replace_review_id)
        out = await mt._request_task_review(project_id, task.id, ReviewRequestIn(
            execution_id=execution_id, reviewer_agent_id=reviewer, idempotency_key=_inner_key(payload)),
            principal, db, commit=False)
        return {"review_id": out.review_id, "demand_id": out.demand_id,
                "facts": {"reviewer_agent_id": str(reviewer), "replaced_review": replaced}}

    if action == "return":
        task = _require_task(task)
        execution_id = _require(params.execution_id, "execution_id")
        out = await mt._return_task_for_correction(project_id, task.id, TaskReturnIn(
            execution_id=execution_id, reason=payload.reason, idempotency_key=_inner_key(payload)), principal, db, commit=False)
        return {"review_id": out.review_id, "facts": {"execution_id": str(execution_id),
                                                       "task_status": out.task_status}}

    if action == "reprocess":
        task = _require_task(task)
        demand_id = _require(params.demand_id, "demand_id")
        demand = await db.get(AgentDemand, demand_id)
        if demand is None or demand.origin_type != "task" or demand.origin_id != task.id:
            raise mission_error(404, "DEMAND_NOT_FOUND", "The demand is not a run of this task")
        from app.api.routes.demand import _reprocess_demand

        await mt._authorize(db, principal, mission, mt.ASSIGN_ACTION, task_project_id, task.id)
        try:
            await _reprocess_demand(demand_id, db, commit=False)
        except HTTPException as exc:
            code = "RETRY_LIMIT_REACHED" if "times" in str(exc.detail) else (
                "RECONCILIATION_REQUIRED" if "uncertain" in str(exc.detail) else "NOT_REPROCESSABLE")
            raise mission_error(exc.status_code, code, str(exc.detail)) from exc
        return {"demand_id": demand_id, "facts": {"infra": classify_infra_failure(
            demand.dispatch_result, demand.dispatch_error)}}

    if action == "integrate":
        return await _integrate(db, payload, principal, mission, _require_task(task), task_project_id, authorization)

    if action == "reverify":
        task = _require_task(task)
        execution = await mt._execution(db, task, _require(params.execution_id, "execution_id"))
        from app.core.task_completion_guard import resolve_executor_agent_id
        from app.core.task_evidence import verify_evidence

        if principal.principal_type == "agent" and principal.principal_id == await resolve_executor_agent_id(db, execution):
            raise mission_error(403, "REVERIFY_BY_EXECUTOR", "The executor does not re-verify its own delivery")
        if execution.status != "verified":
            raise mission_error(409, "EXECUTION_NOT_VERIFIED", "Only a verified execution is re-verified",
                                execution_status=execution.status)
        ok, detail = await verify_evidence(db, execution)
        # The environment sentinel (§3.4 item 2) has no recorded snapshot yet.
        return {"facts": {"execution_id": str(execution.id), "match": ok, "detail": detail[:500],
                          "evidence_ref": execution.evidence_ref, "sentinel": "not_evaluated"}}

    if action == "ask_marcelo":
        return await _ask_marcelo(db, payload, mission, run)

    if action == "pause":
        from app.api.routes.mission import _transition_mission

        reason = payload.reason.strip()
        if not reason.startswith("blocked:"):
            raise mission_error(403, "ORCHESTRATOR_PAUSE_ONLY_WHEN_BLOCKED",
                                "The cycle pauses a mission only when blocked (reason 'blocked:...')")
        current = await db.get(ProjectMission, project_id)
        await _transition_mission(project_id, MissionTransitionIn(
            to="paused", reason=reason, expected_row_version=current.row_version), principal, db, commit=False)
        return {"facts": {"paused": True}}

    # defer: a recorded non-action (§2.3 item 3).
    if task is not None:
        await mt._authorize(db, principal, mission, ORCHESTRATE_ACTION, task_project_id, task.id)
    return {}


async def _fail_infra_review(db: AsyncSession, task: ProjectTask, review_id: uuid.UUID) -> dict[str, Any]:
    """§3.4 item 3: an open review whose run ended on infrastructure is marked
    failed (never changes_requested) so another independent reviewer can take
    the same role."""
    review = await db.get(TaskExecutionReview, review_id)
    execution = await db.get(TaskExecution, review.execution_id) if review else None
    if review is None or execution is None or execution.task_id != task.id:
        raise mission_error(404, "REVIEW_NOT_FOUND", "Review not found for this task")
    demand = await db.get(AgentDemand, uuid.UUID(review.runtime_session_ref)) if review.runtime_session_ref else None
    kind = classify_infra_failure(demand.dispatch_result, demand.dispatch_error) if demand else None
    if review.status not in ("pending", "running") or demand is None or demand.dispatch_status != "failed" or not kind:
        raise mission_error(409, "REVIEW_NOT_REPLACEABLE",
                            "Only an open review whose run failed on infrastructure is replaced")
    review.status = "failed"
    review.feedback = f"infra_failure:{kind} (run #{demand.number}); not a review verdict"
    review.decided_at = _now()
    await db.flush()
    return {"review_id": str(review.id), "infra": kind, "demand_number": demand.number}


def _integration_body(task: ProjectTask, execution: TaskExecution) -> str:
    sha = (execution.evidence_ref or "").partition(":")[2]
    return "\n\n".join([
        f"Integração da Task #{task.number}: {task.title}",
        f"A revisão independente aprovou a execução {execution.id} (evidência {execution.evidence_ref}).",
        f"Integre o commit aprovado {sha} na linha principal da missão (develop) pelo fluxo git existente, "
        "sem publicar em produção. Depois rode as validações nomeadas na tarefa sobre o resultado integrado.",
        "Se houver conflito, não resolva às cegas: liste cada arquivo em linhas 'CONFLICT (content): Merge "
        "conflict in <arquivo>' e termine com STATUS: BLOCKED. Integrado e validado: termine com STATUS: DONE "
        "e a evidência git:<sha do merge>.",
    ])


async def _integrate(
    db: AsyncSession, payload: DecisionIn, principal: ActorPrincipal, mission: ProjectMission,
    task: ProjectTask, task_project_id: uuid.UUID, authorization: str | None,
) -> dict[str, Any]:
    """§3.4 item 1: an approved task finishes only integrated. Already in the
    mainline: completed through PATCH /tasks/{id} (the completion guard runs
    again and audits the principal). Not yet: the executor -- never the
    reviewer -- gets an integration Messages Task; nothing is published."""
    from app.api.routes.task import _update_task
    from app.api.schemas.task import ProjectTaskUpdate
    from app.core.mission_dispatch import task_run_in_flight
    from app.core.task_completion_guard import (
        COMPLETION_NOT_INTEGRATED,
        CompletionRefused,
        evaluate_task_completion,
        resolve_executor_agent_id,
    )

    await mt._authorize(db, principal, mission, ORCHESTRATE_ACTION, task_project_id, task.id)
    execution = await mt._execution(db, task, _require(payload.params.execution_id, "execution_id"))
    approved = await db.scalar(select(TaskExecutionReview.id).where(
        TaskExecutionReview.execution_id == execution.id, TaskExecutionReview.status == "approved").limit(1))
    if approved is None:
        raise mission_error(409, "REVIEW_NOT_APPROVED", "Only a delivery with an approved review is integrated")
    in_flight = await task_run_in_flight(db, task.id)
    if in_flight is not None:
        raise mission_error(409, "INTEGRATION_IN_FLIGHT" if (in_flight.channel_ref or "").startswith(
            INTEGRATION_REF_PREFIX) else "TASK_RUN_IN_FLIGHT", "A run of this task is in flight",
            demand_number=in_flight.number)
    try:
        await evaluate_task_completion(db, task, "done")
        integrated = True
    except CompletionRefused as exc:
        if exc.code != COMPLETION_NOT_INTEGRATED:
            raise mission_error(409, exc.code, exc.message) from exc
        integrated = False
    if integrated:
        await _update_task(task.id, ProjectTaskUpdate(status="done"), authorization, db, commit=False)
        return {"facts": {"integrated": True, "task_status": "done", "execution_id": str(execution.id)}}

    executor_id = await resolve_executor_agent_id(db, execution)
    if executor_id is None:
        raise mission_error(409, "EXECUTOR_UNKNOWN", "The execution has no resolvable executor")
    project = await db.get(Project, task_project_id)
    orchestrator = await db.get(Agent, mission.orchestrator_agent_id)
    demand = AgentDemand(
        from_agent=orchestrator.name if orchestrator else "forgehub",
        from_agent_id=orchestrator.id if orchestrator else None,
        subject=f"Integração: Task #{task.number} — {task.title}"[:255], body=_integration_body(task, execution),
        status="new", target_agent_id=executor_id, project_id=task_project_id,
        working_path=project.working_directory_path if project else None, origin_type="task", origin_id=task.id,
        channel="factory", channel_ref=f"{INTEGRATION_REF_PREFIX}{task.id}", requires_response=False,
        scheduled_at=_now(),
    )
    db.add(demand)
    await db.flush()
    return {"demand_id": demand.id, "facts": {"integrated": False, "executor_agent_id": str(executor_id),
                                              "demand_number": demand.number, "execution_id": str(execution.id)}}


async def _ask_marcelo(
    db: AsyncSession, payload: DecisionIn, mission: ProjectMission, run: AgentRoutineRun | None,
) -> dict[str, Any]:
    """§3.7: a genuine doubt goes through ask_marcelo (core/agent_questions,
    Telegram with quiet hours), carrying mission, tasks, context, options,
    recommendation, the default action and answer_by. It blocks only the
    dependent tasks (their proposals become `defer`)."""
    from app.api.routes.mission import _load as load_mission
    from app.core.agent_questions import create_question
    from app.core.mission_plan import mission_scope_tasks

    p = payload.params
    question_text = _require(p.question, "question")
    options = _require(p.options, "options")
    if len(options) < 2:
        raise mission_error(422, "OPTIONS_REQUIRED", "A question to Marcelo offers at least two options")
    recommendation = _require(p.recommendation, "recommendation")
    default_action = _require(p.default_action, "default_action")
    reversible = _require(p.default_reversible, "default_reversible")
    answer_by = _require(p.answer_by, "answer_by")
    if answer_by.tzinfo is None or answer_by <= _now():
        raise mission_error(422, "ANSWER_BY_NOT_IN_FUTURE", "answer_by must be a future, zoned time")
    scope = await mission_scope_tasks(db, mission.project_id)
    unknown = [str(t) for t in p.dependent_task_ids if t not in scope]
    if unknown:
        raise mission_error(422, "TASK_NOT_IN_MISSION", "dependent_task_ids outside the mission", task_ids=unknown)
    if p.reask_of is not None:
        original = await db.get(AgentQuestion, p.reask_of)
        if original is None or original.status != "pending" or not await db.scalar(select(MissionDecision.id).where(
                MissionDecision.mission_project_id == mission.project_id, MissionDecision.question_id == original.id)):
            raise mission_error(422, "REASK_NOT_PENDING", "reask_of must be a pending question of this mission")
    project, _ = await load_mission(db, mission.project_id)
    asker = await db.get(Agent, mission.orchestrator_agent_id)
    numbers = [f"#{scope[t].number}" for t in p.dependent_task_ids]
    context = "\n".join(filter(None, [
        f"Missão: {project.name}" + (f" · Tarefas: {', '.join(numbers)}" if numbers else ""),
        (p.context or "").strip() or None,
        "Opções:\n" + "\n".join(f"- {o}" for o in options),
        f"Se não houver resposta até {answer_by.astimezone(LOCAL_TZ):%d/%m %H:%M}: {default_action} "
        + ("(reversível)" if reversible else "(irreversível: não será aplicado sem a sua resposta)"),
    ]))
    question = await create_question(db, asker, question=question_text, context=context,
                                     recommendation=recommendation, blocking=True, urgent=p.urgent,
                                     origin_demand_id=run.demand_id if run else None)
    return {"question_id": question.id, "facts": {
        "question_number": question.number, "options": options, "recommendation": recommendation,
        "default_action": default_action, "default_reversible": reversible, "answer_by": answer_by.isoformat(),
        "dependent_task_ids": [str(t) for t in p.dependent_task_ids],
        "reask_of": str(p.reask_of) if p.reask_of else None}}


# ---------------------------------------------------------------------------
# Undo (§5)
# ---------------------------------------------------------------------------
@router.post("/{project_id}/decisions/{decision_id}:undo", response_model=DecisionOut,
             status_code=status.HTTP_201_CREATED)
async def undo_decision(
    project_id: uuid.UUID,
    decision_id: uuid.UUID,
    payload: UndoIn,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
) -> DecisionOut:
    """Applies the inverse of §3 when still possible; else 409
    UNDO_NOT_POSSIBLE with why. Marcelo only."""
    from app.api.schemas.demand import DemandDecisionIn
    from app.core.demand_workflow import WorkflowBlocked, decide_demand

    _require_admin(principal)
    _project, mission = await _load(db, project_id, lock=True)
    original = await db.get(MissionDecision, decision_id)
    if original is None or original.mission_project_id != project_id:
        raise mission_error(404, "DECISION_NOT_FOUND", "Decision not found")
    if original.status != "applied" or original.undone_by_decision_id is not None:
        raise mission_error(409, "UNDO_NOT_POSSIBLE", f"The decision is {original.status}, not an applied one")
    facts: dict[str, Any] = {"undone_decision_id": str(original.id), "undone_action": original.action}
    if original.action in ("dispatch", "schedule") and original.demand_id is not None:
        demand = await db.get(AgentDemand, original.demand_id)
        if demand is None or demand.dispatch_status is not None or demand.agent_run_id is not None:
            raise mission_error(409, "UNDO_NOT_POSSIBLE",
                                "The run already started; use the investigate/confirm_inactive path",
                                demand_number=demand.number if demand else None)
        try:
            await decide_demand(db, demand, DemandDecisionIn(action="archive", reason=f"Undo: {payload.reason}"),
                                actor=principal.display_name)
        except WorkflowBlocked as exc:
            raise mission_error(409, "UNDO_NOT_POSSIBLE", str(exc.detail)) from exc
        if demand.task_execution_id is not None:
            execution = await db.get(TaskExecution, demand.task_execution_id)
            if execution is not None and execution.status == "pending":
                execution.status = "failed"
                execution.outcome_summary = f"Withdrawn before start: {payload.reason}"
        facts["archived_demand_number"] = demand.number
    elif original.action == "reassign" and (original.facts or {}).get("previous_agent_id"):
        task = await db.get(ProjectTask, original.task_id)
        await mt._assign_task(project_id, task.id, TaskAssignIn(
            agent_id=uuid.UUID(original.facts["previous_agent_id"]), reason=f"Undo: {payload.reason}",
            idempotency_key=f"undo:{original.id}"), principal, db)
        facts["reassigned_back_to"] = original.facts["previous_agent_id"]
    else:
        raise mission_error(409, "UNDO_NOT_POSSIBLE", f"No inverse for a {original.action} decision in M0",
                            action=original.action)
    original = await db.get(MissionDecision, decision_id, populate_existing=True)
    undo = MissionDecision(
        mission_project_id=project_id, action="undo", task_id=original.task_id, demand_id=original.demand_id,
        reason=payload.reason.strip(), facts=facts, autonomy_level="N0", actor_type="user",
        actor_id=principal.principal_id, actor_name=principal.display_name, authority_source="admin",
        status="applied", idempotency_key=f"undo:{original.id}",
    )
    db.add(undo)
    await db.flush()
    original.status, original.undone_by_decision_id = "undone", undo.id
    db.add(AuditEvent(entity_type="mission", entity_id=project_id, event_type="mission_decision_undo",
                      actor=principal.display_name,
                      payload={"decision_id": str(undo.id), "undone_decision_id": str(original.id),
                               "reason": undo.reason}))
    await db.commit()
    await db.refresh(undo)
    return _decision_out(undo)


# ---------------------------------------------------------------------------
# Locks (§5)
# ---------------------------------------------------------------------------
async def _lock(db: AsyncSession, principal: ActorPrincipal, project_id: uuid.UUID, task_id: uuid.UUID | None,
                payload: CycleLockIn) -> MissionCycleLock:
    _require_admin(principal)
    _project, mission = await _load(db, project_id, lock=True)
    if task_id is not None:
        await mt._scope_task(db, mission, task_id)
    if payload.until is not None and (payload.until.tzinfo is None or payload.until <= _now()):
        raise mission_error(422, "UNTIL_NOT_IN_FUTURE", "until must be a future, zoned time")
    existing = next((lock for lock in await open_locks(db, project_id) if lock.task_id == task_id), None)
    if existing is not None:
        raise mission_error(409, "ALREADY_LOCKED", "This lock is already in place", lock_id=str(existing.id))
    lock = MissionCycleLock(mission_project_id=project_id, task_id=task_id, locked_by=principal.display_name,
                            reason=payload.reason.strip(), locked_until=payload.until)
    db.add(lock)
    await db.flush()
    db.add(MissionDecision(
        mission_project_id=project_id, action="lock", task_id=task_id, reason=lock.reason,
        facts={"lock_id": str(lock.id), "until": payload.until.isoformat() if payload.until else None},
        autonomy_level="N0", actor_type="user", actor_id=principal.principal_id, actor_name=principal.display_name,
        authority_source="admin", status="applied", idempotency_key=f"lock:{lock.id}",
    ))
    db.add(AuditEvent(entity_type="mission", entity_id=project_id, event_type="mission_cycle_locked",
                      actor=principal.display_name,
                      payload={"lock_id": str(lock.id), "task_id": str(task_id) if task_id else None,
                               "reason": lock.reason}))
    await db.commit()
    await db.refresh(lock)
    return lock


async def _unlock(db: AsyncSession, principal: ActorPrincipal, project_id: uuid.UUID, task_id: uuid.UUID | None,
                  payload: CycleUnlockIn) -> MissionCycleLock:
    _require_admin(principal)
    await _load(db, project_id, lock=True)
    lock = next((lock for lock in await open_locks(db, project_id) if lock.task_id == task_id), None)
    if lock is None:
        raise mission_error(404, "LOCK_NOT_FOUND", "No open lock here")
    lock.released_at, lock.released_by = _now(), principal.display_name
    db.add(MissionDecision(
        mission_project_id=project_id, action="unlock", task_id=task_id, reason=payload.reason.strip(),
        facts={"lock_id": str(lock.id)}, autonomy_level="N0", actor_type="user", actor_id=principal.principal_id,
        actor_name=principal.display_name, authority_source="admin", status="applied",
        idempotency_key=f"unlock:{lock.id}",
    ))
    db.add(AuditEvent(entity_type="mission", entity_id=project_id, event_type="mission_cycle_unlocked",
                      actor=principal.display_name, payload={"lock_id": str(lock.id), "reason": payload.reason}))
    await db.commit()
    await db.refresh(lock)
    return lock


@router.post("/{project_id}/cycle:lock", response_model=CycleLockOut, status_code=status.HTTP_201_CREATED)
async def lock_cycle(project_id: uuid.UUID, payload: CycleLockIn,
                     principal: ActorPrincipal = Depends(get_actor_principal), db: AsyncSession = Depends(get_db)):
    return await _lock(db, principal, project_id, None, payload)


@router.post("/{project_id}/cycle:unlock", response_model=CycleLockOut)
async def unlock_cycle(project_id: uuid.UUID, payload: CycleUnlockIn,
                       principal: ActorPrincipal = Depends(get_actor_principal), db: AsyncSession = Depends(get_db)):
    return await _unlock(db, principal, project_id, None, payload)


@router.post("/{project_id}/tasks/{task_id}:lock-cycle", response_model=CycleLockOut,
             status_code=status.HTTP_201_CREATED)
async def lock_task_cycle(project_id: uuid.UUID, task_id: uuid.UUID, payload: CycleLockIn,
                          principal: ActorPrincipal = Depends(get_actor_principal), db: AsyncSession = Depends(get_db)):
    return await _lock(db, principal, project_id, task_id, payload)


@router.post("/{project_id}/tasks/{task_id}:unlock-cycle", response_model=CycleLockOut)
async def unlock_task_cycle(project_id: uuid.UUID, task_id: uuid.UUID, payload: CycleUnlockIn,
                            principal: ActorPrincipal = Depends(get_actor_principal),
                            db: AsyncSession = Depends(get_db)):
    return await _unlock(db, principal, project_id, task_id, payload)


# ---------------------------------------------------------------------------
# propose_skill_change (§3.6, MCP spec §6.1)
# ---------------------------------------------------------------------------
@router.post("/{project_id}/skill-proposals", response_model=SkillProposalOut, status_code=status.HTTP_201_CREATED,
             dependencies=COMMAND_DEPENDENCIES)
async def propose_skill_change(
    project_id: uuid.UUID,
    payload: SkillProposalIn,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
):
    """Records a proposal and hands it to the skill's canonical owner (Athos
    for shared/Foundation skills) as an Incubation message, which never runs by
    itself. Never touches agent_skills: granting or creating stays with the
    owner and its approval. The task it blocks gets a `defer` decision with
    reason `skill_gap`."""
    from app.api.routes.operations import COORDINATOR_SLUG
    from app.db.models.agent import Skill

    enforce_command_limits(principal)
    _project, mission = await _load(db, project_id)
    source, delegation = await _authorize_cycle(db, principal, mission)
    command = "mission.propose_skill"
    body_hash = request_hash(command, {"project_id": str(project_id), **payload.model_dump(mode="json")})
    receipt = await begin_command(db, principal, payload.idempotency_key, command, body_hash)
    if receipt is not None:
        return receipt
    key = f"skill:{payload.idempotency_key}"
    replay = (await db.execute(select(MissionDecision).where(
        MissionDecision.actor_type == principal.principal_type, MissionDecision.actor_id == principal.principal_id,
        MissionDecision.idempotency_key == key))).scalar_one_or_none()
    if replay is not None:
        if replay.facts.get("request_hash") != body_hash or replay.mission_project_id != project_id:
            raise mission_error(409, "IDEMPOTENCY_KEY_REUSED", "The original skill proposal payload differs or requires reconciliation")
        proposal = await db.get(MissionSkillProposal, uuid.UUID(replay.facts["skill_proposal_id"]))
        audit = await db.scalar(select(AuditEvent).where(
            AuditEvent.entity_type == "mission_skill_proposal", AuditEvent.entity_id == proposal.id,
            AuditEvent.event_type == "learning_evidence_qualified"))
        out = SkillProposalOut.model_validate(proposal)
        out.learning = audit.payload if audit else None
        return JSONResponse(status_code=200, content=out.model_dump(mode="json"),
                            headers={"Idempotent-Replay": "true"})
    await assert_cycle_unlocked(db, mission, principal, payload.task_id)
    task = None
    if payload.task_id is not None:
        task, _ = await mt._scope_task(db, mission, payload.task_id)
    if payload.kind in ("assign_other_agent", "grant_to_agent") and payload.skill_id is None:
        raise mission_error(422, "SKILL_REQUIRED", "This kind of proposal names an existing skill")
    if payload.skill_id is not None and await db.get(Skill, payload.skill_id) is None:
        raise mission_error(422, "SKILL_NOT_FOUND", "skill_id is not a registered skill")
    learning = None
    if payload.learning is not None:
        from app.core.mission_learning import validate_learning
        learning = await validate_learning(db, mission, payload.learning)
    run = await _cycle_run(db, mission, payload.cycle_id)
    owner = (await db.execute(select(Agent).where(Agent.profile_slug == COORDINATOR_SLUG))).scalar_one_or_none()
    orchestrator = await db.get(Agent, mission.orchestrator_agent_id)
    proposal = MissionSkillProposal(
        mission_project_id=project_id, task_id=task.id if task else None, kind=payload.kind,
        skill_id=payload.skill_id, agent_id=payload.agent_id, owner_agent_id=owner.id if owner else None,
        reason=payload.reason.strip(), proposed_by=principal.display_name,
    )
    db.add(proposal)
    await db.flush()
    if owner is not None and orchestrator is not None:
        demand = AgentDemand(
            from_agent=orchestrator.name, from_agent_id=orchestrator.id, target_agent_id=owner.id,
            subject=f"Proposta de skill ({payload.kind}) — missão {_project.name}"[:255],
            body="\n\n".join([
                f"Proposta {proposal.id} registrada pelo ciclo da missão {_project.name}.",
                f"Tipo: {payload.kind}. Skill: {payload.skill_id or '(nova)'}. Agente: {payload.agent_id or '-'}."
                + (f" Tarefa: #{task.number}." if task else ""),
                f"Motivo: {proposal.reason}",
                (f"Aprendizado qualificado: {learning}" if learning else "Observação/proposta sem aprendizado qualificado."),
                "Decida como dono da skill (com backup e revisão); o ciclo não concede nem instala skills.",
            ]),
            origin_type="incubation", project_id=project_id,
        )
        db.add(demand)
        await db.flush()
        proposal.demand_id = demand.id
    db.add(MissionDecision(
        mission_project_id=project_id, cycle_id=run.id if run else None, action="defer",
        task_id=task.id if task else None, reason=f"skill_gap: {proposal.reason}"[:2000],
        facts={"skill_proposal_id": str(proposal.id), "kind": payload.kind, "request_hash": body_hash,
               "skill_id": str(payload.skill_id) if payload.skill_id else None},
        autonomy_level=mission.autonomy_level, actor_type=principal.principal_type, actor_id=principal.principal_id,
        actor_name=principal.display_name, authority_source=source,
        delegation_id=delegation.id if delegation is not None else None, status="deferred", idempotency_key=key,
    ))
    db.add(AuditEvent(entity_type="mission", entity_id=project_id, event_type="mission_skill_proposed",
                      actor=principal.display_name,
                      payload={"skill_proposal_id": str(proposal.id), "kind": payload.kind,
                               "reason": proposal.reason}))
    if learning is not None:
        db.add(AuditEvent(entity_type="mission_skill_proposal", entity_id=proposal.id,
                          event_type="learning_evidence_qualified", actor=principal.display_name, payload=learning))
    out = SkillProposalOut.model_validate(proposal)
    out.learning = learning
    record_command(db, principal, payload.idempotency_key, command, body_hash, 201, out,
                   target_type="mission_skill_proposal", target_id=proposal.id)
    await db.commit()
    await db.refresh(proposal)
    return out


# ---------------------------------------------------------------------------
# Dependencies between missions (§6.3)
# ---------------------------------------------------------------------------
@router.post("/{project_id}/dependencies", response_model=MissionDependencyOut, status_code=status.HTTP_201_CREATED)
async def add_mission_dependency(
    project_id: uuid.UUID,
    payload: MissionDependencyIn,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
) -> MissionDependency:
    """Marcelo registers that this mission starts only after another completes,
    while it is still draft/ready. A cycle is refused (MISSION_DEPENDENCY_CYCLE)."""
    _require_admin(principal)
    await db.execute(select(func.pg_advisory_xact_lock(func.hashtext("mission-dependencies"))))
    _project, mission = await _load(db, project_id, lock=True)
    if mission.state not in ("draft", "planning", "ready"):
        raise mission_error(409, "MISSION_ALREADY_STARTED", "Dependencies are declared before the mission starts")
    other = await db.get(ProjectMission, payload.depends_on_mission_project_id)
    if other is None:
        raise mission_error(404, "MISSION_NOT_FOUND", "The mission it depends on does not exist")
    if other.project_id == project_id:
        raise mission_error(422, "MISSION_DEPENDENCY_SELF", "A mission does not depend on itself")
    edges = (await db.execute(select(MissionDependency.mission_project_id,
                                     MissionDependency.depends_on_mission_project_id))).all()
    graph: dict[uuid.UUID, set[uuid.UUID]] = {}
    for source_id, target_id in edges:
        graph.setdefault(source_id, set()).add(target_id)
    stack, seen = [other.project_id], set()
    while stack:
        node = stack.pop()
        if node == project_id:
            raise mission_error(409, "MISSION_DEPENDENCY_CYCLE", "This dependency would create a cycle")
        if node not in seen:
            seen.add(node)
            stack.extend(graph.get(node, ()))
    if any(s == project_id and t == other.project_id for s, t in edges):
        raise mission_error(409, "MISSION_DEPENDENCY_EXISTS", "This dependency already exists")
    row = MissionDependency(mission_project_id=project_id, depends_on_mission_project_id=other.project_id,
                            created_by=principal.display_name)
    db.add(row)
    await db.flush()
    db.add(AuditEvent(entity_type="mission", entity_id=project_id, event_type="mission_dependency_added",
                      actor=principal.display_name,
                      payload={"dependency_id": str(row.id), "depends_on": str(other.project_id),
                               "reason": payload.reason}))
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/{project_id}/dependencies/{dependency_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_mission_dependency(
    project_id: uuid.UUID,
    dependency_id: uuid.UUID,
    reason: str,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
) -> None:
    _require_admin(principal)
    row = await db.get(MissionDependency, dependency_id)
    if row is None or row.mission_project_id != project_id:
        raise mission_error(404, "DEPENDENCY_NOT_FOUND", "Dependency not found")
    if not reason.strip():
        raise mission_error(422, "REASON_REQUIRED", "Removing a dependency requires a reason")
    db.add(AuditEvent(entity_type="mission", entity_id=project_id, event_type="mission_dependency_removed",
                      actor=principal.display_name,
                      payload={"dependency_id": str(row.id), "depends_on": str(row.depends_on_mission_project_id),
                               "reason": reason}))
    await db.delete(row)
    await db.commit()

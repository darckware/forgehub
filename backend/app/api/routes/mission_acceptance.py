"""Criterion verification and governed final mission acceptance."""
import uuid
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from app.api.routes.mission import _audit_payload, _load
from app.api.routes.mission_records import _authorize_manager, _membership
from app.core.command_receipts import begin_command, enforce_command_limits, limit_command_body, record_command, request_hash
from app.core.deps import ActorPrincipal, get_actor_principal
from app.core.mission import _criteria, _criterion_task_ids, mission_error, utcnow
from app.core.mission_acceptance import assert_criterion_evidence, open_acceptance
from app.core.mission_plan import mission_scope_tasks
from app.core.task_completion_guard import assert_task_completion_allowed, resolve_executor_agent_id
from app.db.base import get_db
from app.db.models.governance import AuditEvent
from app.db.models.mission import MissionAcceptanceCriterion, MissionCriterionTask
from app.db.models.task import TaskExecution

router = APIRouter(prefix="/api/v1/missions", tags=["missions"], dependencies=[Depends(limit_command_body)])


class AcceptanceRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=1, max_length=150)


class CriterionDecisionIn(AcceptanceRequestIn):
    status: Literal["proven", "failed"]
    evidence_ref: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=1, max_length=4000)


class CriterionCreateIn(AcceptanceRequestIn):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: str = Field(min_length=1, max_length=20)
    statement: str = Field(min_length=1, max_length=12000)
    verification_method: str = Field(min_length=1, max_length=4000)
    verifier_agent_id: uuid.UUID | None = None
    verifier_is_marcelo: bool = False
    task_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def exactly_one_verifier_and_unique_tasks(self):
        if (self.verifier_agent_id is not None) == self.verifier_is_marcelo:
            raise ValueError("Choose exactly one verifier: an eligible agent or Marcelo")
        if len(set(self.task_ids)) != len(self.task_ids):
            raise ValueError("task_ids must not contain duplicates")
        return self


@router.get("/{project_id}/criteria")
async def list_criteria(project_id: uuid.UUID, principal: ActorPrincipal = Depends(get_actor_principal),
                        db=Depends(get_db)):
    _, mission = await _load(db, project_id)
    if principal.principal_type == "user":
        if not principal.is_admin:
            raise mission_error(403, "MISSION_ADMIN_ONLY", "Only an administrator can read mission criteria in M0")
    elif principal.principal_type == "agent":
        if principal.principal_id != mission.orchestrator_agent_id and await _membership(
            db, project_id, principal.principal_id
        ) is None:
            raise mission_error(404, "MISSION_NOT_FOUND", "Mission not found")
    else:
        raise mission_error(404, "MISSION_NOT_FOUND", "Mission not found")
    criteria = await _criteria(db, project_id)
    task_ids = await _criterion_task_ids(db, [criterion.id for criterion in criteria])
    return [{
        "id": str(criterion.id), "code": criterion.code, "statement": criterion.statement,
        "verification_method": criterion.verification_method, "status": criterion.status,
        "verifier_agent_id": str(criterion.verifier_agent_id) if criterion.verifier_agent_id else None,
        "verifier_is_marcelo": criterion.verifier_is_marcelo, "evidence_ref": criterion.evidence_ref,
        "task_ids": sorted(str(task_id) for task_id in task_ids[criterion.id]),
    } for criterion in criteria]


@router.post("/{project_id}/criteria", status_code=201)
async def create_criterion(project_id: uuid.UUID, payload: CriterionCreateIn,
    principal: ActorPrincipal = Depends(get_actor_principal), db=Depends(get_db)):
    """Register one objective acceptance criterion before the mission baseline."""
    enforce_command_limits(principal)
    _, mission = await _load(db, project_id, lock=True)
    source, delegation = await _authorize_manager(db, principal, mission, None)
    command = "mission.create_criterion"
    digest = request_hash(command, {"project_id": project_id, **payload.model_dump()})
    replay = await begin_command(db, principal, payload.idempotency_key, command, digest)
    if replay is not None:
        return replay
    if mission.state not in ("draft", "planning") or mission.current_baseline_id is not None:
        raise mission_error(409, "CRITERIA_LOCKED", "Acceptance criteria are immutable after a baseline exists")

    existing = await db.scalar(select(MissionAcceptanceCriterion.id).where(
        MissionAcceptanceCriterion.mission_project_id == project_id,
        MissionAcceptanceCriterion.code == payload.code,
    ))
    if existing is not None:
        raise mission_error(409, "CRITERION_CODE_EXISTS", "Criterion code already exists in this mission",
                            code=payload.code)
    if payload.verifier_agent_id is not None:
        if await _membership(db, project_id, payload.verifier_agent_id, can_review=True) is None:
            raise mission_error(422, "CRITERION_VERIFIER_NOT_ELIGIBLE",
                                "The criterion verifier must be an active mission reviewer")
    scope = await mission_scope_tasks(db, project_id)
    outside_scope = [task_id for task_id in payload.task_ids if task_id not in scope]
    if outside_scope:
        raise mission_error(422, "CRITERION_TASKS_OUT_OF_SCOPE",
                            "Every criterion task must belong to this mission or a linked executor project",
                            task_ids=[str(task_id) for task_id in outside_scope])

    criterion = MissionAcceptanceCriterion(
        mission_project_id=project_id,
        code=payload.code,
        statement=payload.statement,
        verification_method=payload.verification_method,
        verifier_agent_id=payload.verifier_agent_id,
        verifier_is_marcelo=payload.verifier_is_marcelo,
        status="open",
    )
    db.add(criterion)
    await db.flush()
    for task_id in payload.task_ids:
        db.add(MissionCriterionTask(criterion_id=criterion.id, task_id=task_id))
    mission.row_version += 1
    out = {"id": str(criterion.id), "code": criterion.code, "status": criterion.status,
           "verifier_agent_id": str(criterion.verifier_agent_id) if criterion.verifier_agent_id else None,
           "verifier_is_marcelo": criterion.verifier_is_marcelo,
           "task_ids": [str(task_id) for task_id in payload.task_ids]}
    db.add(AuditEvent(entity_type="mission", entity_id=project_id, event_type="mission_criterion_created",
        actor=principal.display_name,
        payload={**_audit_payload(principal, source, delegation),
                 "criterion_id": str(criterion.id), "code": criterion.code,
                 "task_ids": out["task_ids"], "verifier_agent_id": out["verifier_agent_id"],
                 "verifier_is_marcelo": criterion.verifier_is_marcelo}))
    record_command(db, principal, payload.idempotency_key, command, digest, 201, out,
                   target_type="mission", target_id=project_id)
    await db.commit()
    return out


@router.post("/{project_id}/acceptance:request", status_code=201)
async def request_acceptance(project_id: uuid.UUID, payload: AcceptanceRequestIn,
    principal: ActorPrincipal = Depends(get_actor_principal), db=Depends(get_db)):
    enforce_command_limits(principal)
    _, mission = await _load(db, project_id, lock=True)
    await _authorize_manager(db, principal, mission, None)
    command = "mission.request_acceptance"
    digest = request_hash(command, {"project_id": project_id, **payload.model_dump()})
    replay = await begin_command(db, principal, payload.idempotency_key, command, digest)
    if replay is not None:
        return replay
    request = await open_acceptance(db, principal, mission)
    out = {"approval_request_id": str(request.id), "target_hash": request.target_hash, "status": request.status}
    record_command(db, principal, payload.idempotency_key, command, digest, 201, out,
                   target_type="mission", target_id=project_id)
    await db.commit()
    return out


@router.post("/{project_id}/criteria/{criterion_id}:decide")
async def decide_criterion(project_id: uuid.UUID, criterion_id: uuid.UUID, payload: CriterionDecisionIn,
    principal: ActorPrincipal = Depends(get_actor_principal), db=Depends(get_db)):
    enforce_command_limits(principal)
    _, mission = await _load(db, project_id, lock=True)
    criterion = await db.get(MissionAcceptanceCriterion, criterion_id)
    if criterion is None or criterion.mission_project_id != project_id:
        raise mission_error(404, "CRITERION_NOT_FOUND", "Criterion not found in this mission")
    human = principal.principal_type == "user" and principal.is_admin
    if not human and not (principal.principal_type == "agent" and criterion.verifier_agent_id == principal.principal_id
                          and await _membership(db, project_id, principal.principal_id, can_review=True)):
        raise mission_error(403, "CRITERION_VERIFIER_REQUIRED", "Only the assigned verifier or an administrator may decide")
    command = "mission.decide_criterion"
    digest = request_hash(command, {"project_id": project_id, "criterion_id": criterion_id, **payload.model_dump()})
    replay = await begin_command(db, principal, payload.idempotency_key, command, digest)
    if replay is not None:
        return replay
    if mission.state not in ("active", "verifying"):
        raise mission_error(409, "CRITERION_DECISION_STATE_INVALID", "Criteria are verified during active delivery or verification")
    if not payload.reason.strip() or not payload.evidence_ref.strip():
        raise mission_error(422, "EVIDENCE_REQUIRED", "Verification needs evidence and a reason")
    linked = (await _criterion_task_ids(db, [criterion.id]))[criterion.id]
    tasks = await mission_scope_tasks(db, project_id)
    if not linked or any(tid not in tasks for tid in linked):
        raise mission_error(409, "CRITERION_TASK_SCOPE_INVALID", "Criterion tasks must belong to the mission")
    from app.core.task_baseline_guard import assert_task_baseline_matches, lock_writable_delivery_task
    for tid in sorted(linked, key=str):
        task = await lock_writable_delivery_task(db, tid)
        if task is None:
            raise mission_error(409, "CRITERION_TASK_SCOPE_INVALID", "A linked task disappeared")
        latest = await db.scalar(select(TaskExecution).where(TaskExecution.task_id == tid)
                                 .order_by(TaskExecution.attempt_number.desc()).limit(1))
        if not human and latest and await resolve_executor_agent_id(db, latest) == principal.principal_id:
            raise mission_error(409, "VERIFIER_IS_EXECUTOR", "The criterion verifier cannot be its task executor")
        if payload.status == "proven":
            if task.status not in ("done", "deployed"):
                raise mission_error(409, "CRITERION_TASK_NOT_ACCEPTED", "Linked tasks must be accepted before proving the criterion")
            await assert_task_baseline_matches(db, task, mission)
            await assert_task_completion_allowed(db, task, "done")
    if payload.status == "proven":
        await assert_criterion_evidence(db, [tasks[tid] for tid in sorted(linked, key=str)], payload.evidence_ref.strip())
    criterion.status, criterion.evidence_ref = payload.status, payload.evidence_ref.strip()
    criterion.decided_by, criterion.decided_at = principal.display_name, utcnow()
    mission.row_version += 1
    out = {"id": str(criterion.id), "status": criterion.status, "evidence_ref": criterion.evidence_ref}
    db.add(AuditEvent(entity_type="mission", entity_id=project_id, event_type="mission_criterion_decided",
        actor=principal.display_name, payload={**out, "reason": payload.reason, "principal_id": str(principal.principal_id)}))
    record_command(db, principal, payload.idempotency_key, command, digest, 200, out,
                   target_type="mission", target_id=project_id)
    await db.commit()
    return out

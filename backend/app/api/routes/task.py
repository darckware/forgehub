"""Task domain routes.

Primary entity: ProjectTask (with nested TaskExecution sub-resource).
Secondary tables: TaskDependency, TaskRequiredSkill, TaskAssignment get
create/list (+ delete where cheap) endpoints.

Business rules encoded here (see docs/SPEC.md section 6.4 Execution Rules
and 6.2 used as a pattern for dependency-style blocking):
- 6.4.1 Planned/assigned/executed remain distinct states: creating a
  TaskAssignment moves the task status from "planned" to "assigned";
  creating a TaskExecution moves it to "in_progress"; it never silently
  jumps to "done". Since M0.6a (Plano Integrado, 2026-10-29) every new
  transition to "done"/"deployed" -- here and in every other writer --
  goes through core/task_completion_guard.py: verified latest execution,
  evidence that checks out, an independent approved review, dependencies
  and subtasks done. A task with no execution can no longer be completed
  (prospective: tasks already done stay done).
- 6.4.2 Each task can have multiple executions -- enforced naturally by
  allowing repeated POSTs to the executions sub-resource; attempt_number
  auto-increments per task.
- 6.4.3 Every execution must have evidence -- enforced in the Pydantic
  schema (evidence_ref required once status is verified/completed) and
  re-checked here for partial updates.
- Dependency cycle/self-reference guard: a task cannot depend on itself
  (schema-level); direct and indirect cycles are rejected here.
- A task cannot start or complete while it has an incomplete dependency;
  all predecessors must be "done" or "deployed"
  (mirrors SPEC 6.2.9 "blocked stages must prevent dependent stages from
  advancing", applied at task granularity).
- A task cannot be marked "done" while any of its own subtasks
  (`parent_task_id`) hasn't reached "done"/"deployed" -- the fan-out half
  of layered task-execution governance (2026-08-17): an area breaks a task
  into subtasks via the same self-FK, dispatches each individually, and
  the parent can't complete until all of them have (the completion guard's
  COMPLETION_SUBTASKS_OPEN).
- A task must trace back to the planning item it was split from
  (core traceability invariant, CLAUDE.md / SPEC 5.4) -- planning_item_id
  is required on create and must reference an existing PlanningItem.
- 6.4.4 Every task completion must be auditable: marking a task "done" or
  a TaskExecution "verified"/"completed" writes a companion AuditEvent
  (governance domain) so the transition is part of the audit trail.
"""
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.task_baseline_guard import assert_task_baseline_current
from app.api.schemas.task import (
    ResponsibilityAreaCreate,
    ResponsibilityAreaOut,
    ResponsibilityAreaUpdate,
    TaskAssignmentCreate,
    TaskAssignmentOut,
    TaskDependencyAddedOut,
    TaskDependencyCreate,
    TaskDependencyOut,
    TaskExecutionCreate,
    TaskExecutionOut,
    TaskExecutionUpdate,
    TaskRequiredSkillCreate,
    TaskRequiredSkillOut,
    ProjectTaskCreate,
    ProjectTaskOut,
    ProjectTaskUpdate,
    TaskInboxDispatchIn,
    TaskInboxDispatchOut,
    TaskSubmitIn,
)
from app.core.config import settings
from app.core.deps import ActorPrincipal, authorize_action, get_actor_principal
from app.core.mission import (
    assert_required_skills_writable,
    assert_task_environment_writable,
    project_id_for_task_source,
)
from app.core.command_receipts import (
    begin_command,
    enforce_command_limits,
    limit_command_body,
    record_command,
    request_hash,
    require_mission_tools,
)
from app.core.responsibility import resolve_responsibility_owner
from app.core.task_skills import attach_required_skill_ids, replace_required_skills, required_skill_map
from app.api.schemas.mission import TaskReportIn, TaskReportOut
from app.core.task_completion_guard import (
    COMPLETION_TARGET_STATUSES,
    assert_task_completion_allowed,
    completion_audit_event,
    principal_from_authorization,
    resolve_executor_agent_id,
)
from app.core.task_dependencies import ensure_task_dependencies_satisfied
from app.db.base import get_db
from app.db.models.agent import Agent, AgentServiceCredential, SubAgent
from app.db.models.backlog import PLANNING_ITEM_TYPES, PlanningItem
from app.db.models.demand import AgentDemand
from app.db.models.governance import ApprovalRequest, AuditEvent
from app.db.models.notification import Notification
from app.db.models.progress import ProgressCheckpoint
from app.db.models.orchestration import AgentRuntimeProfile, ProjectAgentMembership, ProjectLoopPolicy
from app.db.models.project import ChangeRequest, Project
from app.db.models.task import (
    ProjectTask,
    ResponsibilityArea,
    TaskAssignment,
    TaskDependency,
    TaskExecution,
    TaskRequiredSkill,
)

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])

# Standalone resource (not nested under a task) -- a ResponsibilityArea maps
# a task_type (optionally scoped to a project) to a default owner agent, see
# db/models/task.py's ResponsibilityArea docstring. Registered separately in
# main.py alongside `router` (same pattern module, two prefixes).
responsibility_router = APIRouter(prefix="/api/v1/responsibility-areas", tags=["responsibility-areas"])


async def _get_task_or_404(db: AsyncSession, task_id: uuid.UUID) -> ProjectTask:
    task = await db.get(ProjectTask, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


async def _authorize_agent_task_update(
    db: AsyncSession,
    task: ProjectTask,
    authorization: str | None,
) -> None:
    """Apply delegated authority only to agt_ callers.

    Human/JWT behavior remains owned by the existing application permission
    boundary. Agent credentials are denied unless explicitly delegated
    ``planning.execution.manage`` for the task's Project.
    """
    if not authorization or not authorization.lower().startswith("bearer agt_"):
        return
    token = authorization[7:]
    credential = (
        await db.execute(
            select(AgentServiceCredential).where(
                AgentServiceCredential.token_hash == hashlib.sha256(token.encode()).hexdigest(),
                AgentServiceCredential.revoked_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if credential is None:
        raise HTTPException(401, "Invalid or expired agent credential")
    agent = await db.get(Agent, credential.agent_id)
    if agent is None or not agent.is_active or agent.status != "active":
        raise HTTPException(403, "Agent principal is inactive")
    project_id: uuid.UUID | None = None
    if task.planning_item_id is not None:
        planning_item = await db.get(PlanningItem, task.planning_item_id)
        project_id = planning_item.project_id if planning_item else None
    elif task.change_request_id is not None:
        change_request = await db.get(ChangeRequest, task.change_request_id)
        project_id = change_request.project_id if change_request else None
    if project_id is None:
        raise HTTPException(409, "Task cannot be resolved to a project")
    await authorize_action(
        db,
        ActorPrincipal("agent", agent.id, agent.name),
        "planning.execution.manage",
        project_id=project_id,
    )


async def _resolve_task_project_id(db: AsyncSession, task: ProjectTask) -> uuid.UUID:
    if task.planning_item_id:
        planning_item = await db.get(PlanningItem, task.planning_item_id)
        if planning_item and planning_item.project_id:
            return planning_item.project_id
    if task.change_request_id:
        change_request = await db.get(ChangeRequest, task.change_request_id)
        if change_request:
            return change_request.project_id
    raise HTTPException(status_code=409, detail="Task cannot be resolved to a project")


async def _attach_project_ids(db: AsyncSession, tasks: list[ProjectTask]) -> None:
    """Populates the transient `project_id` attribute ProjectTaskOut reads
    (see its docstring) on every task in `tasks`, batched into two IN
    queries instead of N+N round-trips. Read-only/output use only -- unlike
    `_resolve_task_project_id`, this never raises: a task that somehow
    doesn't resolve just gets `project_id=None` rather than failing the
    whole list response."""
    planning_item_ids = {t.planning_item_id for t in tasks if t.planning_item_id}
    change_request_ids = {t.change_request_id for t in tasks if t.change_request_id}
    planning_project_map: dict[uuid.UUID, uuid.UUID] = {}
    if planning_item_ids:
        rows = (
            await db.execute(
                select(PlanningItem.id, PlanningItem.project_id).where(
                    PlanningItem.id.in_(planning_item_ids)
                )
            )
        ).all()
        planning_project_map = {row.id: row.project_id for row in rows}
    change_request_project_map: dict[uuid.UUID, uuid.UUID] = {}
    if change_request_ids:
        rows = (
            await db.execute(
                select(ChangeRequest.id, ChangeRequest.project_id).where(
                    ChangeRequest.id.in_(change_request_ids)
                )
            )
        ).all()
        change_request_project_map = {row.id: row.project_id for row in rows}
    for task in tasks:
        project_id = None
        if task.planning_item_id:
            project_id = planning_project_map.get(task.planning_item_id)
        if project_id is None and task.change_request_id:
            project_id = change_request_project_map.get(task.change_request_id)
        task.project_id = project_id


async def _attach_task_health(db: AsyncSession, tasks: list[ProjectTask]) -> None:
    """Populates the transient `health` attribute ProjectTaskOut reads --
    see core/task_health.py's module docstring for what "overdue"/
    "stalled"/"failed" mean. Same batched, read-only, never-raises
    discipline as _attach_project_ids above."""
    from app.core.task_health import compute_health_map

    health_map = await compute_health_map(db, tasks)
    for task in tasks:
        task.health = health_map.get(task.id, "ok")


async def _record_execution_lifecycle_checkpoint(
    db: AsyncSession,
    task: ProjectTask,
    execution: TaskExecution,
    checkpoint_type: str,
    step_key: str,
    step_label: str,
) -> None:
    """Persist adapter-independent lifecycle recovery facts with the execution transaction."""
    idempotency_key = f"execution:{execution.id}:{checkpoint_type}"
    exists = (await db.execute(select(ProgressCheckpoint.id).where(
        ProgressCheckpoint.idempotency_key == idempotency_key
    ))).scalar_one_or_none()
    if exists:
        return
    sequence = int((await db.execute(select(func.coalesce(func.max(ProgressCheckpoint.sequence), 0)).where(
        ProgressCheckpoint.task_execution_id == execution.id
    ))).scalar_one()) + 1
    evidence = [execution.evidence_ref] if execution.evidence_ref else []
    db.add(ProgressCheckpoint(
        project_id=await _resolve_task_project_id(db, task), task_id=task.id,
        task_execution_id=execution.id, sequence=sequence,
        checkpoint_type=checkpoint_type, step_key=step_key, step_label=step_label,
        state_snapshot={"status": execution.status, "attempt_number": execution.attempt_number},
        completed_requirement_keys=[], evidence_refs=evidence,
        last_confirmed_at=datetime.now(timezone.utc),
        resume_from_step_key=step_key if checkpoint_type in {"started", "failed"} else None,
        error_code="execution_failed" if checkpoint_type == "failed" else None,
        message=execution.outcome_summary, actor_type="system", actor_id=None,
        actor_name="ForgeHub runtime", idempotency_key=idempotency_key,
    ))
    # The create route may add both started and terminal checkpoints in one
    # transaction. Flush so the next sequence query observes this row.
    await db.flush()
    if checkpoint_type == "failed":
        # Unlike progress.py's own checkpoint routes (which call
        # _notify_checkpoint), this helper used to leave a failed execution
        # silent -- the ProgressCheckpoint row above existed, but nothing
        # ever told a human. event_key ties to this same idempotency_key so
        # a retried/duplicate call never double-notifies.
        db.add(Notification(
            source="system", severity="warning",
            title=f"Task execution failed: {task.title}",
            message=execution.outcome_summary or f"Task #{task.number}, attempt {execution.attempt_number} failed.",
            event_key=f"task-execution-failed:{idempotency_key}",
            occurred_at=datetime.now(timezone.utc),
        ))


# --------------------------------------------------------------------------
# ProjectTask CRUD
# --------------------------------------------------------------------------


@router.post("/submit", response_model=ProjectTaskOut, status_code=status.HTTP_201_CREATED)
async def submit_task(
    payload: TaskSubmitIn,
    x_bridge_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> ProjectTask:
    """Public path (see main.py's _PUBLIC_API_PATHS) guarded by the shared
    bridge token -- same trust boundary as demand.py's /submit, so any
    Hermes agent on the host can log a task with a plain curl (no user JWT
    available to a cron/agent). See TaskSubmitIn's docstring for why this
    creates a PlanningItem alongside the task rather than a bare task."""
    if not settings.CHAT_BRIDGE_TOKEN or x_bridge_token != settings.CHAT_BRIDGE_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid bridge token")
    if await db.get(Project, payload.project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    # Lazy import: core/conversions.py imports create_task from this module
    # at its own top level, so importing it back at module scope here would
    # be a circular import -- deferring to call time breaks the cycle.
    from app.core import conversions

    item_type = payload.item_type or conversions.DEFAULT_ITEM_TYPE
    if item_type not in PLANNING_ITEM_TYPES:
        raise HTTPException(400, f"item_type must be one of {PLANNING_ITEM_TYPES}")
    content = f"(via {payload.from_agent})\n\n{payload.description}" if payload.from_agent else payload.description
    task_id, _ = await conversions.convert_to_quick_task(
        db, title=payload.title, content=content, project_id=payload.project_id, item_type=item_type
    )
    task = await _get_task_or_404(db, task_id)
    await _attach_project_ids(db, [task])
    await _attach_task_health(db, [task])
    await attach_required_skill_ids(db, [task])
    return task


TASK_ENVIRONMENT_FIELDS = ("target_environment", "environment_prerequisites")


async def _mission_environment_change(
    db: AsyncSession, project_id: uuid.UUID | None, authorization: str | None,
    task_id: uuid.UUID, changes: dict,
) -> AuditEvent | None:
    """M0.0b (spec §2.6): a mission task's environment changes only while the
    mission is planning, and every change is a mission audit event."""
    await assert_task_environment_writable(db, project_id)
    project = await db.get(Project, project_id) if project_id is not None else None
    if project is None or project.project_type != "mission":
        return None
    principal = await principal_from_authorization(db, authorization)
    return AuditEvent(
        entity_type="mission", entity_id=project.id, event_type="mission_task_environment_set",
        actor=principal.display_name,
        payload={"principal_type": principal.principal_type, "principal_id": str(principal.principal_id),
                 "task_id": str(task_id), "changes": changes},
    )


@router.post("", response_model=ProjectTaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: ProjectTaskCreate,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> ProjectTask:
    # Traceability: a task must trace back to a planning item or a change request.
    if payload.planning_item_id is None and payload.change_request_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of planning_item_id or change_request_id must be provided",
        )

    if payload.planning_item_id is not None:
        if await db.get(PlanningItem, payload.planning_item_id) is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="planning_item_id must reference an existing planning item",
            )

    if payload.change_request_id is not None:
        if await db.get(ChangeRequest, payload.change_request_id) is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="change_request_id must reference an existing change request",
            )

    if payload.parent_task_id is not None:
        await _get_task_or_404(db, payload.parent_task_id)

    if payload.required_skill_ids:
        await assert_required_skills_writable(
            db,
            await project_id_for_task_source(db, payload.planning_item_id, payload.change_request_id),
            payload.required_skill_ids,
            [],
        )

    task = ProjectTask(**payload.model_dump(exclude={"required_skill_ids"}))
    environment = {f: getattr(payload, f) for f in TASK_ENVIRONMENT_FIELDS if getattr(payload, f) is not None}
    if environment:
        task.id = uuid.uuid4()
        event = await _mission_environment_change(
            db,
            await project_id_for_task_source(db, payload.planning_item_id, payload.change_request_id),
            authorization, task.id, {f: [None, v] for f, v in environment.items()},
        )
        if event is not None:
            db.add(event)
    db.add(task)
    if payload.required_skill_ids:
        await db.flush()
        await replace_required_skills(db, task.id, payload.required_skill_ids)
    await db.commit()
    await db.refresh(task)
    await _attach_project_ids(db, [task])
    await _attach_task_health(db, [task])
    await attach_required_skill_ids(db, [task])
    return task


@router.get("", response_model=list[ProjectTaskOut])
async def list_tasks(
    status_filter: str | None = None,
    planning_item_id: uuid.UUID | None = None,
    change_request_id: uuid.UUID | None = None,
    parent_task_id: uuid.UUID | None = None,
    policy_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[ProjectTask]:
    stmt = select(ProjectTask)
    if status_filter is not None:
        stmt = stmt.where(ProjectTask.status == status_filter)
    if planning_item_id is not None:
        stmt = stmt.where(ProjectTask.planning_item_id == planning_item_id)
    if change_request_id is not None:
        stmt = stmt.where(ProjectTask.change_request_id == change_request_id)
    if parent_task_id is not None:
        stmt = stmt.where(ProjectTask.parent_task_id == parent_task_id)
    if policy_id is not None:
        stmt = stmt.where(ProjectTask.policy_id == policy_id)
    if project_id is not None:
        # Indirect: a task has no project_id column of its own (see
        # _attach_project_ids) -- reach the project through whichever of
        # planning_item/change_request this task traces back to.
        stmt = stmt.where(
            or_(
                ProjectTask.planning_item_id.in_(
                    select(PlanningItem.id).where(PlanningItem.project_id == project_id)
                ),
                ProjectTask.change_request_id.in_(
                    select(ChangeRequest.id).where(ChangeRequest.project_id == project_id)
                ),
            )
        )
    result = await db.execute(stmt.order_by(ProjectTask.created_at))
    tasks = list(result.scalars().all())
    await _attach_project_ids(db, tasks)
    await _attach_task_health(db, tasks)
    await attach_required_skill_ids(db, tasks)
    return tasks


@router.get("/{task_id}", response_model=ProjectTaskOut)
async def get_task(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ProjectTask:
    task = await _get_task_or_404(db, task_id)
    await _attach_project_ids(db, [task])
    await _attach_task_health(db, [task])
    await attach_required_skill_ids(db, [task])
    return task


@router.patch("/{task_id}", response_model=ProjectTaskOut)
async def update_task(
    task_id: uuid.UUID,
    payload: ProjectTaskUpdate,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> ProjectTask:
    task = await _get_task_or_404(db, task_id)
    await _authorize_agent_task_update(db, task, authorization)

    data = payload.model_dump(exclude_unset=True)
    if data.get("status") == "ready":
        raise HTTPException(status_code=409, detail="Task ready is set only by ActivateExecutionWave")

    if "planning_item_id" in data and data["planning_item_id"] is not None:
        if await db.get(PlanningItem, data["planning_item_id"]) is None:
            raise HTTPException(
                status_code=400,
                detail="planning_item_id must reference an existing planning item",
            )

    if "change_request_id" in data and data["change_request_id"] is not None:
        if await db.get(ChangeRequest, data["change_request_id"]) is None:
            raise HTTPException(
                status_code=400,
                detail="change_request_id must reference an existing change request",
            )

    if "parent_task_id" in data and data["parent_task_id"] is not None:
        if data["parent_task_id"] == task_id:
            raise HTTPException(status_code=400, detail="A task cannot be its own parent")
        await _get_task_or_404(db, data["parent_task_id"])

    if "required_skill_ids" in data:
        if data["required_skill_ids"] is None:
            raise HTTPException(status_code=422, detail="required_skill_ids cannot be null; send [] to clear it")
        required_skill_ids = data.pop("required_skill_ids")
        await assert_required_skills_writable(
            db,
            await project_id_for_task_source(db, task.planning_item_id, task.change_request_id),
            required_skill_ids,
            (await required_skill_map(db, [task.id]))[task.id],
        )
        await replace_required_skills(db, task.id, required_skill_ids)

    environment_changes = {
        f: [getattr(task, f), data[f]] for f in TASK_ENVIRONMENT_FIELDS
        if f in data and data[f] != getattr(task, f)
    }
    if environment_changes:
        event = await _mission_environment_change(
            db, await project_id_for_task_source(db, task.planning_item_id, task.change_request_id),
            authorization, task.id, environment_changes,
        )
        if event is not None:
            db.add(event)

    # M0.6a: a *new* transition to done/deployed goes through the global
    # completion guard (repeating the current status is not a transition, so
    # historical done tasks stay editable and are never re-judged).
    completion_target = (
        data["status"]
        if data.get("status") in COMPLETION_TARGET_STATUSES and data["status"] != task.status
        else None
    )
    if data.get("status") == "in_progress":
        await _ensure_dependencies_satisfied(db, task_id)
    proof = None
    principal = None
    if completion_target is not None:
        principal = await principal_from_authorization(db, authorization)
        await _ensure_no_pending_task_approval(db, task_id)
        proof = await assert_task_completion_allowed(db, task, completion_target, principal)

    for field, value in data.items():
        setattr(task, field, value)

    if completion_target is not None:
        if completion_target == "done" and task.completed_at is None:
            task.completed_at = datetime.now(timezone.utc)
        db.add(completion_audit_event(task, completion_target, principal, proof, via="patch_task"))

    await db.commit()
    await db.refresh(task)
    await _attach_project_ids(db, [task])
    await _attach_task_health(db, [task])
    await attach_required_skill_ids(db, [task])
    if data.get("status") in ("done", "deployed"):
        from app.core.dispatch_signal import wake_scheduled_dispatch
        wake_scheduled_dispatch()
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    task = await _get_task_or_404(db, task_id)
    await db.delete(task)
    await db.commit()


async def _ensure_dependencies_satisfied(db: AsyncSession, task_id: uuid.UUID) -> None:
    await ensure_task_dependencies_satisfied(db, task_id)


async def _ensure_no_pending_task_approval(db: AsyncSession, task_id: uuid.UUID) -> None:
    """Fase 3: if a governed approval decision is outstanding for this exact
    execution, a direct PATCH status=done must wait for that decision --
    request_task_approval (core/governed_approval.py) only ever creates one
    when an active project_task policy binding exists. Evidence, review and
    dependencies are the completion guard's job (core/task_completion_guard.py,
    M0.6a), which replaced `_ensure_evidence_verified`."""
    latest_id = (
        await db.execute(
            select(TaskExecution.id)
            .where(TaskExecution.task_id == task_id)
            .order_by(TaskExecution.attempt_number.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest_id is None:
        return
    pending = (
        await db.execute(
            select(ApprovalRequest.id).where(
                ApprovalRequest.target_type == "project_task",
                ApprovalRequest.target_id == task_id,
                ApprovalRequest.target_revision_id == latest_id,
                ApprovalRequest.status == "pending",
            )
        )
    ).scalar_one_or_none()
    if pending is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot complete task: awaiting governed approval decision",
        )


# --------------------------------------------------------------------------
# TaskExecution (nested under a task)
# --------------------------------------------------------------------------


@router.post(
    "/{task_id}/executions",
    response_model=TaskExecutionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_task_execution(
    task_id: uuid.UUID, payload: TaskExecutionCreate, db: AsyncSession = Depends(get_db)
) -> TaskExecution:
    task = await _get_task_or_404(db, task_id)
    await ensure_task_dependencies_satisfied(db, task_id)

    if payload.assignment_id is not None:
        assignment = await db.get(TaskAssignment, payload.assignment_id)
        if assignment is None or assignment.task_id != task_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="assignment_id must reference an assignment belonging to this task",
            )

    if payload.runtime_profile_id is not None:
        profile = await db.get(AgentRuntimeProfile, payload.runtime_profile_id)
        if profile is None or not profile.is_active:
            raise HTTPException(status_code=400, detail="runtime_profile_id must reference an active profile")
        if payload.runtime_type is not None and payload.runtime_type != profile.runtime_type:
            raise HTTPException(status_code=400, detail="runtime_type must match the runtime profile")

    if payload.loop_policy_id is not None:
        policy = await db.get(ProjectLoopPolicy, payload.loop_policy_id)
        if policy is None or not policy.is_active:
            raise HTTPException(status_code=400, detail="loop_policy_id must reference an active policy")
        if policy.project_id != await _resolve_task_project_id(db, task):
            raise HTTPException(status_code=400, detail="loop policy belongs to another project")

    count_result = await db.execute(
        select(TaskExecution.id).where(TaskExecution.task_id == task_id)
    )
    attempt_number = len(count_result.all()) + 1

    execution = TaskExecution(
        task_id=task_id, attempt_number=attempt_number, **payload.model_dump()
    )
    db.add(execution)
    await db.flush()
    await _record_execution_lifecycle_checkpoint(
        db, task, execution, "started", "execution.started", "Execution attempt started"
    )
    created_terminal_checkpoint = {
        "failed": "failed", "verified": "evidence", "completed": "completed",
    }.get(execution.status)
    if created_terminal_checkpoint:
        await _record_execution_lifecycle_checkpoint(
            db, task, execution, created_terminal_checkpoint,
            f"execution.{execution.status}", f"Execution {execution.status}",
        )

    # Rule 6.4.1: planned/assigned/executed remain distinct -- starting an
    # execution moves the parent task into "in_progress" if it hasn't
    # progressed further already.
    if task.status in ("planned", "assigned"):
        task.status = "in_progress"

    await db.commit()
    await db.refresh(execution)
    return execution


@router.get("/{task_id}/executions", response_model=list[TaskExecutionOut])
async def list_task_executions(
    task_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[TaskExecution]:
    await _get_task_or_404(db, task_id)
    result = await db.execute(
        select(TaskExecution)
        .where(TaskExecution.task_id == task_id)
        .order_by(TaskExecution.attempt_number)
    )
    return list(result.scalars().all())


@router.get("/{task_id}/executions/{execution_id}", response_model=TaskExecutionOut)
async def get_task_execution(
    task_id: uuid.UUID, execution_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> TaskExecution:
    execution = await db.get(TaskExecution, execution_id)
    if execution is None or execution.task_id != task_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")
    return execution


@router.patch("/{task_id}/executions/{execution_id}", response_model=TaskExecutionOut)
async def update_task_execution(
    task_id: uuid.UUID,
    execution_id: uuid.UUID,
    payload: TaskExecutionUpdate,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> TaskExecution:
    # §5.7 (M0.2c): this PATCH can set verified/completed, so it is never an
    # agent's. An agent reports through POST .../{execution_id}:report.
    if authorization and authorization.lower().startswith("bearer agt_"):
        raise HTTPException(403, detail={"code": "USE_REPORT_TASK_EXECUTION",
                                         "message": "An agent reports an execution with :report, never this PATCH"})
    execution = await db.get(TaskExecution, execution_id)
    if execution is None or execution.task_id != task_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")

    data = payload.model_dump(exclude_unset=True)

    # Re-validate evidence rule against the merged (existing + incoming) state,
    # since evidence_ref might already be set from a previous PATCH.
    new_status = data.get("status", execution.status)
    new_evidence = data.get("evidence_ref", execution.evidence_ref)
    if new_status != execution.status and new_status != "failed":
        await ensure_task_dependencies_satisfied(db, task_id)
    if new_status in ("verified", "completed") and not new_evidence:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="evidence_ref is required when status is verified or completed",
        )

    for field, value in data.items():
        setattr(execution, field, value)

    if new_status in ("verified", "completed"):
        db.add(
            AuditEvent(
                entity_type="task_execution",
                entity_id=execution.id,
                event_type=f"execution_{new_status}",
                actor="system",
                payload={
                    "task_id": str(execution.task_id),
                    "attempt_number": execution.attempt_number,
                    "evidence_ref": execution.evidence_ref,
                },
            )
        )

    checkpoint_type = {
        "failed": "failed", "verified": "evidence", "completed": "completed",
    }.get(new_status)
    if checkpoint_type:
        task = await _get_task_or_404(db, task_id)
        await _record_execution_lifecycle_checkpoint(
            db, task, execution, checkpoint_type,
            f"execution.{new_status}", f"Execution {new_status}",
        )
        if new_status == "completed":
            # Exact match on origin_id (a real ProjectTask.id) since the
            # 2026-07-25 origin unification -- every Inbox message whose
            # Tipo=Task points at this task gets its execution timestamp
            # stamped. See AgentDemand.task_execution_at's docstring.
            await db.execute(
                update(AgentDemand)
                .where(
                    AgentDemand.origin_type == "task",
                    AgentDemand.origin_id == task.id,
                )
                .values(task_execution_at=execution.finished_at or datetime.now(timezone.utc))
            )

    await db.commit()
    await db.refresh(execution)
    return execution


REPORT_ACTION = "mission.execution.report"
REPORT_OPEN_STATUSES = ("pending", "running", "blocked", "reported")


async def _evidence_scope(db: AsyncSession, task: ProjectTask) -> tuple[set[uuid.UUID], set[uuid.UUID]]:
    """(project ids, task ids) an evidence ref of this task may name: its own
    project and, for a mission task, every mission it serves with their
    executor projects."""
    from app.core.mission import executor_project_ids

    project_id = await _resolve_task_project_id(db, task)
    missions, scope = await _task_missions_scope(db, task)
    projects = {project_id}
    for mission in missions:
        projects |= {mission.project_id, *(await executor_project_ids(db, mission.project_id))}
    return projects, scope | {task.id}


async def _assert_evidence_in_scope(db: AsyncSession, task: ProjectTask, evidence: list[str]) -> None:
    """§5.7: each ref is git:<sha>, file:<relative path inside the project> or
    db:<type>:<uuid> naming a row of this task's own scope. Anything else is
    422 (EVIDENCE_INVALID for the format, EVIDENCE_OUT_OF_SCOPE otherwise)."""
    from app.core.task_evidence import DB_EVIDENCE_ENTITIES, GIT_SHA_RE
    from app.db.models.product import ProductVersion

    def refuse(code: str, ref: str, message: str):
        raise HTTPException(422, detail={"code": code, "message": message, "evidence": ref})

    projects: set[uuid.UUID] | None = None
    tasks: set[uuid.UUID] = set()
    for ref in evidence:
        prefix, _, rest = ref.partition(":")
        if len(ref) > 500 or not rest:
            refuse("EVIDENCE_INVALID", ref, "Evidence is git:<sha>, file:<relative path> or db:<type>:<uuid>")
        if prefix == "git":
            if not GIT_SHA_RE.match(rest.lower()):
                refuse("EVIDENCE_OUT_OF_SCOPE", ref, "git evidence is a commit sha of the project's own repository")
        elif prefix == "file":
            parts = rest.split("/")
            if rest.startswith(("/", "~")) or "\\" in rest or ".." in parts or "" in parts or "." in parts:
                refuse("EVIDENCE_OUT_OF_SCOPE", ref, "file evidence is a normalized path relative to the project")
        elif prefix == "db":
            entity_type, _, entity_id = rest.partition(":")
            model = DB_EVIDENCE_ENTITIES.get(entity_type)
            try:
                row_id = uuid.UUID(entity_id)
            except ValueError:
                row_id = None
            if model is None or row_id is None:
                refuse("EVIDENCE_INVALID", ref, "db evidence is db:<project|project_task|planning_item|"
                       "change_request|product>:<uuid>")
            if projects is None:
                projects, tasks = await _evidence_scope(db, task)
            row = await db.get(model, row_id)
            owner: set[uuid.UUID] = set()
            if row is not None:
                if entity_type == "project":
                    owner = {row.id}
                elif entity_type == "project_task":
                    owner = {await _resolve_task_project_id(db, row)} if row.id in tasks else set()
                elif entity_type in ("planning_item", "change_request"):
                    owner = {row.project_id}
                elif entity_type == "product":
                    owner = set((await db.execute(
                        select(Project.id).join(ProductVersion, ProductVersion.id == Project.product_version_id)
                        .where(ProductVersion.product_id == row.id, Project.id.in_(list(projects)))
                    )).scalars())
            if not owner & projects:
                refuse("EVIDENCE_OUT_OF_SCOPE", ref, "db evidence must name an existing row of this task's scope")
        else:
            refuse("EVIDENCE_INVALID", ref, "Evidence is git:<sha>, file:<relative path> or db:<type>:<uuid>")


@router.post("/{task_id}/executions/{execution_id}:report", response_model=TaskReportOut,
             dependencies=[Depends(require_mission_tools), Depends(limit_command_body)])
async def report_task_execution(
    task_id: uuid.UUID,
    execution_id: uuid.UUID,
    payload: TaskReportIn,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
):
    """report_task_execution (M0.2c, §5.7): DONE is a report, not acceptance.
    Only the execution's executor (assignment agent, else the dispatched
    demand's target) with mission.execution.report on the task's project (or
    one of its missions); anyone else is 403. The status is reported, failed
    or blocked -- never verified/completed: only the evidence verification
    pass promotes reported -> verified, and the task still needs an
    independent review. The first evidence ref is the one the pass checks;
    all of them are audited. A later report supersedes an earlier one
    (history in audit) until the execution is verified, completed or failed."""
    if principal.principal_type != "agent":
        raise HTTPException(403, detail={"code": "AGENT_ONLY",
                                         "message": "The executor reports with its own agt_ credential"})
    enforce_command_limits(principal)
    command = "task.report_execution"
    body_hash = request_hash(command, {"task_id": str(task_id), "execution_id": str(execution_id),
                                       **payload.model_dump(mode="json")})
    task = await _get_task_or_404(db, task_id)
    execution = (await db.execute(
        select(TaskExecution).where(TaskExecution.id == execution_id).with_for_update()
    )).scalar_one_or_none()
    if execution is None or execution.task_id != task_id:
        raise HTTPException(404, detail={"code": "EXECUTION_NOT_FOUND", "message": "Execution not found for this task"})
    if await resolve_executor_agent_id(db, execution) != principal.principal_id:
        raise HTTPException(403, detail={"code": "NOT_EXECUTOR",
                                         "message": "Only the executor of this execution reports it"})
    projects = [await _resolve_task_project_id(db, task)]
    missions, _scope = await _task_missions_scope(db, task)
    projects += [m.project_id for m in missions if m.project_id not in projects]
    source, delegation = None, None
    for project_id in projects:
        try:
            source, delegation = await authorize_action(db, principal, REPORT_ACTION, project_id=project_id)
            break
        except HTTPException as exc:
            if exc.status_code != 403:
                raise
    if source is None:
        raise HTTPException(403, detail={"code": "DELEGATION_REQUIRED", "action": REPORT_ACTION,
                                         "message": f"No active delegation permits {REPORT_ACTION} here"})
    replay = await begin_command(db, principal, payload.idempotency_key, command, body_hash)
    if replay is not None:
        return replay
    if execution.status not in REPORT_OPEN_STATUSES:
        raise HTTPException(409, detail={"code": "EXECUTION_CLOSED",
                                         "message": f"The execution is {execution.status}; open a new attempt",
                                         "execution_status": execution.status})
    evidence = [ref.strip() for ref in payload.evidence]
    await _assert_evidence_in_scope(db, task, evidence)

    previous_status = execution.status
    execution.status = payload.status
    execution.outcome_summary = payload.summary
    execution.evidence_ref = evidence[0]
    if payload.status in ("reported", "failed"):
        execution.finished_at = datetime.now(timezone.utc)
    db.add(AuditEvent(
        entity_type="task_execution", entity_id=execution.id, event_type="execution_reported",
        actor=principal.display_name,
        payload={"principal_type": principal.principal_type, "principal_id": str(principal.principal_id),
                 "authority_source": source, "delegation_id": str(delegation.id) if delegation else None,
                 "idempotency_key": payload.idempotency_key, "task_id": str(task.id),
                 "status": payload.status, "previous_status": previous_status, "evidence": evidence,
                 "summary_sha256": hashlib.sha256(payload.summary.encode()).hexdigest()},
    ))
    out = TaskReportOut(task_id=task.id, execution_id=execution.id, status=execution.status,
                        evidence_ref=execution.evidence_ref, evidence=evidence,
                        verification="queued" if payload.status == "reported" else "not_applicable")
    record_command(db, principal, payload.idempotency_key, command, body_hash, 200, out.model_dump(mode="json"),
                   target_type="task_execution", target_id=execution.id)
    await db.commit()
    return out


# --------------------------------------------------------------------------
# TaskDependency
# --------------------------------------------------------------------------


async def _task_missions_scope(db: AsyncSession, task: ProjectTask) -> tuple[list, set[uuid.UUID]]:
    """The missions a task belongs to and the union of their task scopes."""
    from app.core.mission_plan import mission_scope_tasks
    from app.core.task_baseline_guard import task_missions

    missions = await task_missions(db, task)
    scope: set[uuid.UUID] = set()
    for mission in missions:
        scope |= set(await mission_scope_tasks(db, mission.project_id))
    return missions, scope


async def _dependency_principal(
    db: AsyncSession, authorization: str | None,
) -> tuple[ActorPrincipal | None, str]:
    """(principal, actor name). An `agt_` caller is resolved strictly: it is
    authorized and audited as itself. A person's JWT was already checked by
    RequireAuthMiddleware and this route never authorized people beyond that,
    so it keeps doing so: the user is resolved when it exists (audit and
    receipt), else only the token's subject names the audit actor."""
    if authorization and authorization.lower().startswith("bearer agt_"):
        principal = await principal_from_authorization(db, authorization)
        return principal, principal.display_name
    try:
        principal = await principal_from_authorization(db, authorization)
        return principal, principal.display_name
    except HTTPException:
        from app.core.security import decode_access_token

        token = authorization[7:].strip() if authorization else ""
        subject = (decode_access_token(token) or {}).get("sub") if token else None
        return None, str(subject or "user")


async def _assert_not_in_baseline(db: AsyncSession, task_id: uuid.UUID) -> None:
    """§5.4: a dependency of a task frozen in a current baseline is part of its
    content hash, so changing it needs a change request and a new approval."""
    from app.core.mission_plan import current_baseline_of_task

    baseline = await current_baseline_of_task(db, task_id)
    if baseline is not None:
        raise HTTPException(409, detail={
            "code": "TASK_IN_BASELINE",
            "message": "The task is in a current baseline; changing its dependencies needs a change request",
            "task_id": str(task_id), "baseline_id": str(baseline.id),
        })


@router.post(
    "/{task_id}/dependencies",
    response_model=TaskDependencyAddedOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_command_body)],
)
async def create_task_dependency(
    task_id: uuid.UUID,
    payload: TaskDependencyCreate,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Also add_task_dependency (M0.2b, §5.4). An `agt_` caller needs
    MISSION_TOOLS_ENABLED, an idempotency key (receipt, §0.4) and
    planning.execution.manage on the task's project. For a mission task, the
    other task must be in the same mission scope (else 404, no existence
    leak) and only finish_to_start is accepted -- the dispatch gate only
    understands that one; an agent is held to it everywhere. A task frozen in
    a current baseline refuses with 409 TASK_IN_BASELINE. One edge per pair
    (409 DEPENDENCY_ALREADY_EXISTS with its id)."""
    if payload.task_id != task_id:
        raise HTTPException(status_code=400, detail="task_id in body must match the path task_id")

    principal, actor = await _dependency_principal(db, authorization)
    is_agent = principal is not None and principal.principal_type == "agent"
    command = "task.add_dependency"
    body_hash = request_hash(command, {"task_id": str(task_id), **payload.model_dump(mode="json")})
    if is_agent:
        enforce_command_limits(principal)
        if payload.idempotency_key is None:
            raise HTTPException(422, detail={"code": "IDEMPOTENCY_KEY_REQUIRED",
                                             "message": "idempotency_key is required"})

    task = await _get_task_or_404(db, task_id)
    source, delegation = "user", None
    if is_agent:
        try:
            source, delegation = await authorize_action(
                db, principal, "planning.execution.manage", project_id=await _resolve_task_project_id(db, task),
            )
        except HTTPException as exc:
            if exc.status_code != 403:
                raise
            raise HTTPException(403, detail={
                "code": "DELEGATION_REQUIRED", "message": "No active delegation permits planning.execution.manage "
                "on this task's project", "action": "planning.execution.manage"}) from exc
    receipt = payload.idempotency_key is not None and principal is not None
    if receipt:
        replay = await begin_command(db, principal, payload.idempotency_key, command, body_hash)
        if replay is not None:
            return replay

    depends_on = await db.get(ProjectTask, payload.depends_on_task_id)
    missions, scope = await _task_missions_scope(db, task)
    not_found = HTTPException(404, detail={"code": "TASK_NOT_FOUND",
                                           "message": "depends_on_task_id is not a task of this scope"})
    if depends_on is None:
        raise not_found if (missions or is_agent) else HTTPException(404, "Task not found")
    if missions and depends_on.id not in scope:
        raise not_found
    if is_agent and not missions and (
        await _resolve_task_project_id(db, depends_on) != await _resolve_task_project_id(db, task)
    ):
        raise not_found
    if (missions or is_agent) and payload.dependency_type != "finish_to_start":
        raise HTTPException(422, detail={
            "code": "DEPENDENCY_TYPE_NOT_SUPPORTED",
            "message": "Only finish_to_start is accepted: the dispatch gate understands no other type",
            "dependency_type": payload.dependency_type})
    await _assert_not_in_baseline(db, task_id)

    # Serialize graph edits so concurrent A->B and B->A cannot both pass.
    await db.execute(select(func.pg_advisory_xact_lock(0x464854444550)))
    existing = await db.scalar(select(TaskDependency.id).where(
        TaskDependency.task_id == task_id, TaskDependency.depends_on_task_id == payload.depends_on_task_id,
    ))
    if existing is not None:
        raise HTTPException(409, detail={"code": "DEPENDENCY_ALREADY_EXISTS",
                                         "message": "This dependency already exists",
                                         "dependency_id": str(existing)})
    reachable = select(TaskDependency.depends_on_task_id.label("task_id")).where(
        TaskDependency.task_id == payload.depends_on_task_id
    ).cte("dependency_ancestors", recursive=True)
    reachable = reachable.union(
        select(TaskDependency.depends_on_task_id).join(
            reachable, TaskDependency.task_id == reachable.c.task_id
        )
    )
    if await db.scalar(select(reachable.c.task_id).where(reachable.c.task_id == task_id).limit(1)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This dependency would create a cycle between tasks",
        )

    dependency = TaskDependency(**payload.model_dump(exclude={"idempotency_key"}))
    db.add(dependency)
    await db.flush()
    # The task is not in a current baseline (refused above); if its mission
    # already has one, the task runs only after a change request is applied.
    impact = "requires_change_request" if any(m.current_baseline_id for m in missions) else "none"
    db.add(AuditEvent(
        entity_type="project_task", entity_id=task_id, event_type="task_dependency_added", actor=actor,
        payload={"principal_type": principal.principal_type if principal else "user",
                 "principal_id": str(principal.principal_id) if principal else None,
                 "authority_source": source, "delegation_id": str(delegation.id) if delegation else None,
                 "idempotency_key": payload.idempotency_key, "dependency_id": str(dependency.id),
                 "depends_on_task_id": str(payload.depends_on_task_id),
                 "dependency_type": payload.dependency_type, "baseline_impact": impact},
    ))
    await db.flush()
    await db.refresh(dependency)
    out = TaskDependencyAddedOut.model_validate(dependency).model_copy(update={"baseline_impact": impact})
    if receipt:
        record_command(db, principal, payload.idempotency_key, command, body_hash, 201, out.model_dump(mode="json"),
                       target_type="task_dependency", target_id=dependency.id)
    await db.commit()
    return out


@router.get("/{task_id}/dependencies", response_model=list[TaskDependencyOut])
async def list_task_dependencies(
    task_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[TaskDependency]:
    await _get_task_or_404(db, task_id)
    result = await db.execute(
        select(TaskDependency).where(TaskDependency.task_id == task_id)
    )
    return list(result.scalars().all())


@router.delete("/{task_id}/dependencies/{dependency_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task_dependency(
    task_id: uuid.UUID, dependency_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> None:
    dependency = await db.get(TaskDependency, dependency_id)
    if dependency is None or dependency.task_id != task_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dependency not found")
    # Same baseline rule as adding one (§5.4).
    await _assert_not_in_baseline(db, task_id)
    await db.delete(dependency)
    await db.commit()


# --------------------------------------------------------------------------
# TaskRequiredSkill
# --------------------------------------------------------------------------


@router.post(
    "/{task_id}/required-skills",
    response_model=TaskRequiredSkillOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_task_required_skill(
    task_id: uuid.UUID, payload: TaskRequiredSkillCreate, db: AsyncSession = Depends(get_db)
) -> TaskRequiredSkill:
    if payload.task_id != task_id:
        raise HTTPException(status_code=400, detail="task_id in body must match the path task_id")
    task = await _get_task_or_404(db, task_id)
    # DT-M0-1 (M0.2b): this table is the one store of required skills, so the
    # mission lock (planning only) applies here as on PATCH /tasks.
    current = (await required_skill_map(db, [task_id]))[task_id]
    if payload.is_mandatory:
        await assert_required_skills_writable(
            db, await project_id_for_task_source(db, task.planning_item_id, task.change_request_id),
            list(dict.fromkeys([*current, payload.skill_id])), current,
        )
    if await db.scalar(select(TaskRequiredSkill.id).where(
        TaskRequiredSkill.task_id == task_id, TaskRequiredSkill.skill_id == payload.skill_id,
    )):
        raise HTTPException(status_code=409, detail="This skill is already required by the task")

    required_skill = TaskRequiredSkill(**payload.model_dump())
    db.add(required_skill)
    await db.commit()
    await db.refresh(required_skill)
    return required_skill


@router.get("/{task_id}/required-skills", response_model=list[TaskRequiredSkillOut])
async def list_task_required_skills(
    task_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[TaskRequiredSkill]:
    await _get_task_or_404(db, task_id)
    result = await db.execute(
        select(TaskRequiredSkill).where(TaskRequiredSkill.task_id == task_id)
    )
    return list(result.scalars().all())


# --------------------------------------------------------------------------
# TaskAssignment
# --------------------------------------------------------------------------


@router.post(
    "/{task_id}/assignments",
    response_model=TaskAssignmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_task_assignment(
    task_id: uuid.UUID, payload: TaskAssignmentCreate, db: AsyncSession = Depends(get_db)
) -> TaskAssignment:
    if payload.task_id != task_id:
        raise HTTPException(status_code=400, detail="task_id in body must match the path task_id")
    task = await _get_task_or_404(db, task_id)

    if payload.agent_id is not None:
        agent = await db.get(Agent, payload.agent_id)
        if agent is None or not agent.is_active or agent.status != "active":
            raise HTTPException(status_code=400, detail="agent_id must reference an active agent")
    if payload.sub_agent_id is not None:
        sub_agent = await db.get(SubAgent, payload.sub_agent_id)
        if sub_agent is None or not sub_agent.is_active or sub_agent.status != "active":
            raise HTTPException(status_code=400, detail="sub_agent_id must reference an active sub-agent")

    if payload.membership_id is not None:
        membership = await db.get(ProjectAgentMembership, payload.membership_id)
        if membership is None or membership.status != "active":
            raise HTTPException(status_code=400, detail="membership_id must reference an active membership")
        if membership.project_id != await _resolve_task_project_id(db, task):
            raise HTTPException(status_code=400, detail="membership belongs to another project")
        if membership.agent_id != payload.agent_id or membership.sub_agent_id != payload.sub_agent_id:
            raise HTTPException(
                status_code=400,
                detail="assignment agent/sub-agent must match the project membership",
            )

    assignment = TaskAssignment(**payload.model_dump())
    db.add(assignment)

    # Rule 6.4.1: assigning a task moves it out of "planned" into
    # "assigned" (unless it has already progressed further).
    if task.status == "planned":
        task.status = "assigned"

    await db.commit()
    await db.refresh(assignment)
    return assignment


@router.get("/{task_id}/assignments", response_model=list[TaskAssignmentOut])
async def list_task_assignments(
    task_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[TaskAssignment]:
    await _get_task_or_404(db, task_id)
    result = await db.execute(
        select(TaskAssignment).where(TaskAssignment.task_id == task_id)
    )
    return list(result.scalars().all())


# --------------------------------------------------------------------------
# ResponsibilityArea (standalone -- see responsibility_router above)
# --------------------------------------------------------------------------


@responsibility_router.post("", response_model=ResponsibilityAreaOut, status_code=status.HTTP_201_CREATED)
async def create_responsibility_area(
    payload: ResponsibilityAreaCreate, db: AsyncSession = Depends(get_db)
) -> ResponsibilityArea:
    if payload.project_id is not None:
        if await db.get(Project, payload.project_id) is None:
            raise HTTPException(status_code=400, detail="project_id must reference an existing project")
    if await db.get(Agent, payload.owner_agent_id) is None:
        raise HTTPException(status_code=400, detail="owner_agent_id must reference an existing agent")

    existing = (
        await db.execute(
            select(ResponsibilityArea).where(
                ResponsibilityArea.task_type == payload.task_type,
                ResponsibilityArea.project_id == payload.project_id
                if payload.project_id is not None
                else ResponsibilityArea.project_id.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A responsibility area already exists for this task_type/project combination",
        )

    area = ResponsibilityArea(**payload.model_dump())
    db.add(area)
    await db.commit()
    await db.refresh(area)
    return area


@responsibility_router.get("", response_model=list[ResponsibilityAreaOut])
async def list_responsibility_areas(
    project_id: uuid.UUID | None = None, db: AsyncSession = Depends(get_db)
) -> list[ResponsibilityArea]:
    stmt = select(ResponsibilityArea)
    if project_id is not None:
        # Both the project-scoped overrides and the global defaults are
        # relevant to a project's own view -- resolve_responsibility_owner
        # falls back to the global row, so callers listing "what applies
        # here" need to see both.
        stmt = stmt.where(
            or_(ResponsibilityArea.project_id == project_id, ResponsibilityArea.project_id.is_(None))
        )
    result = await db.execute(stmt)
    return list(result.scalars().all())


@responsibility_router.patch("/{area_id}", response_model=ResponsibilityAreaOut)
async def update_responsibility_area(
    area_id: uuid.UUID, payload: ResponsibilityAreaUpdate, db: AsyncSession = Depends(get_db)
) -> ResponsibilityArea:
    area = await db.get(ResponsibilityArea, area_id)
    if area is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Responsibility area not found")
    if await db.get(Agent, payload.owner_agent_id) is None:
        raise HTTPException(status_code=400, detail="owner_agent_id must reference an existing agent")
    area.owner_agent_id = payload.owner_agent_id
    await db.commit()
    await db.refresh(area)
    return area


@responsibility_router.delete("/{area_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_responsibility_area(area_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    area = await db.get(ResponsibilityArea, area_id)
    if area is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Responsibility area not found")
    await db.delete(area)
    await db.commit()


# --------------------------------------------------------------------------
# Task dispatch -- executed through the Inbox message process
# --------------------------------------------------------------------------
@router.post("/{task_id}/dispatch", response_model=TaskInboxDispatchOut,
             dependencies=[Depends(limit_command_body)])
async def dispatch_task(
    task_id: uuid.UUID,
    payload: TaskInboxDispatchIn,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Executes a task by filing it into the Inbox and dispatching it there.

    Decisão do Marcelo (2026-07-26): **toda** tarefa é processada pelo
    processo de mensagens. Por isso este endpoint não cria um segundo
    executor -- ele monta a mensagem vinculada (`AgentDemand` com
    `origin_type="task"`, `origin_id=task.id`, o mesmo vínculo que
    update_task_execution já carimba de volta) e a entrega ao dispatch do
    domínio demand, que continua sendo o único caminho até o runner
    governado do host-bridge (core/agent_runs.py).

    Consequências de reusar aquele caminho, todas desejadas: a execução
    aparece no Inbox como qualquer outra, o retorno do agente volta como
    item ligado quando `requires_response`, e o polling/reconciliação de
    run já existente (`run_dispatch_completion_pass`) vale para tarefas sem
    nenhum código novo.

    Also dispatch_task (M0.2c, §5.6): an `agt_` caller needs
    MISSION_TOOLS_ENABLED, an `idempotency_key` (receipt, §0.4) and
    planning.execution.manage on the task's project. `scheduled_at` in the
    future queues the demand without reserving.
    """
    principal, actor = await _dependency_principal(db, authorization)
    authority: tuple[str, Any] = ("user", None)
    if principal is not None and principal.principal_type == "agent":
        enforce_command_limits(principal)
        if payload.idempotency_key is None:
            raise HTTPException(422, detail={"code": "IDEMPOTENCY_KEY_REQUIRED",
                                             "message": "idempotency_key is required"})
        task = await _get_task_or_404(db, task_id)
        try:
            authority = await authorize_action(
                db, principal, "planning.execution.manage", project_id=await _resolve_task_project_id(db, task),
            )
        except HTTPException as exc:
            if exc.status_code != 403:
                raise
            raise HTTPException(403, detail={
                "code": "DELEGATION_REQUIRED", "message": "No active delegation permits planning.execution.manage "
                "on this task's project", "action": "planning.execution.manage"}) from exc
    elif principal is not None:
        authority = ("admin" if principal.is_admin else "user", None)
    return await _dispatch_task_by_id(task_id, payload, db, principal=principal, actor=actor, authority=authority)


def _dispatch_out(task: ProjectTask, demand: AgentDemand) -> TaskInboxDispatchOut:
    return TaskInboxDispatchOut(
        task_id=task.id,
        task_status=task.status,
        demand_id=demand.id,
        demand_number=demand.number,
        target_agent_id=demand.target_agent_id,
        dispatch_status=demand.dispatch_status,
        agent_run_id=demand.agent_run_id,
        scheduled_at=demand.scheduled_at,
    )


async def _dispatch_replay(db: AsyncSession, principal: ActorPrincipal, key: str, task: ProjectTask):
    """A replayed key answers with the demand it created, as it is now (a
    reservation commits before the run starts, so the stored body would be
    stale)."""
    from fastapi.responses import JSONResponse

    from app.core.command_receipts import REPLAY_HEADER
    from app.db.models.command_receipt import AgentCommandReceipt

    receipt = (await db.execute(select(AgentCommandReceipt).where(
        AgentCommandReceipt.principal_type == principal.principal_type,
        AgentCommandReceipt.principal_id == principal.principal_id,
        AgentCommandReceipt.idempotency_key == key,
    ))).scalar_one()
    demand = await db.get(AgentDemand, receipt.target_id) if receipt.target_id else None
    body = _dispatch_out(task, demand).model_dump(mode="json") if demand else receipt.response_body
    return JSONResponse(status_code=200, content=body, headers={REPLAY_HEADER: "true"})


async def _mission_assignment(
    db: AsyncSession, task: ProjectTask, target_agent_id: uuid.UUID | None,
) -> tuple[TaskAssignment, ProjectAgentMembership]:
    """§5.6: a mission task runs only on its active assignment with an active
    membership -- never a responsibility-area owner nor another target."""
    assignment = (await db.execute(
        select(TaskAssignment)
        .where(TaskAssignment.task_id == task.id, TaskAssignment.status == "active",
               TaskAssignment.agent_id.isnot(None))
        .order_by(TaskAssignment.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    membership = await db.get(ProjectAgentMembership, assignment.membership_id) if (
        assignment is not None and assignment.membership_id is not None) else None
    if assignment is None or membership is None or membership.status != "active":
        raise HTTPException(409, detail={
            "code": "TASK_NOT_ASSIGNED",
            "message": "A mission task is dispatched only to its active assignment with an active membership",
            "task_id": str(task.id)})
    if target_agent_id is not None and target_agent_id != assignment.agent_id:
        raise HTTPException(409, detail={
            "code": "TARGET_NOT_ASSIGNEE", "message": "A mission task runs only on its assignee; reassign it first",
            "task_id": str(task.id), "assignee_agent_id": str(assignment.agent_id)})
    return assignment, membership


async def _dispatch_task_by_id(
    task_id: uuid.UUID,
    payload: TaskInboxDispatchIn,
    db: AsyncSession,
    *,
    principal: ActorPrincipal | None = None,
    actor: str = "forgehub",
    authority: tuple[str, Any] = ("system", None),
) -> TaskInboxDispatchOut:
    """Core of dispatch_task, factored out so other domains (Pacote 4:
    approving a project_task Approval) can trigger the exact same dispatch
    path instead of re-implementing it or doing an HTTP self-call.

    Order (M0.2c, §5.6): a run of unknown outcome is answered with its demand
    (§0.4); then the M0.6b baseline (mission state included); then the
    no-second-run rule -- an active/reserved run (or, for a mission, a queued
    one) is 409 TASK_RUN_IN_FLIGHT; then task not terminal, dependencies, the
    mission assignment with membership, target serialization (§4.3) and the
    capacity/one-per-agent check inside reserve_dispatch. A scheduled
    dispatch (future `scheduled_at`) leaves dependencies, targets and
    capacity to the scheduled pass, which re-checks them when due."""
    # Import local: demand.py já importa o modelo ProjectTask, e um import
    # route->route no topo deste módulo criaria um ciclo assim que aquele
    # módulo precisar de qualquer coisa daqui.
    from app.api.routes.demand import (
        RECONCILIATION_REQUIRED_ERROR,
        _execute_dispatch,
        _demand_preview,
        recover_dispatch_outcome,
    )
    from app.core.agent_runs import AgentRunDispatchError
    from app.core.dispatch_targets import assert_task_targets_free
    from app.core.mission_dispatch import (
        EVIDENCE_INSTRUCTION,
        build_mission_dispatch_context,
        in_flight_error,
        task_run_in_flight,
    )
    from app.core.task_baseline_guard import _governing_mission, task_missions

    task = await _get_task_or_404(db, task_id)
    missions = await task_missions(db, task)
    is_agent = principal is not None and principal.principal_type == "agent"
    if missions and principal is not None and principal.principal_type == "user" and not principal.is_admin:
        raise HTTPException(403, detail={"code": "MISSION_ADMIN_ONLY",
                                         "message": "Only an administrator acts on a mission in M0"})
    if (missions or is_agent) and payload.command_text and len(payload.command_text) > 4000:
        raise HTTPException(422, detail={"code": "COMMAND_TEXT_TOO_LONG",
                                         "message": "command_text is limited to 4000 characters"})

    command = "task.dispatch"
    use_receipt = principal is not None and payload.idempotency_key is not None
    body_hash = request_hash(command, {"task_id": str(task_id), **payload.model_dump(mode="json")})
    if use_receipt:
        replay = await begin_command(db, principal, payload.idempotency_key, command, body_hash)
        if replay is not None:
            return await _dispatch_replay(db, principal, payload.idempotency_key, task)

    # A second POST after an ambiguous bridge outcome must continue to point
    # at its durable demand/execution, while a completed demand remains free
    # to create the task's intended next attempt. Anything else in flight
    # (running, reserved, or queued for a mission) is never doubled (§0.4).
    in_flight = await task_run_in_flight(db, task.id, include_queued=bool(missions))
    if in_flight is not None and in_flight.agent_run_id and in_flight.dispatch_error == RECONCILIATION_REQUIRED_ERROR:
        return _dispatch_out(task, in_flight)

    # M0.6b: early, non-authoritative baseline check (reserve_dispatch repeats
    # it under its lock), so a refused dispatch leaves no TaskExecution row.
    # First of the guards (§5.6): a changed task says so even while queued.
    await assert_task_baseline_current(db, task)
    if in_flight is not None:
        raise in_flight_error(in_flight)

    if task.status in ("done", "deployed", "cancelled"):
        if missions:
            raise HTTPException(409, detail={"code": "TASK_TERMINAL",
                                             "message": f"Task is already {task.status}", "status": task.status})
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Task is already {task.status} and cannot be dispatched",
        )

    now = datetime.now(timezone.utc)
    scheduled = payload.scheduled_at is not None and payload.scheduled_at > now
    if not scheduled:
        await ensure_task_dependencies_satisfied(db, task.id)

    project_id = await _resolve_task_project_id(db, task)
    project = await db.get(Project, project_id)
    # Task execution belongs in the explicitly configured Project checkout.
    # demand.py validates it and never falls back to a host-global cwd.
    working_path = project.working_directory_path if project is not None else None

    # Alvo: o informado, senão o agente da atribuição ativa da task, senão
    # (layered task-execution governance, Fase 2) o dono padrão resolvido
    # por ResponsibilityArea para a categoria desta task -- só então falha.
    # Uma tarefa de missão só roda na sua atribuição ativa (M0.2c).
    target_agent_id = payload.target_agent_id
    assignment_id: uuid.UUID | None = None
    membership: ProjectAgentMembership | None = None
    if missions:
        assignment, membership = await _mission_assignment(db, task, target_agent_id)
        target_agent_id, assignment_id = assignment.agent_id, assignment.id
        if not scheduled:
            await assert_task_targets_free(db, task, working_path)
    elif target_agent_id is None:
        assignment = (
            await db.execute(
                select(TaskAssignment)
                .where(
                    TaskAssignment.task_id == task.id,
                    TaskAssignment.status == "active",
                    TaskAssignment.agent_id.isnot(None),
                )
                .order_by(TaskAssignment.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if assignment is not None:
            target_agent_id = assignment.agent_id
            assignment_id = assignment.id
        else:
            target_agent_id = await resolve_responsibility_owner(db, task.task_type, project_id)
        if target_agent_id is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Task has no active agent assignment and no responsibility area covers "
                    f"task_type={task.task_type!r}; pass target_agent_id, assign it, or "
                    "register a responsibility area first"
                ),
            )

    agent = await db.get(Agent, target_agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    context_manifest: list[dict[str, Any]] | None = None
    command_text = payload.command_text
    if missions:
        # §6: the body of a mission task comes only from the allowlist; the
        # extra instruction goes inside it, so it counts toward the 32 KiB.
        context = await build_mission_dispatch_context(
            db, task, mission=await _governing_mission(db, task, missions), working_path=working_path,
            membership=membership, command_text=command_text,
        )
        body = context.body
        context_manifest = context.manifest
        command_text = None
    else:
        body_parts = [f"Task #{task.number}: {task.title}"]
        if task.description:
            body_parts.append(task.description)
        if task.plan_brief:
            body_parts.append(f"Plano/abordagem:\n{task.plan_brief}")
        body_parts.append(
            f"Tipo: {task.task_type} | Prioridade: {task.priority} | Status atual: {task.status}"
        )
        # Evidência (Fase 1 da governança em camadas): pede ao agente que declare
        # de forma estruturada o que comprova o trabalho, para o verificador
        # automático (core/task_evidence.py) cruzar contra a realidade em vez de
        # aceitar só a narrativa da resposta.
        body_parts.append(EVIDENCE_INSTRUCTION)
        body = "\n\n".join(body_parts)

    count_result = await db.execute(
        select(TaskExecution.id).where(TaskExecution.task_id == task.id)
    )
    attempt_number = len(count_result.all()) + 1
    execution = TaskExecution(
        task_id=task.id,
        assignment_id=assignment_id,
        attempt_number=attempt_number,
        executor_type="agent",
        status="pending" if scheduled else "running",
        started_at=None if scheduled else now,
    )
    db.add(execution)
    await db.flush()  # atribui execution.id antes do demand referenciá-lo

    demand = AgentDemand(
        from_agent="forgehub",
        subject=f"Task #{task.number} — {task.title}"[:255],
        body=body,
        status="new",
        target_agent_id=target_agent_id,
        project_id=project_id,
        working_path=working_path,
        origin_type="task",
        origin_id=task.id,
        task_execution_id=execution.id,
        # Meio de comunicação = Software Factory, com a própria task como
        # endereço de retorno: aqui o resultado é o status/evidência da task,
        # não uma mensagem (2026-08-13).
        channel="factory",
        channel_ref=str(task.id),
        requires_response=payload.requires_response,
        scheduled_at=payload.scheduled_at if scheduled else None,
        command_text=command_text if scheduled else None,
    )
    db.add(demand)
    await db.flush()  # atribui demand.id/number antes da notificação referenciá-los
    execution.runtime_session_ref = str(demand.id)

    db.add(
        Notification(
            source="system",
            severity="info",
            title=f"New in Inbox: {demand.subject}",
            message=_demand_preview(demand.body),
            event_key=f"demand:{demand.id}",
            occurred_at=now,
        )
    )
    if use_receipt:
        # Committed with the reservation (reserve_dispatch commits before the
        # bridge call), so a retry with this key finds this demand.
        record_command(db, principal, payload.idempotency_key, command, body_hash, 200,
                       {"task_id": str(task.id), "demand_id": str(demand.id), "demand_number": demand.number},
                       target_type="agent_demand", target_id=demand.id)

    if not scheduled:
        known_run_id: str | None = None
        dispatch_id = demand.id
        try:
            demand = await _execute_dispatch(db, demand, target_agent_id, command_text)
            known_run_id = demand.agent_run_id
        except AgentRunDispatchError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            await recover_dispatch_outcome(
                db, dispatch_id, known_run_id=known_run_id or demand.agent_run_id, scheduled=False
            )
            raise HTTPException(
                status_code=502,
                detail="Host-bridge dispatch outcome is uncertain; reconcile the known run before retrying",
            ) from exc

        # Regra 6.4.1 estendida: despachar tira a task de planned/ready/assigned.
        # Estados posteriores (in_progress, blocked) não regridem.
        if task.status in ("planned", "ready", "assigned"):
            task.status = "in_progress"
            if task.started_at is None:
                task.started_at = datetime.now(timezone.utc)

    source, delegation = authority
    audit_payload: dict[str, Any] = {
        "description": f"Task #{task.number} {'scheduled' if scheduled else 'dispatched'} to {agent.name} "
                       f"via Inbox #{demand.number}",
        # An unresolved JWT (no users row) is still a person; an in-process
        # caller (governance's auto-dispatch) is the system.
        "principal_type": principal.principal_type if principal else ("system" if source == "system" else "user"),
        "principal_id": str(principal.principal_id) if principal else None,
        "authority_source": source,
        "delegation_id": str(delegation.id) if delegation is not None else None,
        "idempotency_key": payload.idempotency_key,
        "demand_id": str(demand.id),
        "execution_id": str(execution.id),
        "scheduled_at": demand.scheduled_at.isoformat() if scheduled else None,
    }
    if context_manifest is not None:
        audit_payload["context_manifest"] = context_manifest
    db.add(
        AuditEvent(
            entity_type="project_task",
            entity_id=task.id,
            event_type="task.dispatched",
            actor=actor,
            payload=audit_payload,
        )
    )

    await db.commit()
    await db.refresh(demand)
    await db.refresh(task)
    return _dispatch_out(task, demand)

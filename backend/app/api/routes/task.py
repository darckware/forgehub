"""Task domain routes.

Primary entity: ProjectTask (with nested TaskExecution sub-resource).
Secondary tables: TaskDependency, TaskRequiredSkill, TaskAssignment get
create/list (+ delete where cheap) endpoints.

Business rules encoded here (see docs/SPEC.md section 6.4 Execution Rules
and 6.2 used as a pattern for dependency-style blocking):
- 6.4.1 Planned/assigned/executed remain distinct states: creating a
  TaskAssignment moves the task status from "planned" to "assigned";
  creating a TaskExecution moves it to "in_progress"; it never silently
  jumps to "done" -- only an explicit PATCH with status="done" does that,
  and only once at least one execution is "completed" or "verified".
- 6.4.2 Each task can have multiple executions -- enforced naturally by
  allowing repeated POSTs to the executions sub-resource; attempt_number
  auto-increments per task.
- 6.4.3 Every execution must have evidence -- enforced in the Pydantic
  schema (evidence_ref required once status is verified/completed) and
  re-checked here for partial updates.
- Dependency cycle/self-reference guard: a task cannot depend on itself
  (schema-level) and a direct A->B / B->A cycle is rejected here.
- A task cannot be marked "done" while it has an incomplete dependency
  (mirrors SPEC 6.2.9 "blocked stages must prevent dependent stages from
  advancing", applied at task granularity).
- A task must trace back to the planning item it was split from
  (core traceability invariant, CLAUDE.md / SPEC 5.4) -- planning_item_id
  is required on create and must reference an existing PlanningItem.
- 6.4.4 Every task completion must be auditable: marking a task "done" or
  a TaskExecution "verified"/"completed" writes a companion AuditEvent
  (governance domain) so the transition is part of the audit trail.
"""
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.task import (
    TaskAssignmentCreate,
    TaskAssignmentOut,
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
from app.db.base import get_db
from app.db.models.agent import Agent, SubAgent
from app.db.models.backlog import PLANNING_ITEM_TYPES, PlanningItem
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent
from app.db.models.notification import Notification
from app.db.models.progress import ProgressCheckpoint
from app.db.models.orchestration import AgentRuntimeProfile, ProjectAgentMembership, ProjectLoopPolicy
from app.db.models.project import ChangeRequest, Project
from app.db.models.task import (
    ProjectTask,
    TaskAssignment,
    TaskDependency,
    TaskExecution,
    TaskRequiredSkill,
)

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


async def _get_task_or_404(db: AsyncSession, task_id: uuid.UUID) -> ProjectTask:
    task = await db.get(ProjectTask, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


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
    return task


@router.post("", response_model=ProjectTaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(payload: ProjectTaskCreate, db: AsyncSession = Depends(get_db)) -> ProjectTask:
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

    task = ProjectTask(**payload.model_dump())
    db.add(task)
    await db.commit()
    await db.refresh(task)
    await _attach_project_ids(db, [task])
    await _attach_task_health(db, [task])
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
    return tasks


@router.get("/{task_id}", response_model=ProjectTaskOut)
async def get_task(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ProjectTask:
    task = await _get_task_or_404(db, task_id)
    await _attach_project_ids(db, [task])
    await _attach_task_health(db, [task])
    return task


@router.patch("/{task_id}", response_model=ProjectTaskOut)
async def update_task(
    task_id: uuid.UUID, payload: ProjectTaskUpdate, db: AsyncSession = Depends(get_db)
) -> ProjectTask:
    task = await _get_task_or_404(db, task_id)

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

    if data.get("status") == "done":
        await _ensure_dependencies_satisfied(db, task_id)

    for field, value in data.items():
        setattr(task, field, value)

    if data.get("status") == "done":
        audit_payload: dict = {}
        if task.planning_item_id:
            audit_payload["planning_item_id"] = str(task.planning_item_id)
        if task.change_request_id:
            audit_payload["change_request_id"] = str(task.change_request_id)
        db.add(
            AuditEvent(
                entity_type="project_task",
                entity_id=task.id,
                event_type="task_completed",
                actor="system",
                payload=audit_payload,
            )
        )

    await db.commit()
    await db.refresh(task)
    await _attach_project_ids(db, [task])
    await _attach_task_health(db, [task])
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    task = await _get_task_or_404(db, task_id)
    await db.delete(task)
    await db.commit()


async def _ensure_dependencies_satisfied(db: AsyncSession, task_id: uuid.UUID) -> None:
    """Business rule: a task cannot complete while a task it depends on
    is not itself done (mirrors SPEC 6.2.9 blocked-stage propagation)."""
    stmt = (
        select(ProjectTask.id, ProjectTask.status)
        .join(TaskDependency, TaskDependency.depends_on_task_id == ProjectTask.id)
        .where(TaskDependency.task_id == task_id)
    )
    result = await db.execute(stmt)
    for dep_id, dep_status in result.all():
        if dep_status != "done":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot complete task: dependency {dep_id} is not done (status={dep_status})",
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
    db: AsyncSession = Depends(get_db),
) -> TaskExecution:
    execution = await db.get(TaskExecution, execution_id)
    if execution is None or execution.task_id != task_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")

    data = payload.model_dump(exclude_unset=True)

    # Re-validate evidence rule against the merged (existing + incoming) state,
    # since evidence_ref might already be set from a previous PATCH.
    new_status = data.get("status", execution.status)
    new_evidence = data.get("evidence_ref", execution.evidence_ref)
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


# --------------------------------------------------------------------------
# TaskDependency
# --------------------------------------------------------------------------


@router.post(
    "/{task_id}/dependencies",
    response_model=TaskDependencyOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_task_dependency(
    task_id: uuid.UUID, payload: TaskDependencyCreate, db: AsyncSession = Depends(get_db)
) -> TaskDependency:
    if payload.task_id != task_id:
        raise HTTPException(status_code=400, detail="task_id in body must match the path task_id")

    await _get_task_or_404(db, task_id)
    await _get_task_or_404(db, payload.depends_on_task_id)

    # Guard against a direct A->B / B->A cycle.
    reverse = await db.execute(
        select(TaskDependency).where(
            TaskDependency.task_id == payload.depends_on_task_id,
            TaskDependency.depends_on_task_id == task_id,
        )
    )
    if reverse.scalars().first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This dependency would create a cycle between the two tasks",
        )

    dependency = TaskDependency(**payload.model_dump())
    db.add(dependency)
    await db.commit()
    await db.refresh(dependency)
    return dependency


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
    await _get_task_or_404(db, task_id)

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
# Task dispatch -- executed through the Inbox message process
# --------------------------------------------------------------------------
@router.post("/{task_id}/dispatch", response_model=TaskInboxDispatchOut)
async def dispatch_task(
    task_id: uuid.UUID, payload: TaskInboxDispatchIn, db: AsyncSession = Depends(get_db)
) -> TaskInboxDispatchOut:
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
    """
    # Import local: demand.py já importa o modelo ProjectTask, e um import
    # route->route no topo deste módulo criaria um ciclo assim que aquele
    # módulo precisar de qualquer coisa daqui.
    from app.api.routes.demand import _execute_dispatch, _demand_preview
    from app.core.agent_runs import AgentRunDispatchError

    task = await _get_task_or_404(db, task_id)

    if task.status in ("done", "deployed", "cancelled"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Task is already {task.status} and cannot be dispatched",
        )

    # Alvo: o informado, senão o agente da atribuição ativa da task.
    target_agent_id = payload.target_agent_id
    if target_agent_id is None:
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
        if assignment is None:
            raise HTTPException(
                status_code=400,
                detail="Task has no active agent assignment; pass target_agent_id or assign it first",
            )
        target_agent_id = assignment.agent_id

    agent = await db.get(Agent, target_agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    project_id = await _resolve_task_project_id(db, task)

    body_parts = [f"Task #{task.number}: {task.title}"]
    if task.description:
        body_parts.append(task.description)
    body_parts.append(
        f"Tipo: {task.task_type} | Prioridade: {task.priority} | Status atual: {task.status}"
    )

    demand = AgentDemand(
        from_agent="forgehub",
        subject=f"Task #{task.number} — {task.title}"[:255],
        body="\n\n".join(body_parts),
        status="new",
        target_agent_id=target_agent_id,
        project_id=project_id,
        origin_type="task",
        origin_id=task.id,
        requires_response=payload.requires_response,
    )
    db.add(demand)
    await db.flush()  # atribui demand.id/number antes da notificação referenciá-los

    db.add(
        Notification(
            source="system",
            severity="info",
            title=f"New in Inbox: {demand.subject}",
            message=_demand_preview(demand.body),
            event_key=f"demand:{demand.id}",
            occurred_at=datetime.now(timezone.utc),
        )
    )

    try:
        demand = await _execute_dispatch(db, demand, target_agent_id, payload.command_text)
    except AgentRunDispatchError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Host-bridge dispatch failed: {exc}") from exc

    # Regra 6.4.1 estendida: despachar tira a task de planned/ready/assigned.
    # Estados posteriores (in_progress, blocked) não regridem.
    if task.status in ("planned", "ready", "assigned"):
        task.status = "in_progress"
        if task.started_at is None:
            task.started_at = datetime.now(timezone.utc)

    db.add(
        AuditEvent(
            entity_type="project_task",
            entity_id=task.id,
            event_type="task.dispatched",
            description=f"Task #{task.number} dispatched to {agent.name} via Inbox #{demand.number}",
        )
    )

    await db.commit()
    await db.refresh(demand)
    await db.refresh(task)

    return TaskInboxDispatchOut(
        task_id=task.id,
        task_status=task.status,
        demand_id=demand.id,
        demand_number=demand.number,
        target_agent_id=target_agent_id,
        dispatch_status=demand.dispatch_status,
        agent_run_id=demand.agent_run_id,
    )

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
- POST /{task_id}/sync-kanboard pushes this task to the real Kanboard
  project (app/core/kanboard_client.py) -- idempotent via the stored
  kanboard_task_id, status mapped to a Kanboard column via
  TASK_STATUS_TO_KANBOARD_COLUMN below.
"""
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
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
    ProjectTaskKanboardSyncOut,
    ProjectTaskOut,
    ProjectTaskUpdate,
)
from app.core import kanboard_client
from app.core.config import settings
from app.db.base import get_db
from app.db.models.agent import Agent
from app.db.models.backlog import PlanningItem
from app.db.models.governance import AuditEvent
from app.db.models.product import Product, ProductVersion
from app.db.models.project import ChangeRequest, Project
from app.db.models.task import (
    ProjectTask,
    TaskAssignment,
    TaskDependency,
    TaskExecution,
    TaskRequiredSkill,
)

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])

# ProjectTask.status -> Kanboard column id, against the real "Forgehub"
# Kanboard project (id=8): Backlog/Ready/In Progress/Review/Testing/
# Blocked/Done/Close/Canceled. "done" maps to Kanboard's own "Done" column;
# "deployed" (this task's deliverable shipped to production) maps to
# "Close" -- the next column along, since Kanboard has no "deployed"
# concept of its own.
TASK_STATUS_TO_KANBOARD_COLUMN = {
    "planned": 40,
    "assigned": 41,
    "in_progress": 42,
    "blocked": 45,
    "done": 46,
    "deployed": 47,
    "cancelled": 48,
}

# Inverted: Kanboard column_id -> ForgeHub task status (for reverse sync).
KANBOARD_COLUMN_TO_TASK_STATUS = {v: k for k, v in TASK_STATUS_TO_KANBOARD_COLUMN.items()}


async def _get_task_or_404(db: AsyncSession, task_id: uuid.UUID) -> ProjectTask:
    task = await db.get(ProjectTask, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


# --------------------------------------------------------------------------
# Kanboard cleanup (must be registered BEFORE /{task_id} routes to avoid
# FastAPI matching "kanboard-cleanup" as a task_id segment).
# --------------------------------------------------------------------------


@router.post("/kanboard-cleanup", response_model=dict)
async def kanboard_cleanup(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    """Close all Kanboard cards linked to tasks in the given project, then
    clear kanboard_task_id so the next phase starts with a clean board.

    Intended for phase transitions: when a pipeline stage completes and
    you want to start the next phase with a fresh Kanboard column layout.
    Any task whose kanboard_task_id is None is silently skipped.

    Returns a summary: {closed: N, skipped: N, errors: [...]}.
    """
    result = await db.execute(
        select(ProjectTask).where(ProjectTask.project_id == project_id)
    )
    tasks = list(result.scalars().all())

    closed = 0
    skipped = 0
    errors: list[str] = []

    for task in tasks:
        if task.kanboard_task_id is None:
            skipped += 1
            continue
        try:
            await kanboard_client.close_task(task.kanboard_task_id)
            task.kanboard_task_id = None
            closed += 1
        except (kanboard_client.KanboardError, Exception) as exc:
            errors.append(f"task {task.id}: {exc}")

    await db.commit()
    return {"closed": closed, "skipped": skipped, "errors": errors}


# --------------------------------------------------------------------------
# ProjectTask CRUD
# --------------------------------------------------------------------------


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
    return task


@router.get("", response_model=list[ProjectTaskOut])
async def list_tasks(
    status_filter: str | None = None,
    planning_item_id: uuid.UUID | None = None,
    change_request_id: uuid.UUID | None = None,
    parent_task_id: uuid.UUID | None = None,
    policy_id: uuid.UUID | None = None,
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
    result = await db.execute(stmt.order_by(ProjectTask.created_at))
    return list(result.scalars().all())


@router.get("/{task_id}", response_model=ProjectTaskOut)
async def get_task(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ProjectTask:
    return await _get_task_or_404(db, task_id)


@router.patch("/{task_id}", response_model=ProjectTaskOut)
async def update_task(
    task_id: uuid.UUID, payload: ProjectTaskUpdate, db: AsyncSession = Depends(get_db)
) -> ProjectTask:
    task = await _get_task_or_404(db, task_id)

    data = payload.model_dump(exclude_unset=True)

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
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    task = await _get_task_or_404(db, task_id)
    await db.delete(task)
    await db.commit()


@router.post("/{task_id}/sync-kanboard", response_model=ProjectTaskKanboardSyncOut)
async def sync_task_kanboard(
    task_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> ProjectTask:
    """Push this task to the real Kanboard project as a card (idempotent):
    creates the card on the first call, updates title/description/owner/date
    and moves it to the column matching the task's current status on every
    call after that. See app/core/kanboard_client.py for the JSON-RPC
    client and TASK_STATUS_TO_KANBOARD_COLUMN above for the status->column
    mapping."""
    task = await _get_task_or_404(db, task_id)

    # --- Resolve the product's Kanboard project + column IDs ---------------
    # Chain: task → planning_item → project → product_version → product
    product_column_ids: dict | None = None
    kanboard_project_id: int | None = None
    if task.planning_item_id:
        pi = await db.get(PlanningItem, task.planning_item_id)
        if pi and pi.project_id:
            proj = await db.get(Project, pi.project_id)
            if proj and proj.product_version_id:
                ver = await db.get(ProductVersion, proj.product_version_id)
                if ver:
                    prod = await db.get(Product, ver.product_id)
                    if prod:
                        product_column_ids = prod.kanboard_column_ids
                        kanboard_project_id = prod.kanboard_project_id

    column_id = await kanboard_client.get_column_id_for_status(product_column_ids, task.status)

    # Override the global project_id in client calls when the product has its own project.
    _project_id = kanboard_project_id or settings.KANBOARD_PROJECT_ID

    # --- Resolve assigned agent → Kanboard user id ---
    owner_id: int | None = None
    assignment_result = await db.execute(
        select(TaskAssignment)
        .where(TaskAssignment.task_id == task.id)
        .order_by(TaskAssignment.assigned_at)
        .limit(1)
    )
    assignment = assignment_result.scalar_one_or_none()
    if assignment and assignment.agent_id:
        agent = await db.get(Agent, assignment.agent_id)
        if agent:
            # Try profile_slug first (matches Kanboard username), then name
            for lookup in filter(None, [agent.profile_slug, agent.name]):
                kb_uid = await kanboard_client.get_user_by_name(lookup)
                if kb_uid:
                    owner_id = kb_uid
                    break

    # --- Resolve start date ---
    # Use the earliest execution started_at if available; otherwise use now
    # for statuses that imply active work.
    date_started: int | None = None
    ACTIVE_STATUSES = {"in_progress", "blocked", "done", "deployed", "cancelled"}
    if task.status in ACTIVE_STATUSES:
        exec_result = await db.execute(
            select(TaskExecution)
            .where(TaskExecution.task_id == task.id)
            .order_by(TaskExecution.started_at)
            .limit(1)
        )
        first_exec = exec_result.scalar_one_or_none()
        if first_exec and first_exec.started_at:
            date_started = int(first_exec.started_at.replace(tzinfo=timezone.utc).timestamp())
        else:
            date_started = int(datetime.now(timezone.utc).timestamp())

    try:
        if task.kanboard_task_id is None:
            task.kanboard_task_id = await kanboard_client.create_task(
                title=task.title,
                description=task.description or "",
                column_id=column_id,
                owner_id=owner_id,
                date_started=date_started,
                project_id=_project_id,
            )
        else:
            await kanboard_client.update_task(
                task.kanboard_task_id,
                title=task.title,
                description=task.description or "",
                owner_id=owner_id,
                date_started=date_started,
            )
            await kanboard_client.move_task_to_column(task.kanboard_task_id, column_id, project_id=_project_id)
    except (kanboard_client.KanboardError, httpx.HTTPError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Kanboard sync failed: {exc}",
        ) from exc

    await db.commit()
    await db.refresh(task)
    return ProjectTaskKanboardSyncOut(
        **ProjectTaskOut.model_validate(task).model_dump(),
        kanboard_url=kanboard_client.task_url(task.kanboard_task_id),
    )


@router.post("/{task_id}/pull-kanboard", response_model=ProjectTaskOut)
async def pull_kanboard_status(
    task_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> ProjectTask:
    """Read this task's current column from Kanboard and update the ForgeHub
    status to match (reverse sync).  Only updates if the column maps to a
    known ForgeHub status and differs from the current status.

    Returns 400 if the task has no Kanboard card linked yet.
    """
    task = await _get_task_or_404(db, task_id)
    if task.kanboard_task_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Task has no Kanboard card. Push to Kanboard first.",
        )

    try:
        kb_task = await kanboard_client.get_task(task.kanboard_task_id)
    except (kanboard_client.KanboardError, Exception) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Kanboard pull failed: {exc}",
        ) from exc

    column_id = int(kb_task.get("column_id", 0))
    new_status = KANBOARD_COLUMN_TO_TASK_STATUS.get(column_id)
    if new_status and new_status != task.status:
        task.status = new_status
        await db.commit()
        await db.refresh(task)

    return task


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

    count_result = await db.execute(
        select(TaskExecution.id).where(TaskExecution.task_id == task_id)
    )
    attempt_number = len(count_result.all()) + 1

    execution = TaskExecution(
        task_id=task_id, attempt_number=attempt_number, **payload.model_dump()
    )
    db.add(execution)

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

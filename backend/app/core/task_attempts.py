"""Canonical attempt allocation shared by dispatch and answer continuation."""
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select

from app.core.demand_workflow import WorkflowBlocked
from app.db.models.task import ProjectTask, TaskExecution


async def create_task_attempt(db, task_id: UUID, assignment_id: UUID | None,
                              *, started_at: datetime | None = None) -> TaskExecution:
    # Serialize numbering with every caller; no runtime is started here.
    from app.core.dispatch_targets import DISPATCH_ADMISSION_LOCK
    await db.execute(select(func.pg_advisory_xact_lock(DISPATCH_ADMISSION_LOCK)))
    task = await db.scalar(select(ProjectTask).where(ProjectTask.id == task_id).with_for_update()
                           .execution_options(populate_existing=True))
    if task is None or task.status in {"done", "deployed", "cancelled"}:
        raise WorkflowBlocked("A closed or unavailable task cannot create another execution attempt")
    highest = await db.scalar(select(func.max(TaskExecution.attempt_number)).where(TaskExecution.task_id == task_id))
    execution = TaskExecution(task_id=task_id, assignment_id=assignment_id,
        attempt_number=(highest or 0) + 1, executor_type="agent",
        status="running" if started_at else "pending", started_at=started_at)
    db.add(execution)
    await db.flush()
    return execution

"""Proactive detection of ProjectTasks that silently missed their deadline
or stalled mid-execution -- closing a gap found 2026-07-25 while reviewing
the Task domain: `ProjectTask.planned_end_date` and
`TaskExecution.status="failed"` both already exist in the schema, but
nothing ever proactively checked them. A task could blow past its deadline
without ever starting, or a CLI run could die mid-execution, and nothing
told anyone -- `status="failed"` only produced a `ProgressCheckpoint` row
(api/routes/task.py's `_record_execution_lifecycle_checkpoint`), never a
`Notification` (unlike progress.py's own checkpoint routes, which do
via `_notify_checkpoint`).

Three health states, on top of "ok":
- "failed": latest TaskExecution.status == "failed". Notified immediately
  at the point of transition (see task.py's `_record_execution_lifecycle_
  checkpoint`) -- this module doesn't re-notify it, only surfaces it in
  `compute_health_map` for display.
- "overdue": planned_end_date has passed and no TaskExecution was ever
  created -- the task never even started.
- "stalled": latest TaskExecution stuck in pending/running for longer than
  STALLED_EXECUTION_GRACE with no update (the "heartbeat lost" case
  `db/models/progress.py`'s CHECKPOINT_TYPES already names but nothing
  ever detected).

"overdue"/"stalled" are proactive by nature (nothing transitions them),
so `run_task_failure_pass` (polled by main.py's `_task_failure_poll_loop`,
same pattern as demand.py's `run_scheduled_dispatch_pass`) periodically
scans every non-terminal task and notifies once per occurrence (dedup via
Notification.event_key, same pattern as progress.py's `_notify_checkpoint`).
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.notification import Notification
from app.db.models.task import ProjectTask, TaskExecution

logger = logging.getLogger(__name__)

# How long a TaskExecution can sit in pending/running with no update before
# counting as stalled. Generous on purpose -- a real in-progress task can
# legitimately run for hours; this is for "nothing has touched this in a
# day", not normal execution latency.
STALLED_EXECUTION_GRACE = timedelta(hours=24)

TERMINAL_TASK_STATUSES = {"done", "deployed", "cancelled"}

IN_FLIGHT_EXECUTION_STATUSES = {"pending", "running"}


async def compute_health_map(db: AsyncSession, tasks: list[ProjectTask]) -> dict[uuid.UUID, str]:
    """Batched -- one query for every task's latest execution instead of
    N+1, same discipline as routes/task.py's `_attach_project_ids`. Returns
    every task's id mapped to "ok"/"overdue"/"stalled"/"failed"."""
    non_terminal = [t for t in tasks if t.status not in TERMINAL_TASK_STATUSES]
    health: dict[uuid.UUID, str] = {t.id: "ok" for t in tasks if t.status in TERMINAL_TASK_STATUSES}
    if not non_terminal:
        return health

    task_ids = [t.id for t in non_terminal]
    rows = (
        await db.execute(
            select(TaskExecution.task_id, TaskExecution.status, TaskExecution.attempt_number, TaskExecution.updated_at)
            .where(TaskExecution.task_id.in_(task_ids))
        )
    ).all()
    latest_by_task: dict[uuid.UUID, tuple[str, int, datetime]] = {}
    for row in rows:
        current = latest_by_task.get(row.task_id)
        if current is None or row.attempt_number > current[1]:
            latest_by_task[row.task_id] = (row.status, row.attempt_number, row.updated_at)

    now = datetime.now(timezone.utc)
    for task in non_terminal:
        latest = latest_by_task.get(task.id)
        if latest is not None:
            status, _, updated_at = latest
            if status == "failed":
                health[task.id] = "failed"
            elif status in IN_FLIGHT_EXECUTION_STATUSES and (now - updated_at) > STALLED_EXECUTION_GRACE:
                health[task.id] = "stalled"
            else:
                health[task.id] = "ok"
        elif task.planned_end_date is not None and task.planned_end_date < now.date():
            health[task.id] = "overdue"
        else:
            health[task.id] = "ok"
    return health


async def _notify_once(db: AsyncSession, *, event_key: str, title: str, message: str) -> None:
    """Same dedupe-by-event_key pattern as progress.py's _notify_checkpoint
    and demand.py's run_scheduled_dispatch_pass -- select first, insert
    only if this exact failure hasn't already been reported."""
    exists = (
        await db.execute(select(Notification.id).where(Notification.event_key == event_key))
    ).scalar_one_or_none()
    if exists:
        return
    db.add(
        Notification(
            source="system",
            severity="warning",
            title=title,
            message=message,
            event_key=event_key,
            occurred_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()


async def run_task_failure_pass(db: AsyncSession) -> None:
    """Polled by main.py's _task_failure_poll_loop. Only handles the two
    silent modes (overdue/stalled) -- explicit "failed" is already
    notified immediately at the point of transition, see this module's
    docstring."""
    result = await db.execute(select(ProjectTask).where(ProjectTask.status.notin_(TERMINAL_TASK_STATUSES)))
    tasks = list(result.scalars().all())
    health = await compute_health_map(db, tasks)
    for task in tasks:
        state = health.get(task.id, "ok")
        try:
            if state == "overdue":
                await _notify_once(
                    db,
                    event_key=f"task-overdue:{task.id}",
                    title=f"Task overdue: {task.title}",
                    message=f"Task #{task.number} passed its planned end date "
                    f"({task.planned_end_date}) with no execution ever recorded.",
                )
            elif state == "stalled":
                await _notify_once(
                    db,
                    event_key=f"task-stalled:{task.id}",
                    title=f"Task stalled: {task.title}",
                    message=f"Task #{task.number} has an execution stuck pending/running "
                    f"for over {int(STALLED_EXECUTION_GRACE.total_seconds() // 3600)}h.",
                )
        except Exception:
            await db.rollback()
            logger.exception("Task failure notification failed for task %s", task.id)

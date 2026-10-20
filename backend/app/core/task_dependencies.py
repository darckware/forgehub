"""Shared finish-to-start gate for task execution and completion."""
import uuid

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.task import ProjectTask, TaskDependency


class TaskDependenciesBlocked(HTTPException):
    def __init__(self, blocking: list[dict]) -> None:
        super().__init__(status_code=409, detail={
            "message": "Task has unfinished dependencies and cannot be executed or completed yet",
            "blocking": blocking,
        })


async def blocking_task_dependencies(db: AsyncSession, task_id: uuid.UUID) -> list[dict]:
    rows = (await db.execute(
        select(TaskDependency.depends_on_task_id, ProjectTask.number, ProjectTask.title, ProjectTask.status)
        .outerjoin(ProjectTask, ProjectTask.id == TaskDependency.depends_on_task_id)
        .where(
            TaskDependency.task_id == task_id,
            or_(ProjectTask.status.is_(None), ProjectTask.status.notin_(("done", "deployed"))),
        )
        .order_by(TaskDependency.depends_on_task_id)
    )).all()
    return [
        {"task_id": str(dep_id), "task_number": number, "title": title, "status": state or "missing"}
        for dep_id, number, title, state in rows
    ]


async def ensure_task_dependencies_satisfied(db: AsyncSession, task_id: uuid.UUID) -> None:
    blocking = await blocking_task_dependencies(db, task_id)
    if blocking:
        raise TaskDependenciesBlocked(blocking)

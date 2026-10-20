"""Resolves the default agent owner for a task by category (`task_type`),
optionally scoped to a project -- layered task-execution governance, Fase 2
(plan: resilient-twirling-blossom). See db/models/task.py's
`ResponsibilityArea` docstring for the full rationale; this module is just
the (task_type, project_id) -> owner_agent_id lookup, kept separate from
api/routes/task.py so `_dispatch_task_by_id` doesn't need to import route-
layer CRUD helpers to use it.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.task import ResponsibilityArea


async def resolve_responsibility_owner(
    db: AsyncSession, task_type: str, project_id: uuid.UUID | None
) -> uuid.UUID | None:
    """Exact (task_type, project_id) match first, falling back to the
    global default (task_type, project_id=NULL). Returns None when neither
    exists -- the caller decides what "no owner resolved" means (today,
    _dispatch_task_by_id still requires an explicit target/assignment)."""
    if project_id is not None:
        scoped = (
            await db.execute(
                select(ResponsibilityArea.owner_agent_id).where(
                    ResponsibilityArea.task_type == task_type,
                    ResponsibilityArea.project_id == project_id,
                )
            )
        ).scalar_one_or_none()
        if scoped is not None:
            return scoped
    return (
        await db.execute(
            select(ResponsibilityArea.owner_agent_id).where(
                ResponsibilityArea.task_type == task_type,
                ResponsibilityArea.project_id.is_(None),
            )
        )
    ).scalar_one_or_none()

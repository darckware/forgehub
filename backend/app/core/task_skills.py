"""A task's required skills: one store, `task_required_skills` (M0.2b, DT-M0-1).

M0.0 had added `project_tasks.required_skill_ids` beside the existing
`task_required_skills` table the task screen already used; the two could
disagree. The table won (it carries `is_mandatory`/`minimum_proficiency` and a
real FK to `skills`). The task API keeps `required_skill_ids` as a view of the
**mandatory** rows: reading attaches it, writing replaces the mandatory set
(an optional row named in the list becomes mandatory; optional rows are
otherwise left alone). The mission P2 check (core/mission.py) reads the same
mandatory rows.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.task import ProjectTask, TaskRequiredSkill


async def required_skill_map(db: AsyncSession, task_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, list[uuid.UUID]]:
    """task id -> its mandatory skill ids (in the order they were required)."""
    ids = list(dict.fromkeys(task_ids))
    result: dict[uuid.UUID, list[uuid.UUID]] = {task_id: [] for task_id in ids}
    if not ids:
        return result
    rows = await db.execute(
        select(TaskRequiredSkill.task_id, TaskRequiredSkill.skill_id)
        .where(TaskRequiredSkill.task_id.in_(ids), TaskRequiredSkill.is_mandatory.is_(True))
        .order_by(TaskRequiredSkill.created_at, TaskRequiredSkill.id)
    )
    for task_id, skill_id in rows:
        result[task_id].append(skill_id)
    return result


async def attach_required_skill_ids(db: AsyncSession, tasks: list[ProjectTask]) -> None:
    """Populate the transient `required_skill_ids` ProjectTaskOut reads,
    batched like routes/task.py's _attach_project_ids."""
    skills = await required_skill_map(db, [t.id for t in tasks])
    for task in tasks:
        task.required_skill_ids = skills.get(task.id, [])


async def replace_required_skills(db: AsyncSession, task_id: uuid.UUID, skill_ids: list[uuid.UUID]) -> None:
    """Make `skill_ids` the task's mandatory set. Caller validates and commits."""
    wanted = list(dict.fromkeys(skill_ids))
    rows = {r.skill_id: r for r in (await db.execute(
        select(TaskRequiredSkill).where(TaskRequiredSkill.task_id == task_id)
    )).scalars()}
    for skill_id, row in rows.items():
        if row.is_mandatory and skill_id not in wanted:
            await db.delete(row)
    for skill_id in wanted:
        row = rows.get(skill_id)
        if row is None:
            db.add(TaskRequiredSkill(task_id=task_id, skill_id=skill_id, is_mandatory=True))
        elif not row.is_mandatory:
            row.is_mandatory = True

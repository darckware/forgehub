"""Immutable mission baselines (Plano Integrado M0.6b).

Contract: docs/architecture/MCP_MISSION_TOOLS_SPEC.md §4.2. A baseline freezes
one content hash per task (`plan_baseline_items`); the dispatch guard
(`core/task_baseline_guard.py`) recomputes it before every run. Nothing here
updates an existing baseline: a new one supersedes the previous one.

The hash covers exactly the §4.2 fields. The assignee is deliberately out
(D-M0-3: reassigning a baselined task needs no change request), and so are
status, dates and costs. The mission-level part (brief version and criteria)
is inside every item hash, so editing the brief or a criterion invalidates the
authorization of every task, not only the baseline's aggregate hash.

`create_mission_baseline` is the core the governed plan approval (M0.2b) calls;
until then only the tests call it. Caller commits.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.core.governed_approval import canonical_hash
from app.db.models.artifact import ArtifactVersion
from app.db.models.governance import AuditEvent
from app.db.models.mission import MissionAcceptanceCriterion, MissionCriterionTask, ProjectMission
from app.db.models.project import PlanBaseline, PlanBaselineItem, ProjectPlan
from app.db.models.task import ProjectTask, TaskDependency, TaskExecutionTarget


class BaselineCreationError(ValueError):
    """The requested baseline would not be a valid authorization."""


async def mission_content_part(db, mission: ProjectMission) -> dict[str, Any]:
    """Brief version + criteria set: the mission-level part of every hash."""
    brief_version_id = None
    if mission.brief_artifact_id is not None:
        brief_version_id = (await db.execute(
            select(ArtifactVersion.id)
            .where(ArtifactVersion.artifact_id == mission.brief_artifact_id)
            .order_by(ArtifactVersion.version_number.desc())
            .limit(1)
        )).scalar_one_or_none()
    criteria = (await db.execute(
        select(MissionAcceptanceCriterion)
        .where(MissionAcceptanceCriterion.mission_project_id == mission.project_id)
    )).scalars().all()
    return {
        "brief_artifact_id": mission.brief_artifact_id,
        "brief_artifact_version_id": brief_version_id,
        "criteria": sorted(
            [
                c.code, c.statement, c.verification_method,
                "marcelo" if c.verifier_is_marcelo else str(c.verifier_agent_id),
            ]
            for c in criteria
        ),
    }


async def task_content_part(db, task: ProjectTask) -> dict[str, Any]:
    depends_on = (await db.execute(
        select(TaskDependency.depends_on_task_id).where(TaskDependency.task_id == task.id)
    )).scalars().all()
    targets = (await db.execute(
        select(TaskExecutionTarget.kind, TaskExecutionTarget.target_key)
        .where(TaskExecutionTarget.task_id == task.id)
    )).all()
    criterion_codes = (await db.execute(
        select(MissionAcceptanceCriterion.code)
        .join(MissionCriterionTask, MissionCriterionTask.criterion_id == MissionAcceptanceCriterion.id)
        .where(MissionCriterionTask.task_id == task.id)
    )).scalars().all()
    return {
        "task_id": task.id,
        "title": task.title,
        "description": task.description,
        "plan_brief": task.plan_brief,
        "task_type": task.task_type,
        "priority": task.priority,
        "planning_item_id": task.planning_item_id,
        "change_request_id": task.change_request_id,
        "parent_task_id": task.parent_task_id,
        "depends_on_task_ids": sorted(str(d) for d in depends_on),
        "execution_targets": sorted(f"{kind}:{key}" for kind, key in targets),
        "criterion_codes": sorted(criterion_codes),
        # M0.0b (§2.6): the environment approved with the plan.
        "target_environment": task.target_environment,
        "environment_prerequisites": (
            None if task.environment_prerequisites is None else list(task.environment_prerequisites)
        ),
    }


async def task_content_hash(db, task: ProjectTask, mission_part: dict[str, Any]) -> str:
    return canonical_hash({"task": await task_content_part(db, task), "mission": mission_part})


def baseline_content_hash(item_hashes: list[str], mission_part: dict[str, Any]) -> str:
    return canonical_hash({"items": sorted(item_hashes), "mission": mission_part})


async def create_mission_baseline(
    db,
    mission: ProjectMission,
    plan: ProjectPlan,
    task_ids: list[uuid.UUID],
    *,
    name: str,
    actor: str,
) -> PlanBaseline:
    """Freeze `task_ids` into a new baseline of `mission` and supersede the
    current one (§4.2). `plan` must be the mission's own, already approved
    plan. Every task must be in the mission's scope (its own tasks or those
    of a linked executor project)."""
    from app.core.mission import executor_project_ids, mission_tasks

    if plan.project_id != mission.project_id:
        raise BaselineCreationError("The plan belongs to another project")
    if plan.status != "approved":
        raise BaselineCreationError(f"Only an approved plan can be baselined (current status: '{plan.status}')")
    wanted = list(dict.fromkeys(task_ids))
    if not wanted:
        raise BaselineCreationError("A mission baseline needs at least one task")
    scope = {t.id: t for t in await mission_tasks(db, mission.project_id)}
    for executor_id in await executor_project_ids(db, mission.project_id):
        scope.update({t.id: t for t in await mission_tasks(db, executor_id)})
    outside = [str(t) for t in wanted if t not in scope]
    if outside:
        raise BaselineCreationError(f"Tasks outside the mission scope: {', '.join(outside)}")

    now = datetime.now(timezone.utc)
    mission_part = await mission_content_part(db, mission)
    item_hashes = {t: await task_content_hash(db, scope[t], mission_part) for t in wanted}
    baseline = PlanBaseline(
        project_plan_id=plan.id,
        name=name,
        scope_snapshot=plan.scope_summary,
        cost_snapshot=plan.estimated_cost,
        end_date_snapshot=plan.estimated_end_date,
        frozen_at=now,
        content_hash=baseline_content_hash(list(item_hashes.values()), mission_part),
    )
    db.add(baseline)
    await db.flush()
    db.add_all(PlanBaselineItem(baseline_id=baseline.id, task_id=t, content_hash=h) for t, h in item_hashes.items())

    previous_id = mission.current_baseline_id
    if previous_id is not None:
        previous = await db.get(PlanBaseline, previous_id)
        if previous is not None and previous.superseded_at is None:
            previous.superseded_at = now
            if previous.project_plan_id != plan.id:
                previous_plan = await db.get(ProjectPlan, previous.project_plan_id)
                if previous_plan is not None:
                    previous_plan.status = "superseded"
    plan.status = "baselined"
    mission.current_baseline_id = baseline.id
    mission.row_version += 1
    db.add(AuditEvent(
        entity_type="plan_baseline", entity_id=baseline.id, event_type="mission_baseline_created", actor=actor,
        payload={
            "mission_project_id": str(mission.project_id), "project_plan_id": str(plan.id),
            "content_hash": baseline.content_hash, "task_ids": [str(t) for t in wanted],
            "supersedes": str(previous_id) if previous_id else None,
        },
    ))
    await db.flush()
    return baseline

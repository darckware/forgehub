"""Dispatch guard: a mission task runs only as its current baseline froze it
(Plano Integrado M0.6b, docs/architecture/MCP_MISSION_TOOLS_SPEC.md §4.2).

`assert_task_baseline_current` is authoritative inside `reserve_dispatch`
(core/demand_dispatch_guard.py), which every path to the runner crosses; an
early call at the top of `_dispatch_task_by_id` only spares a TaskExecution
row for a refused dispatch. The refusal is a `WorkflowBlocked` (409), so the
scheduled pass keeps the item queued and consumes no attempt.

Scope: tasks of a mission project or of an executor project linked to one.
A common project is never blocked by an item-less (legacy) baseline; no route
creates items for a common project, so in M0 the guard does not apply there.
Inside a mission it fails closed: no current baseline is TASK_NOT_IN_BASELINE.
"""
from __future__ import annotations

from sqlalchemy import select

from app.core.demand_workflow import WorkflowBlocked
from app.db.models.mission import ProjectMission
from app.db.models.project import ChangeRequest, PlanBaseline, PlanBaselineItem, ProjectPlan
from app.db.models.task import ProjectTask

DISPATCHABLE_MISSION_STATES = ("active", "verifying")
TERMINAL_MISSION_STATES = ("completed", "cancelled")
# A CR that is not yet applied still has to produce the next baseline.
OPEN_CHANGE_REQUEST_STATUSES = ("pending", "approved")


class TaskBaselineBlocked(WorkflowBlocked):
    def __init__(self, code: str, message: str, task: ProjectTask, **extra):
        super().__init__({"code": code, "message": message, "task_id": str(task.id), **extra})
        self.code = code


async def task_missions(db, task: ProjectTask) -> list[ProjectMission]:
    """The missions a task is dispatched under (empty for a common project)."""
    from app.core.task_completion_guard import mission_project_ids_for, task_project

    project = await task_project(db, task)
    if project is None:
        return []
    ids = await mission_project_ids_for(db, project)
    if not ids:
        return []
    return list((await db.execute(
        select(ProjectMission).where(ProjectMission.project_id.in_(ids)).order_by(ProjectMission.created_at)
    )).scalars())


async def _governing_mission(db, task: ProjectTask, missions: list[ProjectMission]) -> ProjectMission:
    # An executor project may serve several missions: the one whose current
    # baseline froze this task governs it. Otherwise a non-terminal mission
    # refuses it (TASK_NOT_IN_BASELINE), and a closed one only when every
    # mission is closed -- a finished mission must not mask the real cause.
    for mission in missions:
        if mission.current_baseline_id is not None and await db.scalar(
            select(PlanBaselineItem.id).where(
                PlanBaselineItem.baseline_id == mission.current_baseline_id, PlanBaselineItem.task_id == task.id
            )
        ):
            return mission
    return next((m for m in missions if m.state not in TERMINAL_MISSION_STATES), missions[0])


async def assert_task_baseline_current(db, task: ProjectTask) -> None:
    from app.core.plan_baseline import mission_content_part, task_content_hash

    missions = await task_missions(db, task)
    if not missions:
        return
    mission = await _governing_mission(db, task, missions)
    mission_ref = {"mission_project_id": str(mission.project_id)}
    if mission.state not in DISPATCHABLE_MISSION_STATES:
        raise TaskBaselineBlocked(
            "MISSION_NOT_ACTIVE", f"The mission is {mission.state}; only an active or verifying mission dispatches",
            task, **mission_ref,
        )
    baseline = await db.get(PlanBaseline, mission.current_baseline_id) if mission.current_baseline_id else None
    if baseline is None:
        raise TaskBaselineBlocked("TASK_NOT_IN_BASELINE", "The mission has no approved baseline", task, **mission_ref)
    mission_ref["baseline_id"] = str(baseline.id)
    plan = await db.get(ProjectPlan, baseline.project_plan_id)
    if plan is None or plan.project_id != mission.project_id:
        raise TaskBaselineBlocked(
            "BASELINE_FOREIGN_PROJECT", "The mission cites a baseline of another project", task, **mission_ref
        )
    if baseline.superseded_at is not None:
        raise TaskBaselineBlocked(
            "BASELINE_SUPERSEDED", "The baseline cited by the mission was superseded", task, **mission_ref
        )
    if task.change_request_id is not None:
        change_request = await db.get(ChangeRequest, task.change_request_id)
        if change_request is not None and change_request.status in OPEN_CHANGE_REQUEST_STATUSES:
            raise TaskBaselineBlocked(
                "CHANGE_REQUEST_PENDING",
                f"Change request '{change_request.title}' is {change_request.status}, not applied; "
                "a new approved baseline must authorize this task", task,
                change_request_id=str(change_request.id), **mission_ref,
            )
    item = (await db.execute(
        select(PlanBaselineItem).where(PlanBaselineItem.baseline_id == baseline.id, PlanBaselineItem.task_id == task.id)
    )).scalar_one_or_none()
    if item is None:
        raise TaskBaselineBlocked(
            "TASK_NOT_IN_BASELINE",
            "The task is not in the mission's current baseline; it needs an applied change request and a new approval",
            task, **mission_ref,
        )
    if await task_content_hash(db, task, await mission_content_part(db, mission)) != item.content_hash:
        raise TaskBaselineBlocked(
            "TASK_CONTENT_CHANGED", "The task (or the mission brief/criteria) changed after the baseline was approved",
            task, **mission_ref,
        )

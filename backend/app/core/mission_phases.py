"""Mission phases (docs/architecture/MISSION_PHASES_PLAN.md, 2026-11-12).

A phase is a ``mission_project_links`` row: the mission's executor project at
``position`` N. Inside a phase, planning items may run in parallel and the
tasks of one planning item always run in sequence (``position`` 1..n plus the
finish_to_start chain). Phases run strictly in order: no task of phase N is
dispatched until every phase before N is ``approved``; each phase ends in a
homologation by an external, independent agent and Marcelo's approval.

This module only reads and checks; routes live in api/routes/mission_phase.py.
The dispatch gate (``assert_phase_dispatchable``) runs inside
``assert_task_baseline_current``, i.e. on every path to the runner, and
``mark_phase_started`` runs in ``reserve_dispatch`` once a dispatch is
admitted (the first one moves ``planned``/``returned`` to ``in_progress``).
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from app.db.models.agent import Agent
from app.db.models.backlog import PlanningItem
from app.db.models.mission import MissionProjectLink, ProjectMission
from app.db.models.project import Project
from app.db.models.task import ProjectTask, TaskAssignment, TaskDependency, TaskExecution

PHASE_EDITABLE_MISSION_STATES = ("draft", "planning")
# A phase in these states takes no new dispatch of its own tasks.
PHASE_CLOSED_STATUSES = ("homologating", "awaiting_approval", "approved")
PHASE_STARTABLE_STATUSES = ("planned", "returned")
TASK_DONE_STATUSES = ("done", "deployed")


def _item(code: str, message: str, **context: Any) -> dict[str, Any]:
    return {"code": code, "message": message, **context}


async def mission_phases(db, mission_project_id: uuid.UUID, *, lock: bool = False) -> list[MissionProjectLink]:
    """The mission's phases (``is_phase`` links only; a plain executor link
    is never a phase), in order."""
    stmt = (select(MissionProjectLink)
            .where(MissionProjectLink.mission_project_id == mission_project_id,
                   MissionProjectLink.is_phase.is_(True))
            .order_by(MissionProjectLink.position, MissionProjectLink.created_at))
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return list((await db.execute(stmt)).scalars())


def phases_frozen(mission: ProjectMission) -> bool:
    """Phases are part of the plan: editable only while draft/planning and
    before any baseline exists."""
    return mission.state not in PHASE_EDITABLE_MISSION_STATES or mission.current_baseline_id is not None


async def phase_hash_part(db, mission: ProjectMission) -> list[list[Any]]:
    """(position, name, objective, executor_project_id) per phase -- the
    phases' part of the plan hash. Empty when the mission has none, so a
    mission without phases keeps hashing exactly as before."""
    return [[p.position, p.name, p.objective, str(p.executor_project_id)]
            for p in await mission_phases(db, mission.project_id)]


async def project_planning_items(db, project_id: uuid.UUID) -> list[PlanningItem]:
    return list((await db.execute(
        select(PlanningItem).where(PlanningItem.project_id == project_id)
        .order_by(PlanningItem.position.asc().nulls_last(), PlanningItem.created_at)
    )).scalars())


async def item_tasks(db, planning_item_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[ProjectTask]]:
    result: dict[uuid.UUID, list[ProjectTask]] = {i: [] for i in planning_item_ids}
    if not planning_item_ids:
        return result
    for task in (await db.execute(
        select(ProjectTask).where(ProjectTask.planning_item_id.in_(planning_item_ids))
        .order_by(ProjectTask.position.asc().nulls_last(), ProjectTask.number)
    )).scalars():
        result[task.planning_item_id].append(task)
    return result


async def dependency_edges(db, task_ids: list[uuid.UUID]) -> set[tuple[uuid.UUID, uuid.UUID]]:
    if not task_ids:
        return set()
    return {(d.task_id, d.depends_on_task_id) for d in (await db.execute(
        select(TaskDependency).where(TaskDependency.task_id.in_(task_ids))
    )).scalars()}


def is_sequenced(tasks: list[ProjectTask], edges: set[tuple[uuid.UUID, uuid.UUID]]) -> bool:
    """Every non-cancelled task has a distinct position and each one depends
    on the previous (the full finish_to_start chain). One task or none is
    trivially sequenced."""
    live = [t for t in tasks if t.status != "cancelled"]
    if len(live) <= 1:
        return True
    if any(t.position is None for t in live) or len({t.position for t in live}) != len(live):
        return False
    ordered = sorted(live, key=lambda t: t.position)
    return all((ordered[i].id, ordered[i - 1].id) in edges for i in range(1, len(ordered)))


async def phase_plan_items(db, mission: ProjectMission) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The phase checks of the plan (draft_plan exit and submission).
    Returns (unmet, warnings): PHASES_MISSING, PHASE_OBJECTIVE_MISSING and
    TASKS_NOT_SEQUENCED are unmet; TASK_OUTSIDE_PHASE (a mission-level task
    while the mission has phases) is only a warning -- it is allowed."""
    from app.core.mission import mission_tasks

    phases = await mission_phases(db, mission.project_id)
    if not phases:
        return [_item("PHASES_MISSING", "The mission has no phase")], []
    unmet: list[dict[str, Any]] = []
    for phase in phases:
        ref = {"phase_id": str(phase.id), "phase_position": phase.position, "phase_name": phase.name}
        if not (phase.objective or "").strip():
            unmet.append(_item("PHASE_OBJECTIVE_MISSING", "The phase has no objective", **ref))
        if not any(t.status != "cancelled" for t in await mission_tasks(db, phase.executor_project_id)):
            # A phase with nothing to deliver could never be homologated.
            unmet.append(_item("PHASE_WITHOUT_TASKS", "The phase has no task", **ref))
        items = await project_planning_items(db, phase.executor_project_id)
        tasks_by_item = await item_tasks(db, [i.id for i in items])
        edges = await dependency_edges(db, [t.id for ts in tasks_by_item.values() for t in ts])
        for item in items:
            if not is_sequenced(tasks_by_item[item.id], edges):
                unmet.append(_item("TASKS_NOT_SEQUENCED",
                                   "The planning item's tasks have no complete sequence (tasks:sequence)",
                                   planning_item_id=str(item.id), planning_item_title=item.title, **ref))
    warnings = [
        _item("TASK_OUTSIDE_PHASE", "Mission-level task outside any phase", task_id=str(t.id),
              task_number=t.number)
        for t in await mission_tasks(db, mission.project_id) if t.status != "cancelled"
    ]
    return unmet, warnings


# ---------------------------------------------------------------------------
# Dispatch gate
# ---------------------------------------------------------------------------
async def _phase_of_task(db, task: ProjectTask, mission: ProjectMission) -> MissionProjectLink | None:
    from app.core.mission import project_id_for_task_source

    project_id = await project_id_for_task_source(db, task.planning_item_id, task.change_request_id)
    if project_id is None or project_id == mission.project_id:
        return None
    return (await db.execute(select(MissionProjectLink).where(
        MissionProjectLink.mission_project_id == mission.project_id,
        MissionProjectLink.executor_project_id == project_id,
        MissionProjectLink.is_phase.is_(True),
    ))).scalar_one_or_none()


async def phase_dispatch_refusal(db, task: ProjectTask, mission: ProjectMission) -> dict[str, Any] | None:
    """PHASE_LOCKED while an earlier phase is not approved; PHASE_CLOSED while
    the task's own phase is homologating, awaiting approval or approved."""
    phase = await _phase_of_task(db, task, mission)
    if phase is None:
        return None
    ref = {"phase_id": str(phase.id), "phase_position": phase.position, "phase_status": phase.phase_status}
    blocking = [p for p in await mission_phases(db, mission.project_id)
                if p.position < phase.position and p.phase_status != "approved"]
    if blocking:
        return {"code": "PHASE_LOCKED",
                "message": f"Phase {phase.position} waits for every earlier phase to be approved",
                "blocking_phases": [{"phase_id": str(p.id), "position": p.position, "name": p.name,
                                     "phase_status": p.phase_status} for p in blocking], **ref}
    if phase.phase_status in PHASE_CLOSED_STATUSES:
        return {"code": "PHASE_CLOSED",
                "message": f"Phase {phase.position} is {phase.phase_status}; its tasks take no new dispatch",
                **ref}
    return None


async def mark_phase_started(db, task: ProjectTask) -> None:
    """The first admitted dispatch of a phase task moves its phase from
    planned/returned to in_progress (called in reserve_dispatch, in the
    reservation's own transaction)."""
    from app.core.task_baseline_guard import _governing_mission, task_missions

    missions = await task_missions(db, task)
    if not missions:
        return
    mission = await _governing_mission(db, task, missions)
    phase = await _phase_of_task(db, task, mission)
    if phase is not None and phase.phase_status in PHASE_STARTABLE_STATUSES:
        phase.phase_status = "in_progress"


# ---------------------------------------------------------------------------
# Who executed and reviewed a phase (homologator independence)
# ---------------------------------------------------------------------------
async def phase_tasks(db, phase: MissionProjectLink) -> list[ProjectTask]:
    from app.core.mission import mission_tasks

    return await mission_tasks(db, phase.executor_project_id)


async def phase_participants(db, tasks: list[ProjectTask]) -> tuple[set[uuid.UUID], set[uuid.UUID]]:
    """(executor agent ids, reviewer agent ids) over every assignment,
    execution and review of the tasks -- current or past. A sub-agent counts
    as its parent agent, as in the completion guard (``_agent_identity``)."""
    from app.core.task_completion_guard import _agent_identity, resolve_executor_agent_id
    from app.db.models.orchestration import ProjectAgentMembership, TaskExecutionReview

    task_ids = [t.id for t in tasks]
    if not task_ids:
        return set(), set()
    executors: set[uuid.UUID] = set()
    for agent_id, sub_agent_id in (await db.execute(select(TaskAssignment.agent_id, TaskAssignment.sub_agent_id)
                                                    .where(TaskAssignment.task_id.in_(task_ids)))).all():
        identity = await _agent_identity(db, agent_id, sub_agent_id)
        if identity is not None:
            executors.add(identity)
    executions = list((await db.execute(select(TaskExecution).where(TaskExecution.task_id.in_(task_ids)))).scalars())
    for execution in executions:
        agent_id = await resolve_executor_agent_id(db, execution)
        if agent_id is not None:
            executors.add(agent_id)
    reviewers: set[uuid.UUID] = set()
    if executions:
        for agent_id, sub_agent_id in (await db.execute(
            select(ProjectAgentMembership.agent_id, ProjectAgentMembership.sub_agent_id)
            .join(TaskExecutionReview, TaskExecutionReview.reviewer_membership_id == ProjectAgentMembership.id)
            .where(TaskExecutionReview.execution_id.in_([e.id for e in executions]))
        )).all():
            identity = await _agent_identity(db, agent_id, sub_agent_id)
            if identity is not None:
                reviewers.add(identity)
    return executors, reviewers


# ---------------------------------------------------------------------------
# Read model (GET /missions/{id}/phases and the board's `phases`)
# ---------------------------------------------------------------------------
async def phases_view(db, mission: ProjectMission) -> list[dict[str, Any]]:
    phases = await mission_phases(db, mission.project_id)
    if not phases:
        return []
    projects = {p.id: p for p in (await db.execute(select(Project).where(
        Project.id.in_([ph.executor_project_id for ph in phases])))).scalars()}
    items_by_phase = {ph.id: await project_planning_items(db, ph.executor_project_id) for ph in phases}
    all_items = [i for items in items_by_phase.values() for i in items]
    tasks_by_item = await item_tasks(db, [i.id for i in all_items])
    all_tasks = [t for ts in tasks_by_item.values() for t in ts]
    task_ids = [t.id for t in all_tasks]
    edges = await dependency_edges(db, task_ids)
    numbers = {t.id: t.number for t in all_tasks}
    missing = {d for _, d in edges if d not in numbers}
    if missing:
        numbers.update({tid: n for tid, n in (await db.execute(
            select(ProjectTask.id, ProjectTask.number).where(ProjectTask.id.in_(missing)))).all()})
    assignees: dict[uuid.UUID, uuid.UUID] = {}
    if task_ids:
        for a in (await db.execute(select(TaskAssignment).where(
            TaskAssignment.task_id.in_(task_ids), TaskAssignment.status == "active",
            TaskAssignment.agent_id.is_not(None)).order_by(TaskAssignment.created_at))).scalars():
            assignees[a.task_id] = a.agent_id
    agent_ids = set(assignees.values()) | {ph.homologator_agent_id for ph in phases if ph.homologator_agent_id}
    agents = {a.id: a for a in (await db.execute(select(Agent).where(Agent.id.in_(agent_ids)))).scalars()} \
        if agent_ids else {}

    def iso(value):
        return value.isoformat() if value is not None else None

    out = []
    for ph in phases:
        project = projects.get(ph.executor_project_id)
        homologator = agents.get(ph.homologator_agent_id) if ph.homologator_agent_id else None
        out.append({
            "phase_id": str(ph.id), "position": ph.position, "name": ph.name, "objective": ph.objective,
            "phase_status": ph.phase_status,
            "executor_project_id": str(ph.executor_project_id),
            "executor_project_name": project.name if project else None,
            "homologator": {"agent_id": str(homologator.id), "name": homologator.name} if homologator else None,
            "homologation_demand_id": str(ph.homologation_demand_id) if ph.homologation_demand_id else None,
            "homologation_verdict": ph.homologation_verdict,
            "homologation_summary": ph.homologation_summary,
            "homologation_evidence": ph.homologation_evidence,
            "homologated_at": iso(ph.homologated_at),
            "decided_by": ph.decided_by, "decided_at": iso(ph.decided_at),
            "decision_reason": ph.decision_reason,
            "planning_items": [{
                "planning_item_id": str(item.id), "title": item.title, "position": item.position,
                "status": item.status,
                "sequenced": is_sequenced(tasks_by_item[item.id], edges),
                "tasks": [{
                    "task_id": str(t.id), "number": t.number, "title": t.title, "status": t.status,
                    "position": t.position,
                    "assignee_name": agents[assignees[t.id]].name if assignees.get(t.id) in agents else None,
                    "depends_on": sorted(numbers[d] for a, d in edges if a == t.id and d in numbers),
                } for t in tasks_by_item[item.id]],
            } for item in items_by_phase[ph.id]],
        })
    return out

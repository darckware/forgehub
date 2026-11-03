"""Mission executions board: the read-only aggregate behind the M0.7 screen.

Contract: docs/architecture/MISSION_EXECUTIONS_SCREEN_SPEC.md §3.2, §4, §4.1,
§4.2, §5, §6, §8. Routes in api/routes/mission_board.py.

The screen decides nothing (04 "Regras do pipeline" 5): this module only
reads. Each task's ``allowed_actions``/``blocked_actions`` are computed for
the caller by dry-running the same guard functions the action routes run
(``task_run_in_flight``, ``assert_task_baseline_current``, the dependency
gate, the mission assignment, target serialization, the dispatch capacity,
``assert_review_independent``) without taking any lock or writing a row. A
button the board lists as allowed still goes through its own route, which
runs those guards again; the board can only be stale, never a bypass.

Never a false all-clear: a source that could not be read (the git ancestry
check through the host-bridge, the planning conditions) is reported as
``unknown``/``unavailable``, not as "no conflict".
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.demand_workflow import WorkflowBlocked, requires_reconciliation
from app.core.deps import ActorPrincipal, authorize_action
from app.core.dispatch_targets import _first_holder, demand_targets, normalize_target_key, task_targets
from app.core.evidence_bridge import EvidenceUnverifiable, commit_is_integrated
from app.core.mission import ALLOWED_TRANSITIONS, executor_project_ids, mission_error, planning_exit_conditions
from app.core.mission_dispatch import OPEN_REVIEW_STATUSES, _hash, task_run_in_flight
from app.core.mission_plan import NON_EXECUTOR_ROLES, mission_scope_tasks
from app.core.mission_records import current_plan, plan_items
from app.core.task_baseline_guard import assert_task_baseline_current
from app.core.task_dependencies import blocking_task_dependencies
from app.core.task_skills import required_skill_map
from app.db.models.agent import Agent, AgentSkill, Skill
from app.db.models.demand import DISPATCH_MAX_ATTEMPTS, AgentDemand
from app.db.models.environment import ENVIRONMENTS
from app.db.models.governance import AuditEvent
from app.db.models.mission import (
    PLANNING_STAGES,
    MissionPlanReview,
    MissionReviewWaiver,
    ProjectMission,
)
from app.db.models.orchestration import ProjectAgentMembership, TaskExecutionReview
from app.db.models.project import PlanBaseline, PlanBaselineItem, Project, ProjectPlan
from app.db.models.task import ProjectTask, TaskAssignment, TaskDependency, TaskExecution, TaskExecutionTarget

DONE_STATUSES = ("done", "deployed")
TERMINAL_TASK_STATUSES = ("done", "deployed", "cancelled")
DECIDED_REVIEW_STATUSES = ("approved", "changes_requested", "rejected")
ACTIVE_MISSION_STATES = ("active", "verifying", "awaiting_acceptance")
# §8 default sort: the state group first (active work on top).
STATE_GROUP = {
    "active": 0, "verifying": 0, "awaiting_acceptance": 0,
    "ready": 1, "planning": 1, "paused": 2, "draft": 3, "completed": 4, "cancelled": 5,
}
ORCHESTRATE_ACTION = "mission.orchestrate"
ASSIGN_ACTION = "planning.execution.manage"
DISPATCH_ACTION = "planning.execution.manage"
READ_MODULE = "product"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _code_of(exc: Exception) -> tuple[str, str]:
    """(code, message) of a guard refusal, whatever form it raised."""
    detail = getattr(exc, "detail", None)
    if isinstance(exc, WorkflowBlocked) and not detail:
        detail = exc.args[0] if exc.args else str(exc)
    if isinstance(detail, dict):
        return str(detail.get("code") or "REFUSED"), str(detail.get("message") or "")
    text = str(detail if detail is not None else exc)
    if text.startswith("TARGET_BUSY"):
        return "TARGET_BUSY", text
    return "REFUSED", text


# ---------------------------------------------------------------------------
# Who reads (§3.2, §10)
# ---------------------------------------------------------------------------
async def _user_can_read(db: AsyncSession, principal: ActorPrincipal) -> bool:
    if principal.is_admin:
        return True
    if principal.profile_id is None:
        return False
    from app.db.models.profile import ProfilePermission

    perm = (await db.execute(select(ProfilePermission).where(
        ProfilePermission.profile_id == principal.profile_id, ProfilePermission.module == READ_MODULE,
    ))).scalar_one_or_none()
    return bool(perm is not None and perm.can_view)


async def _agent_member_of(db: AsyncSession, agent_id: uuid.UUID, mission: ProjectMission) -> bool:
    if mission.orchestrator_agent_id == agent_id:
        return True
    return bool(await db.scalar(select(ProjectAgentMembership.id).where(
        ProjectAgentMembership.project_id == mission.project_id,
        ProjectAgentMembership.agent_id == agent_id,
        ProjectAgentMembership.status == "active",
    ).limit(1)))


async def assert_can_read_board(db: AsyncSession, principal: ActorPrincipal, mission: ProjectMission) -> None:
    """Admin or a person with the `product` module; an agent only where it is
    the orchestrator or an active member (else the same 404 as a missing
    mission). A person without the module is 403."""
    if principal.principal_type == "user":
        if not await _user_can_read(db, principal):
            raise mission_error(403, "PERMISSION_DENIED", "Reading missions needs the product module")
        return
    if not await _agent_member_of(db, principal.principal_id, mission):
        raise mission_error(404, "MISSION_NOT_FOUND", "Mission not found")


async def assert_can_list(db: AsyncSession, principal: ActorPrincipal) -> None:
    if principal.principal_type == "user" and not await _user_can_read(db, principal):
        raise mission_error(403, "PERMISSION_DENIED", "Reading missions needs the product module")


# ---------------------------------------------------------------------------
# Actor capability for actions (dry-run of each route's authorization)
# ---------------------------------------------------------------------------
class _Actor:
    """What the caller may do at all, before any per-task guard."""

    def __init__(self, db: AsyncSession, principal: ActorPrincipal, mission: ProjectMission):
        self.db = db
        self.principal = principal
        self.mission = mission
        self._cache: dict[tuple[str, uuid.UUID], str | None] = {}

    @property
    def is_marcelo(self) -> bool:
        return self.principal.principal_type == "user" and self.principal.is_admin

    async def refusal(self, action: str, delegation: str, project_ids: list[uuid.UUID], *,
                      needs_tools: bool = True, orchestrator_only: bool = False) -> str | None:
        """None when the caller passes the route's authorization, else the
        refusal code the route would answer."""
        principal = self.principal
        if principal.principal_type == "user":
            if not principal.is_admin:
                return "MISSION_ADMIN_ONLY"
            if needs_tools and not settings.MISSION_TOOLS_ENABLED:
                return "MISSION_TOOLS_DISABLED"
            return None
        if not settings.MISSION_TOOLS_ENABLED:
            return "MISSION_TOOLS_DISABLED"
        if orchestrator_only and principal.principal_id != self.mission.orchestrator_agent_id:
            return "MISSION_ACTOR_NOT_ALLOWED"
        for project_id in dict.fromkeys(project_ids):
            key = (delegation, project_id)
            if key not in self._cache:
                try:
                    await authorize_action(self.db, principal, delegation, project_id=project_id)
                    self._cache[key] = None
                except HTTPException as exc:
                    if exc.status_code != 403:
                        raise
                    self._cache[key] = "DELEGATION_REQUIRED"
            if self._cache[key] is None:
                return None
        return "DELEGATION_REQUIRED"


def _blocked(action: str, code: str, message: str = "", **extra: Any) -> dict[str, Any]:
    return {"action": action, "reason": code, "message": message, **extra}


# ---------------------------------------------------------------------------
# Topological order (§1 point 1)
# ---------------------------------------------------------------------------
def topo_order(tasks: list[ProjectTask], edges: list[tuple[uuid.UUID, uuid.UUID]]) -> list[ProjectTask]:
    """Kahn's order (a task after what it depends on), ties by number; a
    cycle's members go last, by number, so nothing disappears."""
    by_id = {t.id: t for t in tasks}
    incoming: dict[uuid.UUID, set[uuid.UUID]] = {t.id: set() for t in tasks}
    for task_id, depends_on in edges:
        if task_id in by_id and depends_on in by_id and task_id != depends_on:
            incoming[task_id].add(depends_on)
    ordered: list[ProjectTask] = []
    remaining = dict(incoming)
    while remaining:
        ready = sorted((by_id[t] for t, deps in remaining.items() if not deps), key=lambda t: (t.number or 0))
        if not ready:
            ordered.extend(sorted((by_id[t] for t in remaining), key=lambda t: (t.number or 0)))
            break
        for task in ready:
            ordered.append(task)
            remaining.pop(task.id)
        done = {t.id for t in ready}
        for deps in remaining.values():
            deps.difference_update(done)
    return ordered


# ---------------------------------------------------------------------------
# Execution state (§4)
# ---------------------------------------------------------------------------
def execution_state(
    task: ProjectTask,
    *,
    execution: TaskExecution | None,
    review: TaskExecutionReview | None,
    approved_independent: bool,
    demand: AgentDemand | None,
    returned_after_execution: bool,
    evidence_failed: bool,
    blocking_deps: list[dict],
    ready: bool,
    now: datetime,
) -> str:
    """One value per task, first matching rule wins (§4 precedence)."""
    if task.status == "cancelled":
        return "cancelled"
    if task.status in DONE_STATUSES:
        if execution is not None and execution.status in ("verified", "completed") and approved_independent:
            return "done_proven"
        return "done_historical"
    if demand is not None:
        if requires_reconciliation(demand):
            return "uncertain"
        if demand.dispatch_status in ("dispatched", "running") or (
            demand.dispatch_status is None and demand.agent_run_id
        ):
            return "running"
        if demand.dispatch_status is None and demand.status != "archived":
            if demand.scheduled_at is not None and demand.scheduled_at > now:
                return "scheduled"
            return "queued"
    if review is not None and review.status in ("changes_requested", "rejected"):
        return "changes_requested"
    if returned_after_execution:
        return "changes_requested"
    if execution is not None and execution.status == "verified":
        return "awaiting_review"
    if execution is not None and execution.status == "failed" and evidence_failed:
        return "evidence_failed"
    if execution is not None and execution.status == "reported":
        return "reported"
    if demand is not None and demand.dispatch_status == "failed":
        return "failed"
    if task.status == "blocked" or blocking_deps:
        return "blocked"
    return "ready" if ready else "not_ready"


# ---------------------------------------------------------------------------
# Board
# ---------------------------------------------------------------------------
async def _agents(db: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, Agent]:
    ids = {i for i in ids if i is not None}
    if not ids:
        return {}
    return {a.id: a for a in (await db.execute(select(Agent).where(Agent.id.in_(ids)))).scalars()}


def _agent_ref(agents: dict[uuid.UUID, Agent], agent_id: uuid.UUID | None) -> dict[str, Any] | None:
    if agent_id is None:
        return None
    agent = agents.get(agent_id)
    return {"agent_id": str(agent_id), "name": agent.name if agent else str(agent_id)[:8]}


def _manifest_version(manifest: list[dict[str, Any]] | None) -> str | None:
    if not manifest:
        return None
    return hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()[:12]


def _git_ref(refs: list[str]) -> str | None:
    for ref in refs:
        if ref.startswith("git:"):
            return ref[4:].strip().lower() or None
    return None


async def _task_project_ids(db: AsyncSession, tasks: list[ProjectTask]) -> dict[uuid.UUID, uuid.UUID | None]:
    from app.core.mission import project_id_for_task_source

    out: dict[uuid.UUID, uuid.UUID | None] = {}
    cache: dict[tuple, uuid.UUID | None] = {}
    for task in tasks:
        key = (task.planning_item_id, task.change_request_id)
        if key not in cache:
            cache[key] = await project_id_for_task_source(db, task.planning_item_id, task.change_request_id)
        out[task.id] = cache[key]
    return out


async def _in_flight_items(db: AsyncSession) -> list[AgentDemand]:
    """Every task demand in flight, reserved, uncertain or queued, across all
    missions and common projects (§5: the 28/10 incident was outside any
    mission)."""
    return list((await db.execute(
        select(AgentDemand).where(
            AgentDemand.origin_type == "task", AgentDemand.origin_id.is_not(None),
            or_(
                AgentDemand.dispatch_status.in_(("dispatched", "running")),
                AgentDemand.agent_run_id.is_not(None) & AgentDemand.dispatch_status.is_(None),
                (AgentDemand.dispatch_status.is_(None)) & (AgentDemand.status != "archived"),
                (AgentDemand.dispatch_status == "failed") & AgentDemand.agent_run_id.is_not(None),
            ),
        ).order_by(AgentDemand.created_at)
    )).scalars())


CONFLICT_KIND = {"worktree": "same_worktree", "branch": "same_branch", "publish": "same_publish_target"}


async def _target_conflicts(db: AsyncSession, scope_ids: set[uuid.UUID]) -> list[dict[str, Any]]:
    """same_worktree / same_branch / same_publish_target between two distinct
    tasks with work in flight or queued, at least one of them in this mission."""
    holders: dict[str, dict[uuid.UUID, AgentDemand]] = {}
    for demand in await _in_flight_items(db):
        if demand.dispatch_status == "failed" and not requires_reconciliation(demand):
            continue
        for target in await demand_targets(db, demand):
            holders.setdefault(target, {}).setdefault(demand.origin_id, demand)
    conflicts = []
    for target, by_task in sorted(holders.items()):
        if len(by_task) < 2 or not (set(by_task) & scope_ids):
            continue
        kind, _, key = target.partition(":")
        task_rows = (await db.execute(select(ProjectTask.id, ProjectTask.number).where(
            ProjectTask.id.in_(list(by_task))))).all()
        numbers = {tid: num for tid, num in task_rows}
        conflicts.append({
            "kind": CONFLICT_KIND.get(kind, kind), "severity": "blocking", "target": key,
            "task_ids": [str(t) for t in by_task], "tasks": sorted(numbers.get(t) or 0 for t in by_task),
            "outside_mission": sorted(numbers.get(t) or 0 for t in by_task if t not in scope_ids),
            "detail": f"{kind} {key} is held or queued by " + ", ".join(
                f"#{numbers.get(t)} (Messages #{d.number})" for t, d in by_task.items()),
        })
    return conflicts


async def build_board(
    db: AsyncSession, project: Project, mission: ProjectMission, principal: ActorPrincipal, *,
    check_git: bool = True, include_planning: bool = True, now: datetime | None = None,
) -> dict[str, Any]:
    from app.api.routes.environment import latest_releases
    from app.api.routes.orchestration import assert_review_independent

    now = now or _now()
    actor = _Actor(db, principal, mission)
    scope = await mission_scope_tasks(db, mission.project_id)
    tasks = list(scope.values())
    task_ids = [t.id for t in tasks]
    scope_ids = set(task_ids)
    task_project = await _task_project_ids(db, tasks)
    projects = {p.id: p for p in (await db.execute(select(Project).where(
        Project.id.in_({pid for pid in task_project.values() if pid} | {mission.project_id})))).scalars()}

    edges = list((await db.execute(select(TaskDependency.task_id, TaskDependency.depends_on_task_id).where(
        TaskDependency.task_id.in_(task_ids)))).all()) if task_ids else []
    dep_tasks = {t.id: t for t in (await db.execute(select(ProjectTask).where(
        ProjectTask.id.in_({d for _, d in edges})))).scalars()} if edges else {}

    assignments: dict[uuid.UUID, TaskAssignment] = {}
    for a in (await db.execute(select(TaskAssignment).where(
        TaskAssignment.task_id.in_(task_ids), TaskAssignment.status == "active",
        TaskAssignment.agent_id.is_not(None)).order_by(TaskAssignment.created_at))).scalars() if task_ids else []:
        assignments[a.task_id] = a

    executions: dict[uuid.UUID, list[TaskExecution]] = {}
    for e in (await db.execute(select(TaskExecution).where(TaskExecution.task_id.in_(task_ids))
                               .order_by(TaskExecution.attempt_number.desc(), TaskExecution.created_at.desc()))
              ).scalars() if task_ids else []:
        executions.setdefault(e.task_id, []).append(e)
    execution_ids = [e.id for es in executions.values() for e in es]

    reviews: dict[uuid.UUID, list[TaskExecutionReview]] = {}
    for r in (await db.execute(select(TaskExecutionReview).where(TaskExecutionReview.execution_id.in_(execution_ids))
                               .order_by(TaskExecutionReview.created_at.desc()))).scalars() if execution_ids else []:
        reviews.setdefault(r.execution_id, []).append(r)
    membership_ids = {r.reviewer_membership_id for rs in reviews.values() for r in rs}
    membership_ids |= {a.membership_id for a in assignments.values() if a.membership_id}
    memberships = {m.id: m for m in (await db.execute(select(ProjectAgentMembership).where(
        ProjectAgentMembership.id.in_(membership_ids)))).scalars()} if membership_ids else {}

    all_members = list((await db.execute(select(ProjectAgentMembership).where(
        ProjectAgentMembership.project_id.in_({mission.project_id, *[p for p in task_project.values() if p]}),
        ProjectAgentMembership.status == "active", ProjectAgentMembership.agent_id.is_not(None),
    ).order_by(ProjectAgentMembership.created_at))).scalars())

    demands: dict[uuid.UUID, list[AgentDemand]] = {}
    for d in (await db.execute(select(AgentDemand).where(
        AgentDemand.origin_type == "task", AgentDemand.origin_id.in_(task_ids))
        .order_by(AgentDemand.created_at.desc()))).scalars() if task_ids else []:
        demands.setdefault(d.origin_id, []).append(d)

    targets: dict[uuid.UUID, list[TaskExecutionTarget]] = {}
    for t in (await db.execute(select(TaskExecutionTarget).where(TaskExecutionTarget.task_id.in_(task_ids))
                               .order_by(TaskExecutionTarget.kind, TaskExecutionTarget.target_key))
              ).scalars() if task_ids else []:
        targets.setdefault(t.task_id, []).append(t)

    audit_rows = list((await db.execute(select(AuditEvent).where(
        or_(
            (AuditEvent.entity_type == "project_task") & AuditEvent.entity_id.in_(task_ids)
            & AuditEvent.event_type.in_(("task.dispatched", "mission_task_returned")),
            (AuditEvent.entity_type == "task_execution") & AuditEvent.entity_id.in_(execution_ids)
            & AuditEvent.event_type.in_(("execution_reported", "execution_auto_verified")),
        )).order_by(AuditEvent.created_at.desc()))).scalars()) if task_ids else []
    last_dispatch: dict[uuid.UUID, AuditEvent] = {}
    last_return: dict[uuid.UUID, AuditEvent] = {}
    last_report: dict[uuid.UUID, AuditEvent] = {}
    auto_verified: set[uuid.UUID] = set()
    for event in audit_rows:
        if event.event_type == "task.dispatched":
            last_dispatch.setdefault(event.entity_id, event)
        elif event.event_type == "mission_task_returned":
            last_return.setdefault(event.entity_id, event)
        elif event.event_type == "execution_reported":
            last_report.setdefault(event.entity_id, event)
        else:
            auto_verified.add(event.entity_id)

    baseline = await db.get(PlanBaseline, mission.current_baseline_id) if mission.current_baseline_id else None
    baseline_items = {i.task_id: i for i in (await db.execute(select(PlanBaselineItem).where(
        PlanBaselineItem.baseline_id == baseline.id))).scalars()} if baseline else {}

    required = await required_skill_map(db, task_ids)
    wanted_skills = {s for ids in required.values() for s in ids}
    skills = {s.id: s for s in (await db.execute(select(Skill).where(Skill.id.in_(wanted_skills)))).scalars()} \
        if wanted_skills else {}

    agent_ids = {mission.orchestrator_agent_id, *[a.agent_id for a in assignments.values()],
                 *[m.agent_id for m in memberships.values()], *[m.agent_id for m in all_members]}
    agents = await _agents(db, agent_ids)
    held: dict[uuid.UUID, set[uuid.UUID]] = {}
    if wanted_skills:
        for agent_id, skill_id in await db.execute(select(AgentSkill.agent_id, AgentSkill.skill_id).where(
                AgentSkill.agent_id.in_(agent_ids), AgentSkill.skill_id.in_(wanted_skills))):
            held.setdefault(agent_id, set()).add(skill_id)

    # Capacity (reserve_dispatch admission, read-only).
    from app.api.routes.demand import _agents_already_running, _dispatch_slots

    slots = await _dispatch_slots(db)
    busy_agents = await _agents_already_running(db)

    conflicts = await _target_conflicts(db, scope_ids)
    releases = {(r.environment, r.target): (r, n) for r, n in await latest_releases(db)}
    publish_targets: set[str] = set()
    ancestry_cache: dict[tuple[str, str, str], tuple[str, str]] = {}

    task_rows: list[dict[str, Any]] = []
    ordered = topo_order(tasks, edges)
    for index, task in enumerate(ordered):
        project_id = task_project.get(task.id)
        project_row = projects.get(project_id)
        working_path = project_row.working_directory_path if project_row else None
        assignment = assignments.get(task.id)
        executor_id = assignment.agent_id if assignment else None
        task_execs = executions.get(task.id, [])
        latest = task_execs[0] if task_execs else None
        latest_reviews = reviews.get(latest.id, []) if latest else []
        review = latest_reviews[0] if latest_reviews else None
        reviewer_membership = memberships.get(review.reviewer_membership_id) if review else None
        reviewer_id = reviewer_membership.agent_id if reviewer_membership else None
        approved_independent = any(
            r.status == "approved" and memberships.get(r.reviewer_membership_id) is not None
            and memberships[r.reviewer_membership_id].agent_id != executor_id
            for r in latest_reviews
        )
        open_review = next((r for r in latest_reviews if r.status in OPEN_REVIEW_STATUSES), None)
        task_demands = demands.get(task.id, [])
        exec_demand = next((d for d in task_demands if latest is not None and d.task_execution_id == latest.id),
                           None) or next((d for d in task_demands if d.task_execution_id is not None), None)
        in_flight = await task_run_in_flight(db, task.id)
        # A queued/running demand of this task decides the state; otherwise
        # the execution's own demand (failed, completed) gives context.
        # An unknown outcome beats everything else in flight (§4: uncertain
        # before running), whichever demand is newer.
        uncertain_demand = next((d for d in task_demands if requires_reconciliation(d)), None)
        state_demand = uncertain_demand or in_flight or exec_demand
        returned = last_return.get(task.id)
        # Returned with no new attempt since: the return names this execution.
        returned_after = bool(returned and latest and (returned.payload or {}).get("execution_id") == str(latest.id))
        report = last_report.get(latest.id) if latest else None
        evidence_refs = list((report.payload or {}).get("evidence") or []) if report else []
        if latest is not None and latest.evidence_ref and latest.evidence_ref not in evidence_refs:
            evidence_refs.insert(0, latest.evidence_ref)
        evidence_failed = bool(latest and latest.status == "failed" and report
                               and (report.payload or {}).get("status") == "reported")
        blocking = await blocking_task_dependencies(db, task.id)

        # Guards, dry-run (same functions as the routes).
        baseline_code = None
        try:
            await assert_task_baseline_current(db, task)
        except (WorkflowBlocked, HTTPException) as exc:
            baseline_code = _code_of(exc)
        target_busy = None
        mission_targets = await task_targets(db, task, working_path)
        holder = await _first_holder(db, mission_targets, demand_id=in_flight.id if in_flight else None) \
            if mission_targets else None
        if holder:
            target_busy = holder

        blocked: list[dict[str, Any]] = []
        allowed: list[str] = []

        def refuse(action: str, code: str, message: str = "", **extra):
            blocked.append(_blocked(action, code, message, **extra))

        terminal = task.status in TERMINAL_TASK_STATUSES
        projects_for_auth = [mission.project_id, *([project_id] if project_id else [])]

        # dispatch / schedule (POST /tasks/{id}/dispatch)
        auth = await actor.refusal("dispatch", DISPATCH_ACTION, projects_for_auth, needs_tools=False)
        for action in ("dispatch", "schedule"):
            if auth:
                refuse(action, auth)
            elif in_flight is not None and requires_reconciliation(in_flight):
                refuse(action, "RECONCILIATION_REQUIRED", "Reconcile the uncertain run first",
                       demand_number=in_flight.number)
            elif baseline_code:
                refuse(action, *baseline_code)
            elif in_flight is not None:
                refuse(action, "TASK_RUN_IN_FLIGHT", "The task already has a run active, reserved or queued",
                       demand_number=in_flight.number)
            elif terminal:
                refuse(action, "TASK_TERMINAL", f"Task is already {task.status}")
            elif assignment is None or assignment.membership_id is None or (
                memberships.get(assignment.membership_id) is None
                or memberships[assignment.membership_id].status != "active"
            ):
                refuse(action, "TASK_NOT_ASSIGNED", "Assign the task first")
            elif action == "dispatch" and blocking:
                refuse(action, "DEPENDENCIES_NOT_DONE", "Unfinished predecessors",
                       blocking=[b["task_number"] for b in blocking])
            elif action == "dispatch" and target_busy:
                refuse(action, "TARGET_BUSY", target_busy)
            elif action == "dispatch" and (slots <= 0 or executor_id in busy_agents):
                refuse(action, "CAPACITY", "Execution capacity is occupied or the agent already runs")
            elif action == "dispatch" and not (working_path or "").startswith("/"):
                refuse(action, "WORKING_PATH_MISSING", "The task's project has no absolute working directory")
            else:
                allowed.append(action)

        # assign (POST /missions/{p}/tasks/{t}:assign)
        auth = await actor.refusal("assign", ASSIGN_ACTION, projects_for_auth)
        if auth:
            refuse("assign", auth)
        elif terminal:
            refuse("assign", "TASK_TERMINAL", f"Task is already {task.status}")
        elif in_flight is not None:
            refuse("assign", "TASK_RUN_IN_FLIGHT", "A run may still be writing", demand_number=in_flight.number)
        else:
            allowed.append("assign")

        # request review (POST .../:request-review)
        reviewer_candidates: list[dict[str, Any]] = []
        if latest is not None:
            seen: set[uuid.UUID] = set()
            for member in all_members:
                if not member.can_review or member.agent_id in seen or member.project_id not in projects_for_auth:
                    continue
                seen.add(member.agent_id)
                try:
                    await assert_review_independent(db, latest, member, project_id or mission.project_id)
                    reviewer_candidates.append({**_agent_ref(agents, member.agent_id), "eligible": True})
                except HTTPException as exc:
                    reviewer_candidates.append({**_agent_ref(agents, member.agent_id), "eligible": False,
                                                "reason": "REVIEWER_IS_EXECUTOR" if exc.status_code == 409
                                                else "REVIEWER_NOT_ELIGIBLE"})
        auth = await actor.refusal("request_review", ORCHESTRATE_ACTION, projects_for_auth)
        if auth:
            refuse("request_review", auth)
        elif terminal:
            refuse("request_review", "TASK_TERMINAL", f"Task is already {task.status}")
        elif latest is None or latest.status != "verified":
            refuse("request_review", "EXECUTION_NOT_VERIFIED", "Only a verified execution is reviewed",
                   execution_status=latest.status if latest else None)
        elif open_review is not None:
            refuse("request_review", "REVIEW_ALREADY_OPEN", "This task already has an open review")
        elif not any(c["eligible"] for c in reviewer_candidates):
            refuse("request_review", "REVIEWER_IS_EXECUTOR" if reviewer_candidates else "REVIEWER_NOT_ELIGIBLE",
                   "No independent reviewer with can_review")
        else:
            allowed.append("request_review")

        # return for correction (POST .../:return)
        auth = await actor.refusal("return", ORCHESTRATE_ACTION, projects_for_auth)
        non_review_in_flight = in_flight if in_flight is not None and not (
            in_flight.task_execution_id is None and in_flight.dispatch_status is None and not in_flight.agent_run_id
        ) else None
        if auth:
            refuse("return", auth)
        elif principal.principal_type == "agent" and principal.principal_id == executor_id:
            refuse("return", "EXECUTOR_CANNOT_RETURN")
        elif terminal:
            refuse("return", "TASK_TERMINAL", f"Task is already {task.status}")
        elif latest is None:
            refuse("return", "EXECUTION_NOT_FOUND", "Nothing was delivered yet")
        elif non_review_in_flight is not None:
            refuse("return", "TASK_RUN_IN_FLIGHT", "A run may still be writing",
                   demand_number=non_review_in_flight.number)
        else:
            allowed.append("return")
        # "Marcar concluída" has no button (§7): completion happens only when
        # the M0.6a guard passes after an approved independent review.

        state = execution_state(
            task, execution=latest, review=review, approved_independent=approved_independent,
            demand=state_demand, returned_after_execution=returned_after, evidence_failed=evidence_failed,
            blocking_deps=blocking,
            ready=not baseline_code and assignment is not None and not blocking,
            now=now,
        )
        queued_reason = None
        if state == "queued":
            if baseline_code:
                queued_reason = baseline_code[0]
            elif blocking:
                queued_reason = "dependencies"
            elif target_busy:
                queued_reason = "TARGET_BUSY"
            elif slots <= 0:
                queued_reason = "capacity"
            elif executor_id in busy_agents:
                queued_reason = "agent_busy"
            elif mission.state == "paused":
                queued_reason = "mission_paused"
        missing = []
        if state == "not_ready":
            if assignment is None:
                missing.append("unassigned")
            if baseline_code:
                missing.append(baseline_code[0])

        # Evidence (§1 point 4).
        evidence = []
        for position, ref in enumerate(evidence_refs):
            verified = None
            if position == 0 and latest is not None:
                if latest.status in ("verified", "completed"):
                    verified = True
                elif evidence_failed:
                    verified = False
            reviewed = None
            if review is not None and reviewer_id is not None:
                reviewed = {"name": _agent_ref(agents, reviewer_id)["name"], "status": review.status}
            evidence.append({
                "ref": ref, "verified": verified,
                "verified_by": ("evidence-check" if latest and latest.id in auto_verified else None)
                if verified else None,
                "checked": position == 0, "reviewed_by": reviewed,
            })

        # Context version (§4.2).
        dispatched = last_dispatch.get(task.id)
        manifest = (dispatched.payload or {}).get("context_manifest") if dispatched else None
        context = None
        if manifest:
            stale_reasons = []
            entries = {m.get("source"): m for m in manifest}
            item = baseline_items.get(task.id)
            baseline_entry = entries.get("plan_baseline_item")
            if item is not None and (baseline_entry is None or baseline_entry.get("id") != str(item.id)):
                stale_reasons.append("baseline_changed")
            task_entry = entries.get("project_task")
            current_fields = {"number": task.number, "title": task.title, "description": task.description,
                              "plan_brief": task.plan_brief, "task_type": task.task_type, "priority": task.priority}
            if task_entry is not None and task_entry.get("hash") != _hash(current_fields):
                stale_reasons.append("task_changed")
            context = {"version": _manifest_version(manifest), "dispatched_at": _iso(dispatched.created_at),
                       "sources": [m.get("source") for m in manifest], "stale": bool(stale_reasons),
                       "stale_reasons": stale_reasons}

        # Skills (§4.2).
        task_skills = []
        for skill_id in required.get(task.id, []):
            skill = skills.get(skill_id)
            task_skills.append({
                "skill_id": str(skill_id), "name": skill.name if skill else str(skill_id)[:8],
                "approved": bool(skill and skill.is_approved),
                "executor_has": executor_id is not None and skill_id in held.get(executor_id, set()),
                "reviewer_has": reviewer_id is not None and skill_id in held.get(reviewer_id, set()),
            })

        # Declared targets and publish ancestry (§5).
        declared = [{"kind": t.kind, "key": t.target_key} for t in targets.get(task.id, [])]
        if working_path:
            declared.append({"kind": "worktree", "key": working_path, "implicit": True})
        for target in targets.get(task.id, []):
            if target.kind != "publish":
                continue
            env, _, name = normalize_target_key("publish", target.target_key).partition(":")
            publish_targets.add(name)
            if env != "production":
                continue
            release = releases.get(("production", name))
            if release is None:
                conflicts.append({"kind": "production_unknown", "severity": "warning", "target": name,
                                  "task_ids": [str(task.id)], "tasks": [task.number],
                                  "detail": "no recorded production release: cannot verify"})
                continue
            candidate = _git_ref(evidence_refs)
            if candidate is None:
                continue
            prod_sha = release[0].commit_sha
            key = (working_path or "", prod_sha, candidate)
            if key not in ancestry_cache:
                if not check_git or not working_path:
                    ancestry_cache[key] = ("unknown", "ancestry not checked")
                else:
                    try:
                        ok, reason = await commit_is_integrated(working_path, prod_sha, candidate)
                        ancestry_cache[key] = ("ok" if ok else "missing", reason)
                    except EvidenceUnverifiable as exc:
                        ancestry_cache[key] = ("unknown", str(exc))
            result, reason = ancestry_cache[key]
            if result == "missing":
                conflicts.append({"kind": "publish_missing_production", "severity": "blocking", "target": name,
                                  "task_ids": [str(task.id)], "tasks": [task.number],
                                  "detail": f"{candidate[:12]} does not contain production {prod_sha[:12]}"})
            elif result == "unknown":
                conflicts.append({"kind": "publish_ancestry_unknown", "severity": "warning", "target": name,
                                  "task_ids": [str(task.id)], "tasks": [task.number],
                                  "detail": f"git check unavailable: {reason}"})

        reviewer_is_executor = reviewer_id is not None and reviewer_id == executor_id
        if reviewer_is_executor:
            conflicts.append({"kind": "reviewer_is_executor", "severity": "blocking", "target": None,
                              "task_ids": [str(task.id)], "tasks": [task.number],
                              "detail": "reviewer equals executor: review blocked"})

        exec_out = None
        if latest is not None or state_demand is not None:
            d = state_demand
            started = d.dispatched_at if d is not None and d.dispatched_at else (latest.started_at if latest else None)
            exec_out = {
                "execution_id": str(latest.id) if latest else None,
                "attempt": latest.attempt_number if latest else None,
                "status": latest.status if latest else None,
                "summary": latest.outcome_summary if latest else None,
                "demand_id": str(d.id) if d else None, "demand_number": d.number if d else None,
                "dispatch_status": d.dispatch_status if d else None,
                "dispatch_error": d.dispatch_error if d else None,
                "agent_run_id": d.agent_run_id if d else None,
                "scheduled_at": _iso(d.scheduled_at) if d else None,
                "dispatched_at": _iso(started),
                "deadline_at": _iso(d.dispatch_deadline_at) if d else None,
                "elapsed_seconds": int((now - started).total_seconds()) if started and state == "running" else None,
                "attempts": d.dispatch_attempts if d else None,
                "retry_limit": (d.retry_limit or DISPATCH_MAX_ATTEMPTS) if d else None,
            }

        task_rows.append({
            "task_id": str(task.id), "number": task.number, "title": task.title, "status": task.status,
            "topo_index": index, "project_id": str(project_id) if project_id else None,
            "depends_on": [{"task_id": str(dep), "number": dep_tasks[dep].number if dep in dep_tasks else None,
                            "status": dep_tasks[dep].status if dep in dep_tasks else "missing"}
                           for tid, dep in edges if tid == task.id],
            "executor": _agent_ref(agents, executor_id),
            "reviewer": _agent_ref(agents, reviewer_id),
            "reviewer_is_executor": reviewer_is_executor,
            "review": {"review_id": str(review.id), "status": review.status, "decided": review.status in
                       DECIDED_REVIEW_STATUSES, "feedback": review.feedback,
                       "created_at": _iso(review.created_at), "decided_at": _iso(review.decided_at)}
            if review else None,
            "reviewer_candidates": reviewer_candidates,
            "executor_candidates": [
                _agent_ref(agents, m.agent_id) for m in all_members
                if m.project_id == (project_id or mission.project_id) and m.role not in NON_EXECUTOR_ROLES
            ],
            "execution_state": state,
            "queued_reason": queued_reason,
            "missing": missing,
            "blocking": [b["task_number"] for b in blocking],
            "returned_reason": (returned.payload or {}).get("reason") if returned_after and returned else None,
            "execution": exec_out,
            "attempts": [{"execution_id": str(e.id), "attempt": e.attempt_number, "status": e.status,
                          "started_at": _iso(e.started_at), "finished_at": _iso(e.finished_at)} for e in task_execs],
            "evidence": evidence,
            "baseline_status": "current" if baseline_code is None else baseline_code[0],
            "context": context,
            "skills": task_skills,
            "targets": declared,
            "conflicts": [],
            "allowed_actions": allowed,
            "blocked_actions": blocked,
        })

    for number, conflict in enumerate(conflicts, start=1):
        conflict["id"] = f"C-{number}"
        for row in task_rows:
            if row["task_id"] in conflict["task_ids"]:
                row["conflicts"].append(conflict["id"])

    environments = []
    names = sorted(publish_targets) or sorted({t for _, t in releases})
    for name in names:
        for environment in ENVIRONMENTS:
            found = releases.get((environment, name))
            if found is None:
                environments.append({"environment": environment, "target": name, "source": "no_record"})
                continue
            release, task_number = found
            environments.append({
                "environment": environment, "target": name, "commit_sha": release.commit_sha,
                "branch": release.branch, "released_at": _iso(release.released_at),
                "released_by": release.released_by, "task_number": task_number, "source": release.source,
                "evidence_ref": release.evidence_ref,
            })

    orchestrator = agents.get(mission.orchestrator_agent_id)
    header_allowed, header_blocked = await _mission_actions(db, actor, mission)
    board = {
        "mission": {
            "project_id": str(project.id), "name": project.name, "state": mission.state,
            "paused_from_state": mission.paused_from_state, "planning_stage": mission.planning_stage,
            "priority": mission.priority, "row_version": mission.row_version,
            "orchestrator": {"id": str(mission.orchestrator_agent_id),
                             "name": orchestrator.name if orchestrator else None},
            "deadline_at": _iso(mission.deadline_at), "paused": mission.state == "paused",
            "paused_seconds": mission.paused_seconds, "state_reason": mission.state_reason,
            "baseline": {"id": str(baseline.id), "name": baseline.name, "content_hash": getattr(
                baseline, "content_hash", None), "approved_at": _iso(baseline.frozen_at),
                "superseded": baseline.superseded_at is not None} if baseline else None,
            "allowed_actions": header_allowed, "blocked_actions": header_blocked,
        },
        "tasks": task_rows,
        "conflicts": conflicts,
        "conflicts_status": "ok",
        "environments": environments,
        "planning": await _planning_view(db, mission, actor) if include_planning else None,
        "viewer": {"principal_type": principal.principal_type, "is_admin": bool(principal.is_admin),
                   "can_act": actor.is_marcelo or principal.principal_type == "agent"},
        "generated_at": now.isoformat(),
    }
    return board


async def _mission_actions(db: AsyncSession, actor: _Actor, mission: ProjectMission) -> tuple[list[str], list[dict]]:
    """Pause / resume / cancel through POST /missions/{p}:transition (§7)."""
    allowed: list[str] = []
    blocked: list[dict] = []
    role = None
    principal = actor.principal
    if principal.principal_type == "user":
        role = "marcelo" if principal.is_admin else None
    elif principal.principal_id == mission.orchestrator_agent_id:
        try:
            await authorize_action(db, principal, ORCHESTRATE_ACTION, project_id=mission.project_id)
            role = "orchestrator"
        except HTTPException as exc:
            if exc.status_code != 403:
                raise
    wanted = {
        "pause": "paused",
        "resume": mission.paused_from_state,
        "cancel": "cancelled",
    }
    for action, to_state in wanted.items():
        if to_state is None or (action == "resume" and mission.state != "paused"):
            blocked.append(_blocked(action, "MISSION_TRANSITION_NOT_ALLOWED", f"{mission.state} -> {action}"))
            continue
        who = ALLOWED_TRANSITIONS.get((mission.state, to_state))
        if mission.state == "paused" and to_state != "cancelled":
            who = frozenset({"marcelo"}) if to_state == mission.paused_from_state else None
        if who is None:
            blocked.append(_blocked(action, "MISSION_TRANSITION_NOT_ALLOWED", f"{mission.state} -> {to_state}"))
        elif role is None:
            blocked.append(_blocked(action, "MISSION_ADMIN_ONLY" if principal.principal_type == "user"
                                    else "MISSION_ACTOR_NOT_ALLOWED"))
        elif role not in who:
            blocked.append(_blocked(action, "MISSION_ACTOR_NOT_ALLOWED"))
        else:
            allowed.append(action)
    blocked.append(_blocked("accept", "ACCEPTANCE_NOT_BUILT",
                            "Mission acceptance (§8) is decided on its governed request, not built in M0"))
    return allowed, blocked


async def _planning_view(db: AsyncSession, mission: ProjectMission, actor: _Actor) -> dict[str, Any] | None:
    """§4.1: stepper, what the current stage waits for, the consolidation
    table and the decisions pending for Marcelo."""
    if mission.state != "planning" and mission.planning_stage is None:
        return None
    view: dict[str, Any] = {"stages": list(PLANNING_STAGES), "current": mission.planning_stage,
                            "status": "ok", "unmet": [], "not_evaluated": []}
    try:
        unmet, not_evaluated = await planning_exit_conditions(db, mission)
        view["unmet"], view["not_evaluated"] = unmet, not_evaluated
    except Exception as exc:  # pragma: no cover - degraded block, never a false all-clear
        view["status"] = "unavailable"
        view["error"] = type(exc).__name__
    plan = await current_plan(db, mission.project_id) or (await db.execute(
        select(ProjectPlan).where(ProjectPlan.project_id == mission.project_id)
        .order_by(ProjectPlan.created_at.desc()).limit(1))).scalars().first()
    reviews = list((await db.execute(select(MissionPlanReview).where(
        MissionPlanReview.project_plan_id == plan.id).order_by(MissionPlanReview.created_at)))
        .scalars()) if plan else []
    waivers = list((await db.execute(select(MissionReviewWaiver).where(
        MissionReviewWaiver.project_plan_id == plan.id))).scalars()) if plan else []
    items = await plan_items(db, plan.id) if plan else []
    agents = await _agents(db, {r.reviewer_agent_id for r in reviews})
    covered = {r.layer for r in reviews if r.kind == "layer"} | {w.layer for w in waivers}
    view["plan_id"] = str(plan.id) if plan else None
    view["layers"] = [{"layer": layer, "reviewed": layer in covered,
                       "waived": any(w.layer == layer for w in waivers)}
                      for layer in mission.required_review_layers or []]
    view["reviews"] = [{"review_id": str(r.id), "kind": r.kind, "layer": r.layer,
                        "reviewer": _agent_ref(agents, r.reviewer_agent_id), "summary": r.summary,
                        "created_at": _iso(r.created_at)} for r in reviews]
    review_by_id = {r.id: r for r in reviews}
    can_decide = actor.is_marcelo and mission.planning_stage in ("consolidation", "cross_review", "decisions")
    view["items"] = [{
        "item_id": str(i.id), "text": i.text,
        "origin": review_by_id[i.review_id].layer if i.review_id in review_by_id else None,
        "disposition": i.disposition, "reason": i.disposition_reason,
        "needs_decision": i.needs_marcelo_decision, "decision": i.marcelo_decision,
        "decision_reason": i.marcelo_reason,
    } for i in items]
    view["pending_decisions"] = [
        {**row, "can_decide": can_decide,
         "blocked_reason": None if can_decide else ("MISSION_ADMIN_ONLY" if not actor.is_marcelo
                                                     else "STAGE_DOES_NOT_DECIDE")}
        for row in view["items"] if row["needs_decision"] and row["decision"] is None
    ]
    return view


# ---------------------------------------------------------------------------
# Mission list (§8)
# ---------------------------------------------------------------------------
async def visible_missions(db: AsyncSession, principal: ActorPrincipal) -> list[tuple[Project, ProjectMission]]:
    stmt = select(Project, ProjectMission).join(ProjectMission, ProjectMission.project_id == Project.id).where(
        Project.project_type == "mission")
    if principal.principal_type == "agent":
        member_projects = select(ProjectAgentMembership.project_id).where(
            ProjectAgentMembership.agent_id == principal.principal_id, ProjectAgentMembership.status == "active")
        stmt = stmt.where(or_(ProjectMission.orchestrator_agent_id == principal.principal_id,
                              ProjectMission.project_id.in_(member_projects)))
    return [(p, m) for p, m in (await db.execute(stmt)).all()]


def summarize(board: dict[str, Any], last_decision: dict[str, Any] | None) -> dict[str, Any]:
    tasks = board["tasks"]
    count = lambda *states: sum(1 for t in tasks if t["execution_state"] in states)  # noqa: E731
    mission = board["mission"]
    deadline = mission["deadline_at"]
    remaining = None
    if deadline:
        remaining = int((datetime.fromisoformat(deadline) - datetime.fromisoformat(board["generated_at"]))
                        .total_seconds())
    agents = sorted({t["executor"]["agent_id"] for t in tasks if t["executor"]
                     and t["execution_state"] in ("queued", "scheduled", "ready")})
    return {
        "project_id": mission["project_id"], "name": mission["name"], "state": mission["state"],
        "priority": mission["priority"], "orchestrator": mission["orchestrator"], "deadline_at": deadline,
        "remaining_seconds": remaining, "progress": {"done_proven": count("done_proven"), "total": len(tasks)},
        "running": count("running"), "queued": count("queued", "scheduled"), "awaiting_review": count("awaiting_review"),
        "uncertain": count("uncertain"),
        "conflicts": sum(1 for c in board["conflicts"] if c["severity"] == "blocking"),
        "warnings": sum(1 for c in board["conflicts"] if c["severity"] != "blocking"),
        "last_decision": last_decision,
        "_agents": {t["executor"]["agent_id"] for t in tasks if t["executor"]},
        "_waiting_agents": agents,
    }


async def last_decision(db: AsyncSession, project_id: uuid.UUID) -> dict[str, Any] | None:
    event = (await db.execute(select(AuditEvent).where(
        AuditEvent.entity_type == "mission", AuditEvent.entity_id == project_id)
        .order_by(AuditEvent.created_at.desc()).limit(1))).scalar_one_or_none()
    if event is None:
        return None
    return {"event_type": event.event_type, "actor": event.actor, "at": _iso(event.created_at)}


def contested_agents(summaries: list[dict[str, Any]], names: dict[str, str]) -> list[dict[str, Any]]:
    """Agents with waiting work in more than one mission; the winner is the
    lowest priority number (cycle spec §6.1)."""
    by_agent: dict[str, list[dict[str, Any]]] = {}
    for summary in summaries:
        for agent_id in summary["_waiting_agents"]:
            by_agent.setdefault(agent_id, []).append(summary)
    out = []
    for agent_id, missions in sorted(by_agent.items()):
        if len(missions) < 2:
            continue
        ordered = sorted(missions, key=lambda s: (s["priority"], s["deadline_at"] or "9999"))
        out.append({"agent_id": agent_id, "name": names.get(agent_id, agent_id[:8]),
                    "missions": [{"project_id": s["project_id"], "name": s["name"], "priority": s["priority"]}
                                 for s in ordered],
                    "winner_project_id": ordered[0]["project_id"]})
    return out


async def executor_project_scope(db: AsyncSession, project_id: uuid.UUID) -> list[uuid.UUID]:
    return [project_id, *(await executor_project_ids(db, project_id))]

"""Mission state machine, planning pipeline exit conditions and the P2 skill check.

Contract: docs/architecture/MCP_MISSION_TOOLS_SPEC.md §2-§3.1 and §6.1
("Skills"). Routes live in api/routes/mission.py; this module only reads the
database and returns what is missing, so the same checks can be reused by the
plan submission (M0.2b) and the cycle (M0.8).

A condition whose data has no place to be read yet is reported as unmet with
``not_recorded: True``: it never passes for lack of data. Those are listed in
``NOT_RECORDED_CONDITIONS`` and lifted by the slice that adds the data; M0.0b
(§2.6, `core/mission_records.py`) lifted every one M0.0 had, so it is empty.
"""
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.mission_records import (
    current_plan_version,
    dossier_items,
    environment_items,
    environment_prerequisite_items,
    record_conditions,
)
from app.core.task_skills import required_skill_map
from app.db.models.agent import AgentSkill, Skill
from app.db.models.artifact import Artifact, ArtifactStatus, ArtifactVersion, ArtifactVersionStatus
from app.db.models.backlog import PlanningItem
from app.db.models.mission import (
    MISSION_STATUS_PROJECTION,
    PLANNING_STAGES,
    MissionAcceptanceCriterion,
    MissionCriterionTask,
    MissionProjectLink,
    ProjectMission,
)
from app.db.models.orchestration import ProjectAgentMembership
from app.db.models.project import ChangeRequest, PlanBaseline, Project, ProjectPlan
from app.db.models.task import ProjectTask, TaskAssignment, TaskDependency

# Settings value in M0.8 (cycle spec §6.2); a constant until then.
MISSION_MAX_ACTIVE_PER_ORCHESTRATOR = 2
ORCHESTRATOR_BUSY_STATES = ("active", "verifying", "awaiting_acceptance")
TASK_CLOSED_STATUSES = ("done", "deployed", "cancelled")

# Who may request each transition (§3 table). "marcelo" = admin user;
# "orchestrator" = the mission's orchestrator agent with `mission.orchestrate`;
# "verifier" = an agent verifying a failed criterion of the mission.
# awaiting_acceptance -> completed is absent on purpose: only the acceptance
# decision (§8) completes a mission.
_PAUSABLE = ("planning", "ready", "active", "verifying")
ALLOWED_TRANSITIONS: dict[tuple[str, str], frozenset[str]] = {
    ("draft", "planning"): frozenset({"marcelo"}),
    ("planning", "ready"): frozenset({"marcelo"}),
    ("ready", "active"): frozenset({"marcelo", "orchestrator"}),
    ("active", "verifying"): frozenset({"marcelo", "orchestrator"}),
    ("verifying", "active"): frozenset({"marcelo", "orchestrator", "verifier"}),
    ("verifying", "awaiting_acceptance"): frozenset({"marcelo", "orchestrator"}),
    ("awaiting_acceptance", "active"): frozenset({"marcelo"}),
    ("completed", "active"): frozenset({"marcelo"}),
    **{(s, "paused"): frozenset({"marcelo", "orchestrator"}) for s in _PAUSABLE},
    **{(s, "cancelled"): frozenset({"marcelo"}) for s in (
        "draft", "planning", "ready", "active", "verifying", "awaiting_acceptance", "paused",
    )},
}
REASON_REQUIRED_TARGETS = ("paused", "cancelled")
REASON_REQUIRED_SOURCES = ("paused", "completed", "awaiting_acceptance")

# code -> why it cannot be read yet. Lifted by M0.0b (§2.6): environment and
# prerequisites (project_tasks columns), review artifacts, dispositions, cross
# reviews, flagged items, application verification and the dossier.
NOT_RECORDED_CONDITIONS: dict[str, str] = {}


def mission_error(status_code: int, code: str, message: str, **context: Any) -> HTTPException:
    return HTTPException(status_code, detail={"code": code, "message": message, **context})


def _item(code: str, message: str, **context: Any) -> dict[str, Any]:
    return {"code": code, "message": message, **context}


def apply_mission_state(
    project: Project, mission: ProjectMission, to_state: str, reason: str | None, now: datetime
) -> None:
    """The only writer of mission state: sets state and its Project.status
    projection together, so both land in the caller's transaction."""
    if mission.state == "paused":
        mission.paused_seconds += max(0, int((now - mission.state_changed_at).total_seconds()))
    mission.paused_from_state = mission.state if to_state == "paused" else None
    mission.state = to_state
    mission.state_changed_at = now
    mission.state_reason = reason
    mission.row_version += 1
    project.status = MISSION_STATUS_PROJECTION[to_state]


async def project_id_for_task_source(
    db: AsyncSession, planning_item_id: uuid.UUID | None, change_request_id: uuid.UUID | None
) -> uuid.UUID | None:
    if planning_item_id is not None:
        item = await db.get(PlanningItem, planning_item_id)
        if item is not None and item.project_id is not None:
            return item.project_id
    if change_request_id is not None:
        change_request = await db.get(ChangeRequest, change_request_id)
        if change_request is not None:
            return change_request.project_id
    return None


async def assert_required_skills_writable(
    db: AsyncSession,
    project_id: uuid.UUID | None,
    new_ids: list[uuid.UUID],
    old_ids: list[uuid.UUID],
) -> None:
    """§6.1: every id must be a registered skill; a mission task's list only
    changes while the mission is `planning` (afterwards by change request)."""
    if set(new_ids) == set(old_ids):
        return
    unknown = set(new_ids) - set((await db.execute(
        select(Skill.id).where(Skill.id.in_(new_ids))
    )).scalars()) if new_ids else set()
    if unknown:
        raise mission_error(422, "UNKNOWN_SKILL_IDS", "required_skill_ids has ids that are not skills",
                            skill_ids=sorted(str(i) for i in unknown))
    if project_id is None:
        return
    mission = await db.get(ProjectMission, project_id)
    if mission is not None and mission.state != "planning":
        raise mission_error(
            409, "REQUIRED_SKILLS_LOCKED",
            "A mission task's required skills change only while the mission is in planning; "
            "afterwards use a change request.",
            mission_state=mission.state,
        )


async def assert_task_environment_writable(db: AsyncSession, project_id: uuid.UUID | None) -> None:
    """§2.6: a mission task's environment and prerequisites change only while
    the mission is `planning`, like its required skills."""
    if project_id is None:
        return
    mission = await db.get(ProjectMission, project_id)
    if mission is not None and mission.state != "planning":
        raise mission_error(
            409, "TASK_ENVIRONMENT_LOCKED",
            "A mission task's environment changes only while the mission is in planning; "
            "afterwards use a change request.",
            mission_state=mission.state,
        )


async def mission_tasks(db: AsyncSession, project_id: uuid.UUID) -> list[ProjectTask]:
    """Tasks of the mission project itself (through planning item or CR)."""
    return list((await db.execute(
        select(ProjectTask).where(or_(
            ProjectTask.planning_item_id.in_(select(PlanningItem.id).where(PlanningItem.project_id == project_id)),
            ProjectTask.change_request_id.in_(select(ChangeRequest.id).where(ChangeRequest.project_id == project_id)),
        )).order_by(ProjectTask.number)
    )).scalars())


async def _criteria(db: AsyncSession, project_id: uuid.UUID) -> list[MissionAcceptanceCriterion]:
    return list((await db.execute(
        select(MissionAcceptanceCriterion)
        .where(MissionAcceptanceCriterion.mission_project_id == project_id)
        .order_by(MissionAcceptanceCriterion.code)
    )).scalars())


async def _criterion_task_ids(db: AsyncSession, criterion_ids: list[uuid.UUID]) -> dict[uuid.UUID, set[uuid.UUID]]:
    result: dict[uuid.UUID, set[uuid.UUID]] = {cid: set() for cid in criterion_ids}
    if criterion_ids:
        rows = await db.execute(
            select(MissionCriterionTask.criterion_id, MissionCriterionTask.task_id)
            .where(MissionCriterionTask.criterion_id.in_(criterion_ids))
        )
        for criterion_id, task_id in rows:
            result[criterion_id].add(task_id)
    return result


async def executor_project_ids(db: AsyncSession, project_id: uuid.UUID) -> list[uuid.UUID]:
    return list((await db.execute(
        select(MissionProjectLink.executor_project_id)
        .where(MissionProjectLink.mission_project_id == project_id)
        .order_by(MissionProjectLink.created_at)
    )).scalars())


async def _active_memberships(db: AsyncSession, project_id: uuid.UUID) -> list[ProjectAgentMembership]:
    return list((await db.execute(
        select(ProjectAgentMembership).where(
            ProjectAgentMembership.project_id == project_id,
            ProjectAgentMembership.status == "active",
            ProjectAgentMembership.agent_id.is_not(None),
        )
    )).scalars())


async def _executors_by_task(
    db: AsyncSession, task_ids: list[uuid.UUID], memberships: list[ProjectAgentMembership]
) -> dict[uuid.UUID, ProjectAgentMembership]:
    """The executor of a task is its active assignment through an active
    membership of the mission (the role comes from the membership)."""
    by_id = {m.id: m for m in memberships}
    executors: dict[uuid.UUID, ProjectAgentMembership] = {}
    if not task_ids:
        return executors
    rows = (await db.execute(
        select(TaskAssignment).where(
            TaskAssignment.task_id.in_(task_ids),
            TaskAssignment.status == "active",
            TaskAssignment.membership_id.is_not(None),
        ).order_by(TaskAssignment.assigned_at)
    )).scalars()
    for assignment in rows:
        membership = by_id.get(assignment.membership_id)
        if membership is not None and membership.agent_id == assignment.agent_id:
            executors[assignment.task_id] = membership
    return executors


def _find_cycle(edges: list[tuple[uuid.UUID, uuid.UUID]]) -> list[uuid.UUID] | None:
    graph: dict[uuid.UUID, list[uuid.UUID]] = {}
    for task_id, depends_on in edges:
        graph.setdefault(task_id, []).append(depends_on)
    state: dict[uuid.UUID, int] = {}
    stack: list[uuid.UUID] = []

    def visit(node: uuid.UUID) -> list[uuid.UUID] | None:
        state[node] = 1
        stack.append(node)
        for nxt in graph.get(node, []):
            if state.get(nxt) == 1:
                return stack[stack.index(nxt):] + [nxt]
            if nxt not in state:
                found = visit(nxt)
                if found:
                    return found
        stack.pop()
        state[node] = 2
        return None

    for node in list(graph):
        if node not in state:
            found = visit(node)
            if found:
                return found
    return None


async def skill_check_items(
    db: AsyncSession,
    tasks: list[ProjectTask],
    executors: dict[uuid.UUID, ProjectAgentMembership],
    memberships: list[ProjectAgentMembership],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """P2 skills (§6.1). Returns (gaps, not_evaluated).

    The required skills are the task's mandatory `task_required_skills` rows
    (the one store since M0.2b, DT-M0-1).

    Per task and required skill: the skill exists and is active (approved);
    the executor holds it; an eligible reviewer -- an active `can_review`
    member other than the executor -- holds it. There is no per-task named
    reviewer before M0.2b, so the reviewer side is checked against that
    pool; an empty pool is its own gap. Whether the skill is installed in
    the agent's runtime is not evaluated: the existing reader
    (`hermes_sync.parse_profile_skills`) only sees Hermes profiles, not the
    external runtimes that execute code."""
    required_by_task = await required_skill_map(db, [t.id for t in tasks])
    wanted = {sid for ids in required_by_task.values() for sid in ids}
    skills = {s.id: s for s in (await db.execute(select(Skill).where(Skill.id.in_(wanted)))).scalars()} if wanted else {}
    agent_ids = {m.agent_id for m in memberships}
    held: dict[uuid.UUID, set[uuid.UUID]] = {}
    if wanted and agent_ids:
        for agent_id, skill_id in await db.execute(
            select(AgentSkill.agent_id, AgentSkill.skill_id)
            .where(AgentSkill.agent_id.in_(agent_ids), AgentSkill.skill_id.in_(wanted))
        ):
            held.setdefault(agent_id, set()).add(skill_id)

    gaps: list[dict[str, Any]] = []
    for task in tasks:
        required = required_by_task.get(task.id, [])
        if not required:
            continue
        executor = executors.get(task.id)
        reviewers = [m for m in memberships if m.can_review and (executor is None or m.agent_id != executor.agent_id)]
        for skill_id in required:
            skill = skills.get(skill_id)
            ctx = {"task_id": str(task.id), "task_number": task.number, "skill_id": str(skill_id)}
            if skill is None:
                gaps.append(_item("SKILL_NOT_FOUND", "Required skill is not registered", **ctx))
                continue
            ctx["skill_name"] = skill.name
            if not skill.is_approved:
                gaps.append(_item("SKILL_NOT_ACTIVE", "Required skill is not approved", **ctx))
            if executor is None:
                gaps.append(_item("SKILL_EXECUTOR_UNASSIGNED", "No executor to check the skill against", **ctx))
            elif skill_id not in held.get(executor.agent_id, set()):
                gaps.append(_item("EXECUTOR_MISSING_SKILL", "The executor does not hold the skill",
                                  agent_id=str(executor.agent_id), **ctx))
            if not reviewers:
                gaps.append(_item("SKILL_REVIEWER_UNASSIGNED", "No eligible reviewer to check the skill against", **ctx))
            elif not any(skill_id in held.get(m.agent_id, set()) for m in reviewers):
                gaps.append(_item("REVIEWER_MISSING_SKILL", "No eligible reviewer holds the skill",
                                  reviewer_agent_ids=sorted(str(m.agent_id) for m in reviewers), **ctx))
    not_evaluated = [
        _item("SKILL_RUNTIME_PRESENCE", "Runtime installation of required skills is not verified in M0.0",
              skill_ids=sorted(str(s) for s in wanted))
    ] if wanted else []
    return gaps, not_evaluated


async def _validator_items(db: AsyncSession, mission: ProjectMission) -> tuple[list[dict], list[dict]]:
    """The P2/P7 plan validator over what M0.0 can read."""
    project_id = mission.project_id
    _plan, _version, unmet = await current_plan_version(db, project_id)
    tasks = await mission_tasks(db, project_id)
    if not tasks:
        unmet.append(_item("NO_TASKS", "The mission has no tasks"))
    task_ids = [t.id for t in tasks]
    edges = [
        (row.task_id, row.depends_on_task_id)
        for row in (await db.execute(
            select(TaskDependency).where(TaskDependency.task_id.in_(task_ids))
        )).scalars()
    ] if task_ids else []
    cycle = _find_cycle(edges)
    if cycle:
        unmet.append(_item("DEPENDENCY_CYCLE", "Task dependencies form a cycle", task_ids=[str(t) for t in cycle]))
    memberships = await _active_memberships(db, project_id)
    executors = await _executors_by_task(db, task_ids, memberships)
    for task in tasks:
        executor = executors.get(task.id)
        if executor is None:
            unmet.append(_item("TASK_WITHOUT_EXECUTOR", "Task has no active assignment through a mission member",
                               task_id=str(task.id), task_number=task.number))
            continue
        if not any(m.can_review and m.agent_id != executor.agent_id for m in memberships):
            unmet.append(_item("NO_INDEPENDENT_REVIEWER", "No active reviewing member other than the executor",
                               task_id=str(task.id), task_number=task.number))
    gaps, not_evaluated = await skill_check_items(db, tasks, executors, memberships)
    unmet.extend(gaps)
    unmet.extend(await environment_prerequisite_items(db, tasks))
    return unmet, not_evaluated


async def _draft_plan_items(db: AsyncSession, mission: ProjectMission) -> list[dict[str, Any]]:
    project_id = mission.project_id
    _plan, _version, unmet = await current_plan_version(db, project_id)
    tasks = await mission_tasks(db, project_id)
    if not tasks:
        unmet.append(_item("NO_TASKS", "The mission has no tasks"))
    unmet.extend(environment_items(tasks))
    task_ids = {t.id for t in tasks}
    executors = await _executors_by_task(db, list(task_ids), await _active_memberships(db, project_id))
    for task in tasks:
        if task.id not in executors:
            unmet.append(_item("TASK_WITHOUT_ROLE", "Task has no active assignment through a mission member",
                               task_id=str(task.id), task_number=task.number))
    if task_ids:
        scope = task_ids | {t.id for pid in await executor_project_ids(db, project_id) for t in await mission_tasks(db, pid)}
        for dep in (await db.execute(select(TaskDependency).where(TaskDependency.task_id.in_(task_ids)))).scalars():
            if dep.depends_on_task_id not in scope:
                unmet.append(_item("DEPENDENCY_OUTSIDE_MISSION", "Task depends on a task outside the mission",
                                   task_id=str(dep.task_id), depends_on_task_id=str(dep.depends_on_task_id)))
    criteria = await _criteria(db, project_id)
    if not criteria:
        unmet.append(_item("NO_CRITERIA", "The mission has no acceptance criteria"))
    linked = await _criterion_task_ids(db, [c.id for c in criteria])
    for criterion in criteria:
        if not linked[criterion.id]:
            unmet.append(_item("CRITERION_WITHOUT_TASK", "Acceptance criterion has no task", code_ref=criterion.code))
    if mission.deadline_at is None:
        unmet.append(_item("DEADLINE_MISSING", "deadline_at is not set"))
    if mission.budget_limit is None:
        unmet.append(_item("BUDGET_MISSING", "budget_limit is not set"))
    if mission.risk_level is None:
        unmet.append(_item("RISK_LEVEL_MISSING", "risk_level is not set"))
    if not mission.required_review_layers:
        unmet.append(_item("REVIEW_LAYERS_MISSING", "required_review_layers is empty"))
    return unmet


async def planning_exit_conditions(db: AsyncSession, mission: ProjectMission) -> tuple[list[dict], list[dict]]:
    """Unmet conditions to leave the mission's current planning stage (§3.1),
    plus checks reported as not evaluated (never counted as passed)."""
    stage = mission.planning_stage
    if stage == "draft_plan":
        return await _draft_plan_items(db, mission), []
    if stage == "auto_check":
        return await _validator_items(db, mission)
    if stage in ("critical_review", "consolidation", "cross_review", "decisions"):
        return await record_conditions(db, mission), []
    if stage == "application":
        unmet, not_evaluated = await _validator_items(db, mission)
        records = [u for u in await record_conditions(db, mission) if u not in unmet]
        return unmet + records, not_evaluated
    return [_item("PLANNING_STAGE_UNKNOWN", f"No exit rule for stage {stage!r}")], []


def next_planning_stages(mission: ProjectMission) -> tuple[str, ...]:
    """Only the next stage; consolidation may jump to decisions when the
    risk is low (cross review skipped). `baseline` has no next stage: it ends
    in the governed baseline approval (§7), which performs planning -> ready."""
    stage = mission.planning_stage
    if stage not in PLANNING_STAGES or stage == PLANNING_STAGES[-1]:
        return ()
    following = (PLANNING_STAGES[PLANNING_STAGES.index(stage) + 1],)
    if stage == "consolidation" and mission.risk_level == "low":
        following += ("decisions",)
    return following


async def _current_baseline_valid(db: AsyncSession, mission: ProjectMission) -> bool:
    if mission.current_baseline_id is None:
        return False
    baseline = await db.get(PlanBaseline, mission.current_baseline_id)
    if baseline is None or baseline.superseded_at is not None:
        return False
    plan = await db.get(ProjectPlan, baseline.project_plan_id)
    return plan is not None and plan.project_id == mission.project_id and plan.status != "superseded"


async def brief_items(db: AsyncSession, mission: ProjectMission) -> list[dict[str, Any]]:
    """The brief artifact is approved with a final version (draft -> planning,
    and the plan submission's `brief_approved` check, M0.2b)."""
    brief = await db.get(Artifact, mission.brief_artifact_id) if mission.brief_artifact_id else None
    if brief is None:
        return [_item("BRIEF_MISSING", "The mission has no brief artifact")]
    final = await db.scalar(select(ArtifactVersion.id).where(
        ArtifactVersion.artifact_id == brief.id, ArtifactVersion.status == ArtifactVersionStatus.FINAL,
    ).limit(1))
    if brief.status != ArtifactStatus.APPROVED or final is None:
        return [_item("BRIEF_NOT_APPROVED", "The brief artifact is not approved with a final version")]
    return []


async def transition_preconditions(
    db: AsyncSession, mission: ProjectMission, to_state: str
) -> list[dict[str, Any]]:
    """Unmet preconditions of the §3 transition table (empty = allowed)."""
    from_state = mission.state
    unmet: list[dict[str, Any]] = []
    project_id = mission.project_id

    if (from_state, to_state) == ("draft", "planning"):
        unmet.extend(await brief_items(db, mission))
        coordinator = await db.scalar(select(ProjectAgentMembership.id).where(
            ProjectAgentMembership.project_id == project_id,
            ProjectAgentMembership.agent_id == mission.orchestrator_agent_id,
            ProjectAgentMembership.role == "coordinator",
            ProjectAgentMembership.status == "active",
        ).limit(1))
        if coordinator is None:
            unmet.append(_item("ORCHESTRATOR_NOT_ACTIVE_COORDINATOR",
                               "The orchestrator has no active coordinator membership"))
        if mission.deadline_at is None:
            unmet.append(_item("DEADLINE_MISSING", "deadline_at is not set"))
        if mission.budget_limit is None:
            unmet.append(_item("BUDGET_MISSING", "budget_limit is not set"))

    elif (from_state, to_state) == ("planning", "ready"):
        if mission.planning_stage != "baseline":
            unmet.append(_item("PLANNING_PIPELINE_UNFINISHED", "The planning pipeline has not reached baseline",
                               planning_stage=mission.planning_stage))
        criteria = await _criteria(db, project_id)
        if not criteria:
            unmet.append(_item("NO_CRITERIA", "The mission has no acceptance criteria"))
        for criterion in criteria:
            if not criterion.verification_method.strip():
                unmet.append(_item("CRITERION_WITHOUT_METHOD", "Criterion has no verification method",
                                   code_ref=criterion.code))
        if mission.deadline_at is None:
            unmet.append(_item("DEADLINE_MISSING", "deadline_at is not set"))
        if mission.budget_limit is None:
            unmet.append(_item("BUDGET_MISSING", "budget_limit is not set"))
        if not await _current_baseline_valid(db, mission):
            unmet.append(_item("BASELINE_MISSING", "No current baseline of this mission's plan"))

    elif (from_state, to_state) == ("ready", "active"):
        if not await _current_baseline_valid(db, mission):
            unmet.append(_item("BASELINE_SUPERSEDED_OR_MISSING", "The current baseline is missing or superseded"))
        busy = list((await db.execute(select(ProjectMission.project_id).where(
            ProjectMission.orchestrator_agent_id == mission.orchestrator_agent_id,
            ProjectMission.state.in_(ORCHESTRATOR_BUSY_STATES),
            ProjectMission.project_id != project_id,
        ))).scalars())
        if len(busy) >= MISSION_MAX_ACTIVE_PER_ORCHESTRATOR:
            unmet.append(_item("ORCHESTRATOR_AT_CAPACITY", "The orchestrator is at its active-mission limit",
                               active_missions=[str(p) for p in busy],
                               limit=MISSION_MAX_ACTIVE_PER_ORCHESTRATOR))
        # Inter-mission dependencies (cycle spec §6.3) need mission_dependencies
        # (M0.8); none can be declared before it exists.

    elif (from_state, to_state) == ("active", "verifying"):
        criteria = await _criteria(db, project_id)
        if not criteria or any(c.status != "proven" for c in criteria):
            unmet.append(_item("CRITERIA_NOT_ALL_PROVEN", "Every acceptance criterion must be proven",
                               open=[c.code for c in criteria if c.status != "proven"]))

    elif (from_state, to_state) == ("verifying", "active"):
        criteria = await _criteria(db, project_id)
        failed = [c.code for c in criteria if c.status == "failed"]
        linked = await _criterion_task_ids(db, [c.id for c in criteria])
        task_ids = {t for ids in linked.values() for t in ids}
        reopened = list((await db.execute(select(ProjectTask.number).where(
            ProjectTask.id.in_(task_ids), ProjectTask.status.not_in(TASK_CLOSED_STATUSES),
        ))).scalars()) if task_ids else []
        if not failed and not reopened:
            unmet.append(_item("NOTHING_FAILED_OR_REOPENED",
                               "Return to active needs a failed criterion or a reopened task"))

    elif (from_state, to_state) == ("verifying", "awaiting_acceptance"):
        unmet.extend(await dossier_items(db, mission))

    return unmet


async def failed_criterion_verifiers(db: AsyncSession, project_id: uuid.UUID) -> set[uuid.UUID]:
    return set((await db.execute(select(MissionAcceptanceCriterion.verifier_agent_id).where(
        MissionAcceptanceCriterion.mission_project_id == project_id,
        MissionAcceptanceCriterion.status == "failed",
        MissionAcceptanceCriterion.verifier_agent_id.is_not(None),
    ))).scalars())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)

"""Governed mission plan approval (Plano Integrado M0.2b).

Contract: docs/architecture/MCP_MISSION_TOOLS_SPEC.md §5.3, §5.4 and §7.

``submit_project_plan`` only *proposes*: it runs the automatic checks M0 can
compute, freezes a ``plan_hash`` and opens an ``ApprovalRequest(target_type=
'project_plan')`` under the ``Mission plan approval v1`` policy
(``deny_self_approval``, ``human_only``, ``expires_hours: 168``). A check that
needs M.1 data is reported ``not_evaluated``, never passed.

Two submissions exist:

- **Initial baseline**: the mission is ``planning`` at stage ``baseline``
  (P1-P7 done on the current plan version, M0.0b). The plan submitted is that
  reviewed version; the body may repeat its fields but not change them.
- **Change request** (§7 item 6): the mission is ``ready``/``active``/
  ``verifying`` and the plan applies an ``approved`` change request of the
  mission. A new ``ProjectPlan`` draft is created with ``change_request_id``.

``decide_plan_approval`` is the ``project_plan`` branch of
``POST /governed/approval-requests/{id}:decide``: an admin user only, the
hash recomputed (409 ``PLAN_CHANGED_SINCE_SUBMISSION``), and on approval, in
the caller's transaction: plan ``approved`` -> ``create_mission_baseline``
(supersedes the previous baseline, sets ``current_baseline_id``), the change
request ``applied``, the ``ApprovalDecisionRecord``. Nothing is dispatched
and the mission state does not move: ``planning -> ready`` stays Marcelo's
transition.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ActorPrincipal
from app.core.governed_approval import _expire, canonical_hash
from app.core.mission import (
    _active_memberships,
    _criteria,
    _criterion_task_ids,
    _executors_by_task,
    _find_cycle,
    brief_items,
    executor_project_ids,
    mission_error,
    mission_tasks,
    skill_check_items,
)
from app.core.mission_records import environment_items, environment_prerequisite_items
from app.core.plan_baseline import BaselineCreationError, create_mission_baseline, mission_content_part, task_content_hash
from app.db.models.governance import (
    ApprovalDecisionRecord,
    ApprovalRequest,
    AuditEvent,
    PolicyBinding,
    PolicyEvaluation,
    PolicyVersion,
)
from app.db.models.mission import MissionPlanSubmission, ProjectMission
from app.db.models.notification import Notification
from app.db.models.orchestration import ProjectAgentMembership
from app.db.models.project import ChangeRequest, PlanBaseline, PlanBaselineItem, ProjectPlan
from app.db.models.task import ProjectTask, TaskDependency

TARGET_TYPE = "project_plan"
APPROVAL_TYPE = "mission_plan_baseline"
CR_MISSION_STATES = ("ready", "active", "verifying")
# Roles that plan, coordinate or review; any other active role executes.
NON_EXECUTOR_ROLES = frozenset({"coordinator", "planner", "reviewer", "security_reviewer"})
# 04 "Validação do plano" checks that need M.1 data (§10).
NOT_EVALUATED_CHECKS = (
    ("critical_path_vs_deadline", "The critical path against the deadline needs plan phases (M.1h)"),
    ("document_owners", "Document owners are not modeled before M.1"),
    ("risk_list", "The mission's risk list is not modeled before M.1"),
    ("budget_sum", "Task costs are not summed against the budget before M.1"),
)


# ---------------------------------------------------------------------------
# Scope and baseline lookups (also used by add_task_dependency)
# ---------------------------------------------------------------------------
async def mission_scope_tasks(db: AsyncSession, mission_project_id: uuid.UUID) -> dict[uuid.UUID, ProjectTask]:
    """The mission's own tasks and those of its linked executor projects."""
    scope = {t.id: t for t in await mission_tasks(db, mission_project_id)}
    for executor_id in await executor_project_ids(db, mission_project_id):
        scope.update({t.id: t for t in await mission_tasks(db, executor_id)})
    return scope


async def current_baseline_of_task(db: AsyncSession, task_id: uuid.UUID) -> PlanBaseline | None:
    """A non-superseded, itemized baseline that froze this task."""
    return (await db.execute(
        select(PlanBaseline).join(PlanBaselineItem, PlanBaselineItem.baseline_id == PlanBaseline.id)
        .where(PlanBaselineItem.task_id == task_id, PlanBaseline.superseded_at.is_(None))
        .limit(1)
    )).scalars().first()


# ---------------------------------------------------------------------------
# Hash and checks
# ---------------------------------------------------------------------------
def _plan_fields(plan: ProjectPlan) -> dict[str, Any]:
    return {
        "name": plan.name, "scope_summary": plan.scope_summary,
        "estimated_start_date": plan.estimated_start_date, "estimated_end_date": plan.estimated_end_date,
        "estimated_cost": None if plan.estimated_cost is None else str(plan.estimated_cost),
        "change_request_id": plan.change_request_id,
    }


async def compute_plan_hash(
    db: AsyncSession, mission: ProjectMission, plan: ProjectPlan, task_ids: list[uuid.UUID],
) -> str:
    """The plan's own fields plus, per task, the content hash the baseline
    would freeze (§4.2; the brief version and criteria are inside it). Any
    edit to either after submission changes the hash."""
    mission_part = await mission_content_part(db, mission)
    tasks = {t.id: t for t in (await db.execute(
        select(ProjectTask).where(ProjectTask.id.in_(task_ids))
    )).scalars()}
    items = []
    for task_id in task_ids:
        content = await task_content_hash(db, tasks[task_id], mission_part) if task_id in tasks else None
        items.append([str(task_id), content])
    items.sort()
    return canonical_hash({"plan": _plan_fields(plan), "tasks": items, "mission": mission_part})


def _check(key: str, unmet: list[dict[str, Any]], message: str) -> dict[str, Any]:
    return {"key": key, "status": "failed" if unmet else "passed", "passed": not unmet,
            "detail": unmet or message}


async def plan_checks(
    db: AsyncSession, mission: ProjectMission, task_ids: list[uuid.UUID], change_request: ChangeRequest | None,
) -> list[dict[str, Any]]:
    """The automatic checks of §7 item 1 over the listed tasks."""
    project_id = mission.project_id
    scope = await mission_scope_tasks(db, project_id)
    outside = [str(t) for t in task_ids if t not in scope]
    tasks = [scope[t] for t in task_ids if t in scope]
    listed = {t.id for t in tasks}

    memberships: list[ProjectAgentMembership] = list(await _active_memberships(db, project_id))
    for executor_id in await executor_project_ids(db, project_id):
        memberships += await _active_memberships(db, executor_id)
    executors = await _executors_by_task(db, list(listed), memberships)
    no_executor, no_reviewer = [], []
    for task in tasks:
        executor = executors.get(task.id)
        ref = {"task_id": str(task.id), "task_number": task.number}
        if executor is None or executor.role in NON_EXECUTOR_ROLES:
            no_executor.append({"code": "TASK_WITHOUT_EXECUTOR",
                                "message": "No active assignment through a member with an executor role", **ref})
            continue
        if not any(m.can_review and m.agent_id != executor.agent_id for m in memberships):
            no_reviewer.append({"code": "NO_INDEPENDENT_REVIEWER",
                                "message": "No active reviewing member other than the executor", **ref})

    edges = [(d.task_id, d.depends_on_task_id) for d in (await db.execute(
        select(TaskDependency).where(TaskDependency.task_id.in_(list(scope)))
    )).scalars()] if scope else []
    cycle = _find_cycle(edges)
    deps_outside = [
        {"code": "DEPENDENCY_OUTSIDE_MISSION", "message": "A listed task depends on a task outside the mission",
         "task_id": str(a), "depends_on_task_id": str(b)}
        for a, b in edges if a in listed and b not in scope
    ]

    criteria = await _criteria(db, project_id)
    linked = await _criterion_task_ids(db, [c.id for c in criteria])
    criteria_unmet = [{"code": "NO_CRITERIA", "message": "The mission has no acceptance criteria"}] if not criteria else []
    criteria_unmet += [
        {"code": "CRITERION_WITHOUT_TASK", "message": "Acceptance criterion has no task", "code_ref": c.code}
        for c in criteria if not linked[c.id]
    ]
    deadline_budget = []
    if mission.deadline_at is None:
        deadline_budget.append({"code": "DEADLINE_MISSING", "message": "deadline_at is not set"})
    if mission.budget_limit is None:
        deadline_budget.append({"code": "BUDGET_MISSING", "message": "budget_limit is not set"})
    skill_gaps, skill_not_evaluated = await skill_check_items(db, tasks, executors, memberships)
    environment = environment_items(tasks) + await environment_prerequisite_items(db, tasks)

    checks = [
        _check("tasks_in_scope", [{"code": "TASK_OUTSIDE_MISSION", "message": "Not a task of the mission or of a "
                                   "linked executor project", "task_id": t} for t in outside] + deps_outside,
               "Every listed task and its dependencies are in the mission scope"),
        _check("criteria_have_tasks", criteria_unmet, "Every acceptance criterion has at least one task"),
        _check("executor_assigned", no_executor, "Every listed task has an executor through a mission member"),
        _check("independent_reviewer", no_reviewer,
               "Every listed task has an eligible reviewer other than its executor (reviewer pool; the per-task "
               "named reviewer is M.1e)"),
        _check("dependencies_acyclic",
               [{"code": "DEPENDENCY_CYCLE", "message": "Task dependencies form a cycle",
                 "task_ids": [str(t) for t in cycle]}] if cycle else [],
               "The dependency graph is acyclic"),
        _check("deadline_and_budget", deadline_budget, "deadline_at and budget_limit are set"),
        _check("brief_approved", await brief_items(db, mission), "The brief is approved with a final version"),
        _check("required_skills", skill_gaps, "Executors and reviewers hold the required skills"),
        _check("environment", environment, "Every listed task records its environment and prerequisites"),
    ]
    not_evaluated = [(key, message) for key, message in NOT_EVALUATED_CHECKS]
    not_evaluated += [("skill_runtime_presence", item["message"]) for item in skill_not_evaluated]
    if change_request is not None:
        not_evaluated.append((
            "change_request_review_pipeline",
            "The change request's own review stages (§3.1) are not recorded before a planning_stage exists on "
            "the change request; Marcelo decides on this plan without them",
        ))
    checks += [{"key": key, "status": "not_evaluated", "passed": None, "detail": message}
               for key, message in not_evaluated]
    return checks


# ---------------------------------------------------------------------------
# Submission
# ---------------------------------------------------------------------------
async def _active_binding(db: AsyncSession) -> tuple[PolicyBinding, PolicyVersion]:
    binding = (await db.execute(
        select(PolicyBinding).join(PolicyVersion).where(
            PolicyBinding.target_type == TARGET_TYPE, PolicyBinding.is_active.is_(True),
            PolicyVersion.status == "active",
        ).order_by(PolicyBinding.priority.desc())
    )).scalars().first()
    if binding is None:
        raise mission_error(409, "PLAN_APPROVAL_POLICY_MISSING", "No active mission plan approval policy binding")
    return binding, await db.get(PolicyVersion, binding.policy_version_id)


async def pending_submission(db: AsyncSession, mission_project_id: uuid.UUID) -> MissionPlanSubmission | None:
    return (await db.execute(
        select(MissionPlanSubmission)
        .join(ApprovalRequest, ApprovalRequest.id == MissionPlanSubmission.approval_request_id)
        .where(MissionPlanSubmission.mission_project_id == mission_project_id, ApprovalRequest.status == "pending")
        .limit(1)
    )).scalars().first()


async def open_plan_approval(
    db: AsyncSession,
    principal: ActorPrincipal,
    mission: ProjectMission,
    plan: ProjectPlan,
    task_ids: list[uuid.UUID],
    checks: list[dict[str, Any]],
    change_request: ChangeRequest | None,
    idempotency_key: str | None,
) -> tuple[ApprovalRequest, MissionPlanSubmission]:
    """Evaluate the policy and open the governed request. Caller commits."""
    binding, version = await _active_binding(db)
    plan_hash = await compute_plan_hash(db, mission, plan, task_ids)
    inputs = {
        "policy_version_id": str(version.id), "target_id": str(plan.id), "target_hash": plan_hash,
        "task_ids": sorted(str(t) for t in task_ids), "checks": [[c["key"], c["status"]] for c in checks],
    }
    input_hash = canonical_hash(inputs)
    evaluation = (await db.execute(select(PolicyEvaluation).where(
        PolicyEvaluation.policy_version_id == version.id, PolicyEvaluation.input_hash == input_hash,
    ))).scalar_one_or_none()
    if evaluation is None:
        evaluation = PolicyEvaluation(
            policy_binding_id=binding.id, policy_version_id=version.id, target_type=TARGET_TYPE,
            target_id=plan.id, target_hash=plan_hash, input_hash=input_hash,
            outcome="pass",
            result={"passed": True, "requirements": [{"key": c["key"], "status": c["status"]} for c in checks],
                    "rules": version.rules_snapshot},
            evaluator_version="structured-v1", evaluated_at=datetime.now(timezone.utc),
        )
        db.add(evaluation)
        await db.flush()
    request = ApprovalRequest(
        target_type=TARGET_TYPE, target_id=plan.id, target_hash=plan_hash, approval_type=APPROVAL_TYPE,
        policy_evaluation_id=evaluation.id, requested_by_type=principal.principal_type,
        requested_by_id=principal.principal_id, requested_by_name=principal.display_name,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=int(version.rules_snapshot.get("expires_hours", 168))),
    )
    db.add(request)
    await db.flush()
    submission = MissionPlanSubmission(
        approval_request_id=request.id, mission_project_id=mission.project_id, project_plan_id=plan.id,
        change_request_id=change_request.id if change_request is not None else None,
        task_ids=list(task_ids), plan_hash=plan_hash, checks=checks,
        submitted_by_type=principal.principal_type, submitted_by_id=principal.principal_id,
        submitted_by=principal.display_name, idempotency_key=idempotency_key,
    )
    db.add(submission)
    db.add(Notification(
        source="system", severity="info", title="Mission plan awaiting approval",
        message=f"{principal.display_name} submitted plan '{plan.name}' ({len(task_ids)} tasks) for approval.",
        event_key=f"approval:requested:{request.id}", occurred_at=datetime.now(timezone.utc),
    ))
    await db.flush()
    return request, submission


# ---------------------------------------------------------------------------
# Decision (the project_plan branch of the governed :decide)
# ---------------------------------------------------------------------------
async def _refuse_stale(
    db: AsyncSession, principal: ActorPrincipal, request: ApprovalRequest, code: str, message: str, **context,
) -> None:
    """Persist `stale` before refusing (same reason as _expire: the 409 rolls
    the session back), so the submitter must submit again."""
    request.status = "stale"
    db.add(AuditEvent(entity_type="approval_request", entity_id=request.id, event_type="approval_stale",
                      actor=principal.display_name,
                      payload={"principal_type": principal.principal_type,
                               "principal_id": str(principal.principal_id), "code": code, **context}))
    await db.commit()
    raise mission_error(409, code, message, approval_request_id=str(request.id), **context)


async def decide_plan_approval(
    db: AsyncSession,
    principal: ActorPrincipal,
    request: ApprovalRequest,
    decision: str,
    comments: str | None,
    idempotency_key: str | None,
) -> ApprovalDecisionRecord:
    # human_only (§7 item 3): the policy decides who, and in M0 that is a person
    # with admin rights. An agent token never decides a plan, delegated or not.
    if principal.principal_type != "user" or not principal.is_admin:
        raise mission_error(403, "PLAN_APPROVAL_HUMAN_ONLY",
                            "A mission plan is approved only by Marcelo (an administrator, by JWT)")
    # Two concurrent decisions serialize here and the second sees `decided`.
    request = (await db.execute(
        select(ApprovalRequest).where(ApprovalRequest.id == request.id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one()
    if idempotency_key:
        existing = (await db.execute(select(ApprovalDecisionRecord).where(
            ApprovalDecisionRecord.idempotency_key == idempotency_key
        ))).scalar_one_or_none()
        if existing:
            if existing.approval_request_id != request.id:
                raise mission_error(409, "IDEMPOTENCY_KEY_REUSED",
                                    "This idempotency key decided another approval request")
            return existing
    if request.status != "pending":
        existing = (await db.execute(select(ApprovalDecisionRecord).where(
            ApprovalDecisionRecord.approval_request_id == request.id
        ))).scalar_one_or_none()
        if existing:
            return existing
        raise mission_error(409, "APPROVAL_NOT_PENDING", f"The approval request is {request.status}",
                            status=request.status)
    if request.expires_at and request.expires_at <= datetime.now(timezone.utc):
        await _expire(db, request)

    submission = await db.get(MissionPlanSubmission, request.id)
    plan = await db.get(ProjectPlan, request.target_id)
    if submission is None or plan is None:
        raise mission_error(404, "PLAN_NOT_FOUND", "The submitted plan no longer exists")
    mission = (await db.execute(
        select(ProjectMission).where(ProjectMission.project_id == submission.mission_project_id).with_for_update()
    )).scalar_one()
    evaluation = await db.get(PolicyEvaluation, request.policy_evaluation_id)
    version = await db.get(PolicyVersion, evaluation.policy_version_id)
    if bool(version.rules_snapshot.get("deny_self_approval", True)) and (
        (principal.principal_type, principal.principal_id) == (request.requested_by_type, request.requested_by_id)
    ):
        raise mission_error(403, "SEPARATION_OF_DUTIES", "The submitter cannot decide its own plan")

    if decision == "approved":
        change_request = await db.get(ChangeRequest, submission.change_request_id) if submission.change_request_id else None
        if change_request is None:
            if mission.state != "planning" or mission.planning_stage != "baseline":
                await _refuse_stale(db, principal, request, "PLAN_SUBMISSION_STALE",
                                    "The mission is no longer at the planning baseline stage",
                                    state=mission.state, planning_stage=mission.planning_stage)
        elif change_request.status != "approved" or mission.state not in CR_MISSION_STATES:
            await _refuse_stale(db, principal, request, "PLAN_SUBMISSION_STALE",
                                "The change request is no longer approved, or the mission left execution",
                                change_request_status=change_request.status, state=mission.state)
        if plan.status != "draft":
            await _refuse_stale(db, principal, request, "PLAN_SUBMISSION_STALE", f"The plan is {plan.status}, not draft",
                                plan_status=plan.status)
        current = await compute_plan_hash(db, mission, plan, list(submission.task_ids))
        if current != request.target_hash:
            await _refuse_stale(db, principal, request, "PLAN_CHANGED_SINCE_SUBMISSION",
                                "The plan or one of its tasks changed after it was submitted; submit it again",
                                submitted_hash=request.target_hash, current_hash=current)

    record = ApprovalDecisionRecord(
        approval_request_id=request.id, decision=decision, decided_by_type=principal.principal_type,
        decided_by_id=principal.principal_id, decided_by_name=principal.display_name, authority_source="admin",
        delegation_id=None, comments=comments, idempotency_key=idempotency_key,
    )
    db.add(record)
    request.status = "decided"
    baseline = None
    if decision == "approved":
        now = datetime.now(timezone.utc)
        plan.status = "approved"
        plan.approved_at = now
        try:
            baseline = await create_mission_baseline(
                db, mission, plan, list(submission.task_ids),
                name=f"{plan.name} (baseline)", actor=principal.display_name,
            )
        except BaselineCreationError as exc:
            raise mission_error(409, "BASELINE_NOT_CREATED", str(exc)) from exc
        submission.baseline_id = baseline.id
        if submission.change_request_id is not None:
            change_request = await db.get(ChangeRequest, submission.change_request_id)
            change_request.status = "applied"
    await db.flush()
    db.add(AuditEvent(
        entity_type="approval_request", entity_id=request.id, event_type=f"approval_{decision}",
        actor=principal.display_name,
        payload={"principal_type": principal.principal_type, "principal_id": str(principal.principal_id),
                 "authority_source": "admin", "delegation_id": None, "target_hash": request.target_hash},
    ))
    db.add(AuditEvent(
        entity_type="mission", entity_id=mission.project_id, event_type=f"mission_plan_{decision}",
        actor=principal.display_name,
        payload={"principal_type": principal.principal_type, "principal_id": str(principal.principal_id),
                 "authority_source": "admin", "delegation_id": None, "idempotency_key": idempotency_key,
                 "approval_request_id": str(request.id), "project_plan_id": str(plan.id),
                 "baseline_id": str(baseline.id) if baseline else None,
                 "change_request_id": str(submission.change_request_id) if submission.change_request_id else None,
                 "reason": comments},
    ))
    return record

"""Mission task commands: assign, request review, return (Plano Integrado M0.2c).

Contract: docs/architecture/MCP_MISSION_TOOLS_SPEC.md §5.5, §5.11, §5.12
(D-M0-5); dispatch (§5.6) and report (§5.7) extend ``routes/task.py``.

- ``POST /api/v1/missions/{id}/tasks/{task_id}:assign``          assign_task
- ``POST /api/v1/missions/{id}/tasks/{task_id}:request-review``  request_task_review
- ``POST /api/v1/missions/{id}/tasks/{task_id}:return``          return_task_for_correction

All three sit behind ``MISSION_TOOLS_ENABLED`` and the §0.4 receipts, take a
task of the mission's scope (its own tasks and its executor projects'; any
other is 404) and refuse while the task has a run in flight
(``core/mission_dispatch.py``). A person must be admin; an agent must be the
orchestrator or an active member (else 404, no existence leak) and hold the
delegation each command names. Errors use the §0.3 object form.
"""
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.mission import _active_membership, _audit_payload, _load
from app.api.routes.orchestration import assert_review_independent
from app.api.schemas.mission import (
    ReviewRequestIn,
    ReviewRequestOut,
    TaskAssignIn,
    TaskAssignOut,
    TaskReturnIn,
    TaskReturnOut,
)
from app.core.command_receipts import (
    begin_command,
    enforce_command_limits,
    limit_command_body,
    record_command,
    request_hash,
    require_mission_tools,
)
from app.core.deps import ActorPrincipal, authorize_action, get_actor_principal
from app.core.dispatch_signal import wake_scheduled_dispatch
from app.core.mission import mission_error, project_id_for_task_source
from app.core.mission_dispatch import OPEN_REVIEW_STATUSES, in_flight_error, task_run_in_flight
from app.core.mission_plan import NON_EXECUTOR_ROLES, mission_scope_tasks
from app.core.task_completion_guard import resolve_executor_agent_id
from app.db.base import get_db
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent
from app.db.models.mission import ProjectMission
from app.db.models.orchestration import ProjectAgentMembership, TaskExecutionReview
from app.db.models.project import Project
from app.db.models.task import ProjectTask, TaskAssignment, TaskExecution

router = APIRouter(prefix="/api/v1/missions", tags=["missions"])

ASSIGN_ACTION = "planning.execution.manage"
ORCHESTRATE_ACTION = "mission.orchestrate"
TERMINAL_TASK_STATUSES = ("done", "deployed", "cancelled")
COMMAND_DEPENDENCIES = [Depends(require_mission_tools), Depends(limit_command_body)]


async def _authorize(
    db: AsyncSession, principal: ActorPrincipal, mission: ProjectMission, action: str,
    task_project_id: uuid.UUID,
) -> tuple[str, Any]:
    """Admin; or an agent that is the orchestrator or an active member of the
    mission (else 404) with `action` delegated on the mission or on the task's
    own (executor) project."""
    if principal.principal_type == "user":
        if not principal.is_admin:
            raise mission_error(403, "MISSION_ADMIN_ONLY", "Only an administrator acts on a mission in M0")
        return "admin", None
    if principal.principal_id != mission.orchestrator_agent_id and not await _active_membership(
        db, mission.project_id, principal.principal_id,
    ):
        raise mission_error(404, "MISSION_NOT_FOUND", "Mission not found")
    for project_id in dict.fromkeys((mission.project_id, task_project_id)):
        try:
            return await authorize_action(db, principal, action, project_id=project_id)
        except HTTPException as exc:
            if exc.status_code != 403:
                raise
    raise mission_error(403, "DELEGATION_REQUIRED", f"No active delegation permits {action} here", action=action)


async def _scope_task(db: AsyncSession, mission: ProjectMission, task_id: uuid.UUID) -> tuple[ProjectTask, uuid.UUID]:
    task = (await mission_scope_tasks(db, mission.project_id)).get(task_id)
    if task is None:
        raise mission_error(404, "TASK_NOT_FOUND", "Task not found in this mission")
    return task, await project_id_for_task_source(db, task.planning_item_id, task.change_request_id)


async def _execution(db: AsyncSession, task: ProjectTask, execution_id: uuid.UUID) -> TaskExecution:
    execution = await db.get(TaskExecution, execution_id)
    if execution is None or execution.task_id != task.id:
        raise mission_error(404, "EXECUTION_NOT_FOUND", "Execution not found for this task")
    return execution


async def _open_reviews(db: AsyncSession, task_id: uuid.UUID) -> list[TaskExecutionReview]:
    return list((await db.execute(
        select(TaskExecutionReview)
        .join(TaskExecution, TaskExecution.id == TaskExecutionReview.execution_id)
        .where(TaskExecution.task_id == task_id, TaskExecutionReview.status.in_(OPEN_REVIEW_STATUSES))
        .order_by(TaskExecutionReview.created_at)
    )).scalars())


def _refuse_terminal(task: ProjectTask) -> None:
    if task.status in TERMINAL_TASK_STATUSES:
        raise mission_error(409, "TASK_TERMINAL", f"Task is already {task.status}", status=task.status)


# ---------------------------------------------------------------------------
# assign_task (§5.5)
# ---------------------------------------------------------------------------
@router.post("/{project_id}/tasks/{task_id}:assign", response_model=TaskAssignOut,
             status_code=status.HTTP_201_CREATED, dependencies=COMMAND_DEPENDENCIES)
async def assign_task(
    project_id: uuid.UUID,
    task_id: uuid.UUID,
    payload: TaskAssignIn,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
):
    """Assign (or reassign) a mission task to an agent with an active executor
    membership in the task's project. Replacing an active assignment also needs
    mission.orchestrate; the previous one is released, never deleted. The
    assignee is not in the baseline hash (D-M0-3), so a baselined task can be
    reassigned without a change request. Refused: a non-executor role or a
    non-member (422 ASSIGNEE_NOT_ELIGIBLE), the reviewer of an open review
    (409 ASSIGNEE_IS_REVIEWER), a run in flight (409 TASK_RUN_IN_FLIGHT)."""
    enforce_command_limits(principal)
    command = "mission.assign_task"
    body_hash = request_hash(command, {"project_id": str(project_id), "task_id": str(task_id),
                                       **payload.model_dump(mode="json")})
    _project, mission = await _load(db, project_id, lock=True)
    task, task_project_id = await _scope_task(db, mission, task_id)
    source, delegation = await _authorize(db, principal, mission, ASSIGN_ACTION, task_project_id)
    replay = await begin_command(db, principal, payload.idempotency_key, command, body_hash)
    if replay is not None:
        return replay
    _refuse_terminal(task)

    agent = await db.get(Agent, payload.agent_id)
    if agent is None or not agent.is_active or agent.status != "active":
        raise mission_error(422, "ASSIGNEE_NOT_ELIGIBLE", "The agent is not active", reason="agent_inactive")
    membership = await _active_membership(db, task_project_id, agent.id)
    if membership is None:
        raise mission_error(422, "ASSIGNEE_NOT_ELIGIBLE", "The agent has no active membership in the task's project",
                            reason="not_a_member", project_id=str(task_project_id))
    if membership.role in NON_EXECUTOR_ROLES:
        raise mission_error(422, "ASSIGNEE_NOT_ELIGIBLE", f"The role {membership.role} does not execute tasks",
                            reason="non_executor_role", role=membership.role)
    for review in await _open_reviews(db, task.id):
        reviewer = await db.get(ProjectAgentMembership, review.reviewer_membership_id)
        if reviewer is not None and reviewer.agent_id == agent.id:
            raise mission_error(409, "ASSIGNEE_IS_REVIEWER", "The agent reviews this task; it cannot execute it",
                                review_id=str(review.id))
    in_flight = await task_run_in_flight(db, task.id)
    if in_flight is not None:
        raise in_flight_error(in_flight)

    active = list((await db.execute(
        select(TaskAssignment).where(TaskAssignment.task_id == task.id, TaskAssignment.status == "active")
        .order_by(TaskAssignment.created_at.desc())
    )).scalars())
    same = next((a for a in active if a.agent_id == agent.id and a.membership_id == membership.id), None)
    if same is not None and len(active) == 1:
        out = TaskAssignOut(task_id=task.id, assignment_id=same.id, membership_id=membership.id, agent_id=agent.id,
                            task_status=task.status, changed=False)
        record_command(db, principal, payload.idempotency_key, command, body_hash, 200, out.model_dump(mode="json"),
                       target_type="task_assignment", target_id=same.id)
        await db.commit()
        return out
    if active and principal.principal_type == "agent":
        source, delegation = await _authorize(db, principal, mission, ORCHESTRATE_ACTION, task_project_id)

    now = datetime.now(timezone.utc)
    for previous in active:
        previous.status = "released"
        previous.unassigned_at = now
    assignment = TaskAssignment(task_id=task.id, agent_id=agent.id, membership_id=membership.id, assigned_at=now)
    db.add(assignment)
    if task.status == "planned":
        task.status = "assigned"
    await db.flush()
    previous_id = active[0].id if active else None
    db.add(AuditEvent(
        entity_type="project_task", entity_id=task.id,
        event_type="task_reassigned" if active else "task_assigned", actor=principal.display_name,
        payload=_audit_payload(principal, source, delegation, idempotency_key=payload.idempotency_key,
                               reason=payload.reason, mission_project_id=str(project_id),
                               assignment_id=str(assignment.id), agent_id=str(agent.id),
                               membership_id=str(membership.id),
                               previous_assignment_ids=[str(a.id) for a in active]),
    ))
    out = TaskAssignOut(task_id=task.id, assignment_id=assignment.id, membership_id=membership.id, agent_id=agent.id,
                        previous_assignment_id=previous_id, task_status=task.status, changed=True)
    record_command(db, principal, payload.idempotency_key, command, body_hash, 201, out.model_dump(mode="json"),
                   target_type="task_assignment", target_id=assignment.id)
    await db.commit()
    return out


# ---------------------------------------------------------------------------
# request_task_review (§5.11)
# ---------------------------------------------------------------------------
def _review_body(task: ProjectTask, execution: TaskExecution, review: TaskExecutionReview) -> str:
    evidence = execution.evidence_ref or "(nenhuma)"
    return "\n\n".join([
        f"Revisão da Task #{task.number}: {task.title}",
        f"Execução {execution.id} (tentativa {execution.attempt_number}), status {execution.status}.",
        f"Resumo relatado pelo executor:\n{execution.outcome_summary or '(sem resumo)'}",
        f"Evidência: {evidence}",
        "Revise a entrega contra a tarefa e a evidência. Decida com a sua própria credencial em "
        f"PATCH /api/v1/orchestration/reviews/{review.id} (status approved, changes_requested ou rejected, "
        "com feedback obrigatório). Você não pode revisar o que você mesmo executou.",
    ])


@router.post("/{project_id}/tasks/{task_id}:request-review", response_model=ReviewRequestOut,
             status_code=status.HTTP_201_CREATED, dependencies=COMMAND_DEPENDENCIES)
async def request_task_review(
    project_id: uuid.UUID,
    task_id: uuid.UUID,
    payload: ReviewRequestIn,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
):
    """Open a pending review of a verified execution and send the reviewer a
    Messages Task (origin = the task, no execution of its own, through the
    normal queue). The reviewer decides on PATCH /orchestration/reviews/{id}
    with its own agt_. Refused: the executor (or its sub-agent) as reviewer,
    a membership without can_review, an execution not yet verified (409
    EXECUTION_NOT_VERIFIED), a review already open (409 REVIEW_ALREADY_OPEN)."""
    enforce_command_limits(principal)
    command = "mission.request_task_review"
    body_hash = request_hash(command, {"project_id": str(project_id), "task_id": str(task_id),
                                       **payload.model_dump(mode="json")})
    _project, mission = await _load(db, project_id, lock=True)
    task, task_project_id = await _scope_task(db, mission, task_id)
    source, delegation = await _authorize(db, principal, mission, ORCHESTRATE_ACTION, task_project_id)
    replay = await begin_command(db, principal, payload.idempotency_key, command, body_hash)
    if replay is not None:
        return replay
    _refuse_terminal(task)
    execution = await _execution(db, task, payload.execution_id)
    if execution.status != "verified":
        raise mission_error(409, "EXECUTION_NOT_VERIFIED",
                            "Only a verified execution is reviewed; the evidence check comes first",
                            execution_status=execution.status)
    open_reviews = await _open_reviews(db, task.id)
    if open_reviews:
        raise mission_error(409, "REVIEW_ALREADY_OPEN", "This task already has an open review",
                            review_id=str(open_reviews[0].id))
    reviewer = (await db.execute(select(ProjectAgentMembership).where(
        ProjectAgentMembership.agent_id == payload.reviewer_agent_id,
        ProjectAgentMembership.project_id.in_(list(dict.fromkeys((task_project_id, mission.project_id)))),
        ProjectAgentMembership.status == "active",
        ProjectAgentMembership.can_review.is_(True),
    ).order_by(ProjectAgentMembership.created_at))).scalars().first()
    if reviewer is None:
        raise mission_error(422, "REVIEWER_NOT_ELIGIBLE",
                            "The reviewer needs an active membership with can_review in this mission")
    try:
        await assert_review_independent(db, execution, reviewer, task_project_id)
    except HTTPException as exc:
        code = "REVIEWER_IS_EXECUTOR" if exc.status_code == 409 else "REVIEWER_NOT_ELIGIBLE"
        raise mission_error(exc.status_code, code, str(exc.detail)) from exc

    review = TaskExecutionReview(execution_id=execution.id, reviewer_membership_id=reviewer.id, status="pending")
    db.add(review)
    await db.flush()
    project = await db.get(Project, task_project_id)
    orchestrator = await db.get(Agent, mission.orchestrator_agent_id) if mission.orchestrator_agent_id else None
    now = datetime.now(timezone.utc)
    # No task_execution_id: the review run must never close the executor's
    # execution (_finalize_dispatch writes there). It still carries the task
    # as its origin, so it holds the task's targets while it runs.
    demand = AgentDemand(
        from_agent=orchestrator.name if orchestrator else "forgehub",
        from_agent_id=orchestrator.id if orchestrator else None,
        subject=f"Revisão: Task #{task.number} — {task.title}"[:255],
        body=_review_body(task, execution, review),
        status="new", target_agent_id=payload.reviewer_agent_id, project_id=task_project_id,
        working_path=project.working_directory_path if project else None,
        origin_type="task", origin_id=task.id, channel="factory", channel_ref=str(task.id),
        requires_response=False, scheduled_at=now,
    )
    db.add(demand)
    await db.flush()
    review.runtime_session_ref = str(demand.id)
    db.add(AuditEvent(
        entity_type="project_task", entity_id=task.id, event_type="review_requested", actor=principal.display_name,
        payload=_audit_payload(principal, source, delegation, idempotency_key=payload.idempotency_key,
                               mission_project_id=str(project_id), execution_id=str(execution.id),
                               review_id=str(review.id), reviewer_membership_id=str(reviewer.id),
                               reviewer_agent_id=str(payload.reviewer_agent_id), demand_id=str(demand.id)),
    ))
    out = ReviewRequestOut(task_id=task.id, execution_id=execution.id, review_id=review.id,
                           reviewer_membership_id=reviewer.id, reviewer_agent_id=payload.reviewer_agent_id,
                           status=review.status, demand_id=demand.id, demand_number=demand.number)
    record_command(db, principal, payload.idempotency_key, command, body_hash, 201, out.model_dump(mode="json"),
                   target_type="task_execution_review", target_id=review.id)
    await db.commit()
    wake_scheduled_dispatch()
    return out


# ---------------------------------------------------------------------------
# return_task_for_correction (§5.12)
# ---------------------------------------------------------------------------
@router.post("/{project_id}/tasks/{task_id}:return", response_model=TaskReturnOut,
             dependencies=COMMAND_DEPENDENCIES)
async def return_task_for_correction(
    project_id: uuid.UUID,
    task_id: uuid.UUID,
    payload: TaskReturnIn,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
):
    """Send a delivery back: an open review becomes changes_requested with the
    reason as feedback (else the reason is recorded as
    mission_task_returned); the task goes back to in_progress. Nothing is
    redispatched -- the orchestrator dispatches explicitly (04 §1), and the
    next dispatch carries the reason (§6). Marcelo, or an agent with
    mission.orchestrate that is not the executor. A review run not yet
    started is withdrawn (archived); a run in flight refuses (409)."""
    enforce_command_limits(principal)
    command = "mission.return_task_for_correction"
    body_hash = request_hash(command, {"project_id": str(project_id), "task_id": str(task_id),
                                       **payload.model_dump(mode="json")})
    _project, mission = await _load(db, project_id, lock=True)
    task, task_project_id = await _scope_task(db, mission, task_id)
    source, delegation = await _authorize(db, principal, mission, ORCHESTRATE_ACTION, task_project_id)
    execution = await _execution(db, task, payload.execution_id)
    if principal.principal_type == "agent" and principal.principal_id == await resolve_executor_agent_id(db, execution):
        raise mission_error(403, "EXECUTOR_CANNOT_RETURN", "The executor does not return its own delivery")
    replay = await begin_command(db, principal, payload.idempotency_key, command, body_hash)
    if replay is not None:
        return replay
    _refuse_terminal(task)

    # A review Task that has not started is withdrawn with the return; one
    # that runs (or whose outcome is unknown) refuses below.
    for queued in (await db.execute(select(AgentDemand).where(
        AgentDemand.origin_type == "task", AgentDemand.origin_id == task.id,
        AgentDemand.task_execution_id.is_(None), AgentDemand.dispatch_status.is_(None),
        AgentDemand.agent_run_id.is_(None), AgentDemand.status != "archived",
    ))).scalars():
        queued.status = "archived"
    await db.flush()
    in_flight = await task_run_in_flight(db, task.id)
    if in_flight is not None:
        raise in_flight_error(in_flight)

    open_review = next((r for r in await _open_reviews(db, task.id) if r.execution_id == execution.id), None)
    now = datetime.now(timezone.utc)
    if open_review is not None:
        open_review.status = "changes_requested"
        open_review.feedback = payload.reason
        open_review.decided_at = now
    previous_status = task.status
    task.status = "in_progress"
    db.add(AuditEvent(
        entity_type="project_task", entity_id=task.id, event_type="mission_task_returned",
        actor=principal.display_name,
        payload=_audit_payload(principal, source, delegation, idempotency_key=payload.idempotency_key,
                               reason=payload.reason, mission_project_id=str(project_id),
                               execution_id=str(execution.id), previous_status=previous_status,
                               review_id=str(open_review.id) if open_review else None),
    ))
    out = TaskReturnOut(task_id=task.id, execution_id=execution.id, task_status=task.status,
                        review_id=open_review.id if open_review else None,
                        review_status=open_review.status if open_review else None)
    record_command(db, principal, payload.idempotency_key, command, body_hash, 200, out.model_dump(mode="json"),
                   target_type="project_task", target_id=task.id)
    await db.commit()
    return out

"""Mission plan submission and withdrawal (Plano Integrado M0.2b).

Contract: docs/architecture/MCP_MISSION_TOOLS_SPEC.md §5.3 and §7; the core
is ``core/mission_plan.py``.

- ``POST /api/v1/missions/{id}/plans:submit``               submit_project_plan: proposes, never approves
- ``POST /api/v1/missions/{id}/plans/{plan_id}:withdraw``   retracts a pending submission (status ``withdrawn``, D-M0-4)

Marcelo decides on ``POST /api/v1/governed/approval-requests/{id}:decide``
(the ``project_plan`` branch). Both writes sit behind ``MISSION_TOOLS_ENABLED``
and the §0.4 receipts; errors use the §0.3 object form.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.mission import _audit_payload, _load
from app.api.schemas.mission import PlanSubmitIn, PlanSubmitOut, PlanWithdrawIn, PlanWithdrawOut
from app.core.command_receipts import (
    begin_command,
    enforce_command_limits,
    limit_command_body,
    record_command,
    request_hash,
    require_mission_tools,
)
from app.core.deps import ActorPrincipal, authorize_action, get_actor_principal
from app.core.mission import mission_error
from app.core.mission_plan import (
    CR_MISSION_STATES,
    open_plan_approval,
    pending_submission,
    plan_checks,
)
from app.core.mission_records import current_plan_version
from app.db.base import get_db
from app.db.models.governance import ApprovalRequest, AuditEvent
from app.db.models.mission import MissionPlanSubmission, MissionPlanVersion, ProjectMission
from app.db.models.orchestration import ProjectAgentMembership
from app.db.models.project import ChangeRequest, ProjectPlan

router = APIRouter(prefix="/api/v1/missions", tags=["missions"])

SUBMIT_ACTION = "mission.plan.submit"


async def _authorize_submitter(
    db: AsyncSession, principal: ActorPrincipal, mission: ProjectMission,
) -> tuple[str, Any]:
    """Admin; or an agent with `mission.plan.submit` on the mission that is its
    orchestrator or one of its active members."""
    if principal.principal_type == "user":
        if not principal.is_admin:
            raise mission_error(403, "MISSION_ADMIN_ONLY", "Only an administrator acts on a mission in M0")
        return "admin", None
    member = principal.principal_id == mission.orchestrator_agent_id or await db.scalar(
        select(ProjectAgentMembership.id).where(
            ProjectAgentMembership.project_id == mission.project_id,
            ProjectAgentMembership.agent_id == principal.principal_id,
            ProjectAgentMembership.status == "active",
        ).limit(1)
    )
    if not member:
        raise mission_error(403, "MISSION_ACTOR_NOT_ALLOWED", "Only the orchestrator or a member submits a plan")
    try:
        return await authorize_action(db, principal, SUBMIT_ACTION, project_id=mission.project_id)
    except HTTPException as exc:
        if exc.status_code != 403:
            raise
        raise mission_error(403, "DELEGATION_REQUIRED", f"No active delegation permits {SUBMIT_ACTION} here",
                            action=SUBMIT_ACTION) from exc


def _same_fields(plan: ProjectPlan, fields: dict[str, Any]) -> list[str]:
    differ = []
    for key, value in fields.items():
        current = getattr(plan, key)
        if key == "estimated_cost":
            current = None if current is None else Decimal(str(current))
            value = None if value is None else Decimal(str(value))
        if current != value:
            differ.append(key)
    return differ


@router.post("/{project_id}/plans:submit", response_model=PlanSubmitOut, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_mission_tools), Depends(limit_command_body)])
async def submit_project_plan(
    project_id: uuid.UUID,
    payload: PlanSubmitIn,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
):
    """submit_project_plan (§5.3): the automatic checks, then a pending
    governed request. Initial baseline: the mission is planning at stage
    `baseline` and the plan is its reviewed current version. After the
    baseline: an approved change request of the mission and a new plan
    version that applies it (§7 item 6). Refusals: 409 PLAN_CHECKS_FAILED
    (with the checks), PLAN_ALREADY_PENDING (with its id),
    MISSION_NOT_DRAFT_OR_CR, PLANNING_PIPELINE_UNFINISHED."""
    enforce_command_limits(principal)
    command = "mission.submit_project_plan"
    body_hash = request_hash(command, {"project_id": str(project_id), **payload.model_dump(mode="json")})
    _project, mission = await _load(db, project_id, lock=True)
    source, delegation = await _authorize_submitter(db, principal, mission)
    replay = await begin_command(db, principal, payload.idempotency_key, command, body_hash)
    if replay is not None:
        return replay

    task_ids = list(dict.fromkeys(payload.task_ids))
    change_request = None
    if mission.state == "planning":
        if payload.change_request_id is not None:
            raise mission_error(422, "CHANGE_REQUEST_AFTER_BASELINE_ONLY",
                                "A change request plan is submitted after the first baseline, not in planning")
        if mission.planning_stage != "baseline":
            raise mission_error(409, "PLANNING_PIPELINE_UNFINISHED",
                                "The planning pipeline has not reached baseline (P8)",
                                planning_stage=mission.planning_stage)
    elif mission.state in CR_MISSION_STATES:
        if payload.change_request_id is None:
            raise mission_error(422, "CHANGE_REQUEST_REQUIRED",
                                "After the baseline a plan only applies an approved change request")
        change_request = await db.get(ChangeRequest, payload.change_request_id)
        if change_request is None or change_request.project_id != project_id:
            raise mission_error(404, "CHANGE_REQUEST_NOT_FOUND", "Change request not found in this mission")
        if change_request.status != "approved":
            raise mission_error(409, "CHANGE_REQUEST_NOT_APPROVED", "Only an approved change request is applied",
                                change_request_status=change_request.status)
        if payload.plan is None:
            raise mission_error(422, "PLAN_REQUIRED", "A change request plan needs its plan fields")
    else:
        raise mission_error(409, "MISSION_NOT_DRAFT_OR_CR",
                            "A plan is submitted at the planning baseline stage or to apply a change request",
                            state=mission.state)

    pending = await pending_submission(db, project_id)
    if pending is not None:
        raise mission_error(409, "PLAN_ALREADY_PENDING", "This mission already has a plan awaiting approval",
                            approval_request_id=str(pending.approval_request_id),
                            plan_id=str(pending.project_plan_id))

    if change_request is None:
        plan, _version, unmet = await current_plan_version(db, project_id)
        if unmet:
            raise mission_error(409, unmet[0]["code"], unmet[0]["message"])
        if payload.plan is not None:
            differ = _same_fields(plan, payload.plan.model_dump())
            if differ:
                raise mission_error(409, "PLAN_DIFFERS_FROM_REVIEWED_VERSION",
                                    "The reviewed plan version is submitted as it is; register a new version "
                                    "(which restarts the pipeline) to change it",
                                    project_plan_id=str(plan.id), fields=differ)
    else:
        for old in (await db.execute(select(ProjectPlan).where(
            ProjectPlan.project_id == project_id, ProjectPlan.status == "draft",
        ))).scalars():
            old.status = "superseded"
        plan = ProjectPlan(project_id=project_id, status="draft", change_request_id=change_request.id,
                           **payload.plan.model_dump())
        db.add(plan)
        await db.flush()
        db.add(MissionPlanVersion(project_plan_id=plan.id, mission_project_id=project_id,
                                  author_type=principal.principal_type, author_id=principal.principal_id,
                                  author_name=principal.display_name))

    checks = await plan_checks(db, mission, task_ids, change_request)
    failed = [c for c in checks if c["status"] == "failed"]
    if failed:
        raise mission_error(409, "PLAN_CHECKS_FAILED", "The plan does not pass the automatic checks",
                            checks=checks)
    request, submission = await open_plan_approval(
        db, principal, mission, plan, task_ids, checks, change_request, payload.idempotency_key,
    )
    db.add(AuditEvent(
        entity_type="mission", entity_id=project_id, event_type="plan_submitted", actor=principal.display_name,
        payload=_audit_payload(principal, source, delegation, idempotency_key=payload.idempotency_key,
                               approval_request_id=str(request.id), project_plan_id=str(plan.id),
                               plan_hash=submission.plan_hash, task_ids=[str(t) for t in task_ids],
                               change_request_id=str(change_request.id) if change_request else None),
    ))
    out = PlanSubmitOut(plan_id=plan.id, approval_request_id=request.id, plan_hash=submission.plan_hash,
                        checks=checks, change_request_id=submission.change_request_id, task_ids=task_ids)
    record_command(db, principal, payload.idempotency_key, command, body_hash, 201, out.model_dump(mode="json"),
                   target_type="approval_request", target_id=request.id)
    await db.commit()
    return out


@router.post("/{project_id}/plans/{plan_id}:withdraw", response_model=PlanWithdrawOut,
             dependencies=[Depends(require_mission_tools), Depends(limit_command_body)])
async def withdraw_plan_submission(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    payload: PlanWithdrawIn,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
) -> PlanWithdrawOut:
    """The submitter (or Marcelo, or the orchestrator) retracts a pending
    plan submission: the request becomes `withdrawn` and the plan stays
    `draft`. Nothing is deleted; withdrawing again returns the same result."""
    enforce_command_limits(principal)
    _project, mission = await _load(db, project_id, lock=True)
    submission = (await db.execute(
        select(MissionPlanSubmission)
        .join(ApprovalRequest, ApprovalRequest.id == MissionPlanSubmission.approval_request_id)
        .where(MissionPlanSubmission.mission_project_id == project_id,
               MissionPlanSubmission.project_plan_id == plan_id)
        .order_by(MissionPlanSubmission.created_at.desc()).limit(1)
    )).scalars().first()
    if submission is None:
        raise mission_error(404, "PLAN_SUBMISSION_NOT_FOUND", "No submission of this plan in this mission")
    request = (await db.execute(
        select(ApprovalRequest).where(ApprovalRequest.id == submission.approval_request_id).with_for_update()
    )).scalar_one()
    plan = await db.get(ProjectPlan, plan_id)

    source, delegation = "submitter", None
    if principal.principal_type == "user":
        if not principal.is_admin:
            raise mission_error(403, "MISSION_ADMIN_ONLY", "Only an administrator acts on a mission in M0")
        source = "admin"
    elif (principal.principal_type, principal.principal_id) == (submission.submitted_by_type,
                                                              submission.submitted_by_id):
        source, delegation = await _authorize_submitter(db, principal, mission)
    elif principal.principal_id == mission.orchestrator_agent_id:
        source, delegation = await authorize_action(db, principal, "mission.orchestrate", project_id=project_id)
    else:
        raise mission_error(403, "NOT_PLAN_SUBMITTER", "Only the submitter, the orchestrator or Marcelo withdraws")

    if request.status == "pending":
        now = datetime.now(timezone.utc)
        request.status = "withdrawn"
        submission.withdrawn_at = now
        submission.withdrawn_by = principal.display_name
        submission.withdrawn_reason = payload.reason
        db.add(AuditEvent(
            entity_type="mission", entity_id=project_id, event_type="plan_submission_withdrawn",
            actor=principal.display_name,
            payload=_audit_payload(principal, source, delegation, reason=payload.reason,
                                   approval_request_id=str(request.id), project_plan_id=str(plan_id)),
        ))
        await db.commit()
    elif request.status != "withdrawn":
        raise mission_error(409, "APPROVAL_NOT_PENDING", f"The approval request is {request.status}",
                            status=request.status, approval_request_id=str(request.id))
    return PlanWithdrawOut(
        plan_id=plan_id, approval_request_id=request.id, status=request.status,
        plan_status=plan.status if plan else "unknown", withdrawn_at=submission.withdrawn_at,
        withdrawn_by=submission.withdrawn_by, withdrawn_reason=submission.withdrawn_reason,
    )

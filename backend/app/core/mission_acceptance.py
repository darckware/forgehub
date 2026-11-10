"""Final delivery acceptance: immutable evidence, independent review, human decision.

Uses the existing governed approval ledger; callers own the transaction.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.governed_approval import _expire, canonical_hash
from app.core.mission import _criteria, _criterion_task_ids, mission_error
from app.core.mission_dossier import DossierUnverifiable, verify_dossier
from app.core.mission_plan import mission_scope_tasks
from app.core.plan_baseline import mission_content_part, task_content_part
from app.core.task_completion_guard import assert_task_completion_allowed
from app.db.models.governance import (
    ApprovalDecisionRecord, ApprovalRequest, AuditEvent, AuthorityDelegation,
    PolicyBinding, PolicyEvaluation, PolicyVersion,
)
from app.db.models.mission import MissionDossier, ProjectMission
from app.db.models.orchestration import TaskExecutionReview
from app.db.models.project import ChangeRequest, Project
from app.db.models.task import TaskExecution


def require_human(principal):
    if principal.principal_type != "user" or not principal.is_admin:
        raise mission_error(403, "ACCEPTANCE_RESERVED_TO_MARCELO", "Only an administrator can accept a mission")


async def delivery_snapshot(db, mission, dossier):
    """Recheck facts, not stored labels. Bind the decision to the same delivery."""
    try:
        valid = await verify_dossier(db, mission.project_id, dossier.artifact_version_id, dossier.file_sha256)
    except DossierUnverifiable as exc:
        raise mission_error(409, "DOSSIER_CONTENT_UNVERIFIABLE", str(exc)) from exc
    if not valid:
        raise mission_error(409, "DOSSIER_CONTENT_CHANGED", "Dossier bytes changed since registration")
    criteria = await _criteria(db, mission.project_id)
    linked = await _criterion_task_ids(db, [c.id for c in criteria])
    if not criteria or any(c.status != "proven" or not (c.evidence_ref or "").strip() or not linked[c.id]
                           for c in criteria):
        raise mission_error(409, "CRITERIA_NOT_ALL_PROVEN", "Every criterion needs proven evidence and linked tasks")
    tasks = await mission_scope_tasks(db, mission.project_id)
    if not tasks or any(tid not in tasks for ids in linked.values() for tid in ids):
        raise mission_error(409, "ACCEPTANCE_TASK_SCOPE_INVALID", "Criterion tasks must belong to this mission")
    proofs = []
    for task in sorted(tasks.values(), key=lambda row: str(row.id)):
        if task.status == "cancelled":
            cr = await db.get(ChangeRequest, task.change_request_id) if task.change_request_id else None
            if cr is None or cr.status not in ("approved", "applied"):
                raise mission_error(409, "CANCELLATION_NOT_APPROVED", "Cancelled work needs an approved change request")
            proofs.append([str(task.id), task.status, str(cr.id)])
            continue
        if task.status not in ("done", "deployed"):
            raise mission_error(409, "ACCEPTANCE_TASK_OPEN", "Every delivery task must be accepted", task_id=str(task.id))
        proof = await assert_task_completion_allowed(db, task, "done")
        open_review = await db.scalar(select(TaskExecutionReview.id).join(
            TaskExecution, TaskExecution.id == TaskExecutionReview.execution_id).where(
                TaskExecution.task_id == task.id, TaskExecutionReview.status == "changes_requested",
                TaskExecution.id == proof.execution_id))
        if open_review:
            raise mission_error(409, "ACCEPTANCE_REVIEW_OPEN", "The current delivery still has requested changes")
        proofs.append([str(task.id), task.status, str(proof.execution_id), proof.evidence_ref, str(proof.review_id)])
    return canonical_hash({"baseline": mission.current_baseline_id, "brief": mission.brief_artifact_id,
        "dossier": [dossier.id, dossier.artifact_version_id, dossier.file_sha256], "tasks": proofs,
        "mission_contract": await mission_content_part(db, mission),
        "task_contracts": [await task_content_part(db, task) for task in sorted(tasks.values(), key=lambda t: str(t.id))],
        "criteria": [[str(c.id), c.status, c.evidence_ref, c.statement, c.verification_method,
                       str(c.verifier_agent_id), c.verifier_is_marcelo, sorted(map(str, linked[c.id]))]
                      for c in sorted(criteria, key=lambda row: str(row.id))]})


async def latest_dossier(db, project_id):
    dossier = await db.scalar(select(MissionDossier).where(MissionDossier.mission_project_id == project_id)
        .order_by(MissionDossier.created_at.desc(), MissionDossier.id.desc()).limit(1))
    if dossier is None:
        raise mission_error(409, "DOSSIER_MISSING", "Register a validation dossier before requesting acceptance")
    return dossier


async def open_acceptance(db, principal, mission):
    if mission.state != "awaiting_acceptance":
        raise mission_error(409, "MISSION_NOT_AWAITING_ACCEPTANCE", "The mission must be awaiting acceptance")
    dossier = await latest_dossier(db, mission.project_id)
    snapshot = await delivery_snapshot(db, mission, dossier)
    pending = await db.scalar(select(ApprovalRequest).where(ApprovalRequest.target_type == "mission_dossier",
        ApprovalRequest.target_id == mission.project_id, ApprovalRequest.status == "pending"))
    if pending:
        raise mission_error(409, "ACCEPTANCE_ALREADY_REQUESTED", "A pending acceptance request already exists",
                            approval_request_id=str(pending.id))
    now = datetime.now(timezone.utc)
    binding = await db.scalar(select(PolicyBinding).join(PolicyVersion).where(
        PolicyBinding.target_type == "mission_dossier", PolicyBinding.is_active.is_(True),
        PolicyBinding.target_id.is_(None), PolicyVersion.status == "active",
        (PolicyBinding.effective_from.is_(None) | (PolicyBinding.effective_from <= now)),
        (PolicyBinding.effective_until.is_(None) | (PolicyBinding.effective_until > now)))
        .order_by(PolicyBinding.priority.desc()).limit(1))
    if binding is None:
        raise mission_error(409, "ACCEPTANCE_POLICY_MISSING", "No active mission acceptance policy")
    version = await db.get(PolicyVersion, binding.policy_version_id)
    if not version.rules_snapshot.get("human_only") or not version.rules_snapshot.get("deny_self_approval"):
        raise mission_error(409, "ACCEPTANCE_POLICY_INVALID", "Acceptance requires human separation of duties")
    digest = canonical_hash({"snapshot": snapshot, "version": version.id})
    evaluation = await db.scalar(select(PolicyEvaluation).where(PolicyEvaluation.policy_version_id == version.id,
                                                               PolicyEvaluation.input_hash == digest))
    if evaluation is None:
        evaluation = PolicyEvaluation(policy_binding_id=binding.id, policy_version_id=version.id,
            target_type="mission_dossier", target_id=mission.project_id, target_revision_id=dossier.artifact_version_id,
            target_hash=dossier.file_sha256, input_hash=digest, outcome="pass",
            result={"delivery_snapshot": snapshot, "rules": version.rules_snapshot}, evaluator_version="mission-acceptance-v1",
            evaluated_at=now)
        db.add(evaluation)
        await db.flush()
    request = ApprovalRequest(target_type="mission_dossier", target_id=mission.project_id,
        target_revision_id=dossier.artifact_version_id, target_hash=dossier.file_sha256, approval_type="mission_acceptance",
        policy_evaluation_id=evaluation.id, requested_by_type=principal.principal_type,
        requested_by_id=principal.principal_id, requested_by_name=principal.display_name,
        expires_at=now + timedelta(hours=int(version.rules_snapshot.get("expires_hours", 168))))
    db.add(request)
    await db.flush()
    db.add(AuditEvent(entity_type="mission", entity_id=mission.project_id, event_type="mission_acceptance_requested",
        actor=principal.display_name, payload={"approval_request_id": str(request.id), "delivery_snapshot": snapshot}))
    return request


async def decide_acceptance(db, principal, request, decision, comments, idempotency_key):
    require_human(principal)
    if decision not in ("approved", "rejected", "changes_requested"):
        raise mission_error(422, "ACCEPTANCE_DECISION_INVALID", "Accept, reject or request changes")
    if not (comments or "").strip():
        raise mission_error(422, "REASON_REQUIRED", "An acceptance decision requires a reason")
    request = await db.scalar(select(ApprovalRequest).where(ApprovalRequest.id == request.id)
        .with_for_update().execution_options(populate_existing=True))
    # Authenticate before any replay; bind identity, payload, and target, even without a key.
    existing = await db.scalar(select(ApprovalDecisionRecord).where(
        ApprovalDecisionRecord.approval_request_id == request.id))
    if idempotency_key:
        keyed = await db.scalar(select(ApprovalDecisionRecord).where(
            ApprovalDecisionRecord.idempotency_key == idempotency_key))
        if keyed and (not existing or keyed.id != existing.id):
            raise mission_error(409, "IDEMPOTENCY_KEY_REUSED", "The key belongs to another decision")
    if existing:
        if (existing.decided_by_type, existing.decided_by_id, existing.decision, existing.comments
            ) != (principal.principal_type, principal.principal_id, decision, comments):
            raise mission_error(409, "APPROVAL_ALREADY_DECIDED", "The recorded decision differs from this request")
        return existing
    if request.status != "pending":
        raise mission_error(409, "APPROVAL_NOT_PENDING", "The request is no longer pending")
    if request.expires_at and request.expires_at <= datetime.now(timezone.utc):
        await _expire(db, request)
    if (request.requested_by_type, request.requested_by_id) == (principal.principal_type, principal.principal_id):
        raise mission_error(403, "SEPARATION_OF_DUTIES", "The submitter cannot decide its own delivery")
    mission = await db.scalar(select(ProjectMission).where(ProjectMission.project_id == request.target_id)
        .with_for_update().execution_options(populate_existing=True))
    if mission is None or mission.state != "awaiting_acceptance":
        raise mission_error(409, "ACCEPTANCE_STALE", "The mission is no longer awaiting acceptance")
    if decision == "approved":
        dossier = await latest_dossier(db, mission.project_id)
        evaluation = await db.get(PolicyEvaluation, request.policy_evaluation_id)
        if (dossier.artifact_version_id != request.target_revision_id or dossier.file_sha256 != request.target_hash or
            await delivery_snapshot(db, mission, dossier) != evaluation.result.get("delivery_snapshot")):
            raise mission_error(409, "ACCEPTANCE_STALE", "The delivery changed after the request")
    now = datetime.now(timezone.utc)
    project = await db.get(Project, mission.project_id)
    mission.state = "completed" if decision == "approved" else "active"
    mission.state_changed_at, mission.state_reason = now, comments
    mission.row_version += 1
    mission.acceptance_request_id = request.id
    if decision == "approved":
        project.status = "completed"
        delegations = (await db.scalars(select(AuthorityDelegation).where(
            AuthorityDelegation.project_id == mission.project_id, AuthorityDelegation.status == "active"))).all()
        for delegation in delegations:
            if set(delegation.allowed_actions) & {"mission.orchestrate", "planning.execution.manage"}:
                delegation.status, delegation.revoked_at = "revoked", now
    request.status = "decided"
    record = ApprovalDecisionRecord(approval_request_id=request.id, decision=decision,
        decided_by_type=principal.principal_type, decided_by_id=principal.principal_id,
        decided_by_name=principal.display_name, authority_source="admin", comments=comments, idempotency_key=idempotency_key)
    db.add(record)
    db.add(AuditEvent(entity_type="mission", entity_id=mission.project_id,
        event_type="mission_accepted" if decision == "approved" else f"mission_{decision}", actor=principal.display_name,
        payload={"approval_request_id": str(request.id), "target_hash": request.target_hash, "reason": comments,
                 "principal_id": str(principal.principal_id)}))
    from app.core.mission_cycle import sync_mission_routine
    await sync_mission_routine(db, project, mission, now)
    await db.flush()
    return record

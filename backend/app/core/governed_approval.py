"""Deterministic governed-approval commands shared by Planning and Governance routes."""
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ActorPrincipal, authorize_action
from app.db.models.governance import (
    ApprovalDecisionRecord, ApprovalRequest, AuditEvent, PolicyBinding,
    PolicyEvaluation, PolicyVersion,
)
from app.db.models.notification import Notification
from app.db.models.system_scope import ProductConcept, SystemBlueprint, SystemBlueprintRevision


def canonical_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _notification(event_key: str, title: str, message: str, severity: str = "info") -> Notification:
    return Notification(
        source="system", severity=severity, title=title, message=message, summary=None,
        event_key=event_key, occurred_at=datetime.now(timezone.utc),
    )


async def request_concept_approval(
    db: AsyncSession,
    principal: ActorPrincipal,
    concept: ProductConcept,
    target_hash: str,
) -> ApprovalRequest:
    await authorize_action(db, principal, "planning.concept.submit", product_id=concept.product_id)
    binding = (await db.execute(
        select(PolicyBinding).join(PolicyVersion).where(
            PolicyBinding.target_type == "product_concept",
            PolicyBinding.is_active.is_(True), PolicyVersion.status == "active",
        ).order_by(PolicyBinding.priority.desc())
    )).scalars().first()
    if binding is None:
        raise HTTPException(409, "No active concept approval policy binding")
    version = await db.get(PolicyVersion, binding.policy_version_id)
    inputs = {
        "policy_version_id": str(version.id), "target_id": str(concept.id),
        "target_revision_id": str(concept.current_revision_id), "target_hash": target_hash,
        "blueprint_valid": True,
    }
    input_hash = canonical_hash(inputs)
    evaluation = (await db.execute(select(PolicyEvaluation).where(
        PolicyEvaluation.policy_version_id == version.id,
        PolicyEvaluation.input_hash == input_hash,
    ))).scalar_one_or_none()
    if evaluation is None:
        result = {"passed": True, "requirements": [{"key": "valid_blueprint", "passed": True}], "rules": version.rules_snapshot}
        evaluation = PolicyEvaluation(
            policy_binding_id=binding.id, policy_version_id=version.id,
            target_type="product_concept", target_id=concept.id,
            target_revision_id=concept.current_revision_id, target_hash=target_hash,
            input_hash=input_hash, outcome="pass", result=result,
            evaluator_version="structured-v1", evaluated_at=datetime.now(timezone.utc),
        )
        db.add(evaluation)
        await db.flush()
    existing = (await db.execute(select(ApprovalRequest).where(
        ApprovalRequest.target_type == "product_concept",
        ApprovalRequest.target_id == concept.id,
        ApprovalRequest.target_revision_id == concept.current_revision_id,
        ApprovalRequest.approval_type == "concept_approval",
        ApprovalRequest.status == "pending",
    ))).scalar_one_or_none()
    if existing:
        return existing
    request = ApprovalRequest(
        target_type="product_concept", target_id=concept.id,
        target_revision_id=concept.current_revision_id, target_hash=target_hash,
        approval_type="concept_approval", policy_evaluation_id=evaluation.id,
        requested_by_type=principal.principal_type, requested_by_id=principal.principal_id,
        requested_by_name=principal.display_name,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=int(version.rules_snapshot.get("expires_hours", 72))),
    )
    db.add(request)
    await db.flush()
    db.add(AuditEvent(
        entity_type="approval_request", entity_id=request.id, event_type="approval_requested",
        actor=principal.display_name, payload={"principal_type": principal.principal_type, "target_hash": target_hash},
    ))
    db.add(_notification(
        f"approval:requested:{request.id}", "Concept approval requested",
        f"{principal.display_name} submitted concept {concept.id} for governed approval.",
    ))
    return request


async def approved_concept_request(
    db: AsyncSession, concept: ProductConcept, target_hash: str
) -> ApprovalRequest | None:
    return (await db.execute(
        select(ApprovalRequest).join(ApprovalDecisionRecord).where(
            ApprovalRequest.target_type == "product_concept",
            ApprovalRequest.target_id == concept.id,
            ApprovalRequest.target_revision_id == concept.current_revision_id,
            ApprovalRequest.target_hash == target_hash,
            ApprovalRequest.status == "decided",
            ApprovalDecisionRecord.decision == "approved",
        ).order_by(ApprovalRequest.created_at.desc())
    )).scalars().first()


async def decide_concept_approval(
    db: AsyncSession,
    principal: ActorPrincipal,
    request: ApprovalRequest,
    decision: str,
    comments: str | None,
    idempotency_key: str | None,
) -> ApprovalDecisionRecord:
    if idempotency_key:
        existing = (await db.execute(select(ApprovalDecisionRecord).where(
            ApprovalDecisionRecord.idempotency_key == idempotency_key
        ))).scalar_one_or_none()
        if existing:
            return existing
    if request.status != "pending":
        existing = (await db.execute(select(ApprovalDecisionRecord).where(
            ApprovalDecisionRecord.approval_request_id == request.id
        ))).scalar_one_or_none()
        if existing:
            return existing
        raise HTTPException(409, "Approval request is no longer pending")
    if request.expires_at and request.expires_at <= datetime.now(timezone.utc):
        request.status = "expired"
        raise HTTPException(409, "Approval request expired")
    concept = await db.get(ProductConcept, request.target_id)
    if concept is None:
        raise HTTPException(404, "Product concept not found")
    authority_source, delegation = await authorize_action(
        db, principal, "governance.approval.decide", product_id=concept.product_id
    )
    evaluation = await db.get(PolicyEvaluation, request.policy_evaluation_id)
    version = await db.get(PolicyVersion, evaluation.policy_version_id)
    deny_self = bool(version.rules_snapshot.get("deny_self_approval", True))
    if deny_self and principal.principal_id == request.requested_by_id and principal.principal_type == request.requested_by_type:
        raise HTTPException(403, "separation_of_duties_violation")
    if concept.current_revision_id != request.target_revision_id:
        request.status = "stale"
        raise HTTPException(409, "Approval request is stale because the concept revision changed")
    blueprint = (await db.execute(select(SystemBlueprint).where(
        SystemBlueprint.product_id == concept.product_id
    ))).scalar_one()
    blueprint_revision = await db.get(SystemBlueprintRevision, blueprint.current_revision_id)
    record = ApprovalDecisionRecord(
        approval_request_id=request.id, decision=decision,
        decided_by_type=principal.principal_type, decided_by_id=principal.principal_id,
        decided_by_name=principal.display_name, authority_source=authority_source,
        delegation_id=delegation.id if delegation else None, comments=comments,
        idempotency_key=idempotency_key,
    )
    db.add(record)
    request.status = "decided"
    if decision == "approved":
        concept.status = "approved"
        blueprint_revision.status = "approved"
    elif decision == "changes_requested":
        concept.status = "rework"
        blueprint_revision.status = "draft"
    elif decision == "rejected":
        concept.status = "rejected"
    await db.flush()
    db.add(AuditEvent(
        entity_type="approval_request", entity_id=request.id,
        event_type=f"approval_{decision}", actor=principal.display_name,
        payload={
            "principal_type": principal.principal_type, "principal_id": str(principal.principal_id),
            "authority_source": authority_source, "delegation_id": str(delegation.id) if delegation else None,
            "target_hash": request.target_hash,
        },
    ))
    return record

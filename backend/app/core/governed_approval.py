"""Deterministic governed-approval commands shared by Planning and Governance routes."""
import hashlib
import json
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ActorPrincipal, authorize_action
from app.db.models.demand import AgentDemand
from app.db.models.governance import (
    ApprovalDecisionRecord, ApprovalRequest, AuditEvent, PolicyBinding,
    PolicyEvaluation, PolicyVersion,
)
from app.db.models.notification import Notification
from app.db.models.system_scope import ProductConcept, SystemBlueprint, SystemBlueprintRevision
from app.db.models.task import ProjectTask, TaskExecution


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


# ---------------------------------------------------------------------------
# ProjectTask completion approval -- layered task-execution governance,
# Fase 3 (plan: resilient-twirling-blossom). Mirrors the concept-approval
# shape above (request/decide, policy-evaluated, 3-way decision) but kept
# as its own pair of functions rather than a shared base: `decide_concept_
# approval` is already in production for real concept approvals, and
# extracting a generic helper out of it risks that working path for
# uncertain benefit. The two are intentionally parallel, not shared code.
# ---------------------------------------------------------------------------


async def request_task_approval(
    db: AsyncSession, task: ProjectTask, execution: TaskExecution
) -> ApprovalRequest | None:
    """Called by core/task_evidence.py once an execution is auto-verified.
    Deliberately a silent no-op when no active `project_task` policy
    binding exists -- Fase 1/2's verified-execution-can-go-straight-to-done
    behavior keeps working exactly as shipped until someone (Marcelo/Athos)
    deliberately activates this layer via the generic Policy/PolicyVersion/
    PolicyBinding CRUD (governance.py). No `authorize_action` call here:
    this records that verified work exists and is ready for review, it
    isn't the system acting with anyone's authority.

    `requested_by` is the agent that actually executed the task (resolved
    via the AgentDemand this execution is linked from) -- not a human. That
    makes `deny_self_approval` in decide_task_approval do real work: the
    agent whose output this is can never be the one who approves it, which
    is the "área revisa antes de aprovar" requirement enforced structurally
    instead of by convention.

    Binding scope: `PolicyBinding.target_id` (unused by any existing
    binding -- the product_concept seed leaves it NULL) is interpreted here
    as "scope to this Project" for target_type="project_task" -- a project
    can turn this layer on for just its own tasks without making every
    other project's tasks require approval too. A project-scoped binding
    wins over a global one (target_id IS NULL) when both are active for
    the same task's project."""
    from app.api.routes.task import _resolve_task_project_id
    project_id = await _resolve_task_project_id(db, task)

    binding = (await db.execute(
        select(PolicyBinding).join(PolicyVersion).where(
            PolicyBinding.target_type == "project_task",
            PolicyBinding.is_active.is_(True), PolicyVersion.status == "active",
            or_(PolicyBinding.target_id == project_id, PolicyBinding.target_id.is_(None)),
        ).order_by(PolicyBinding.target_id.isnot(None).desc(), PolicyBinding.priority.desc())
    )).scalars().first()
    if binding is None:
        return None

    demand = (await db.execute(
        select(AgentDemand).where(AgentDemand.task_execution_id == execution.id)
    )).scalar_one_or_none()
    if demand is None or demand.target_agent_id is None:
        # No dispatch record to attribute this execution to -- can't
        # establish who "requested" review, so nothing to open yet.
        return None

    version = await db.get(PolicyVersion, binding.policy_version_id)
    target_hash = canonical_hash({
        "task_id": str(task.id), "execution_id": str(execution.id),
        "evidence_ref": execution.evidence_ref,
    })
    inputs = {
        "policy_version_id": str(version.id), "target_id": str(task.id),
        "target_revision_id": str(execution.id), "target_hash": target_hash,
    }
    input_hash = canonical_hash(inputs)
    evaluation = (await db.execute(select(PolicyEvaluation).where(
        PolicyEvaluation.policy_version_id == version.id,
        PolicyEvaluation.input_hash == input_hash,
    ))).scalar_one_or_none()
    if evaluation is None:
        result = {"passed": True, "requirements": [{"key": "evidence_verified", "passed": True}], "rules": version.rules_snapshot}
        evaluation = PolicyEvaluation(
            policy_binding_id=binding.id, policy_version_id=version.id,
            target_type="project_task", target_id=task.id,
            target_revision_id=execution.id, target_hash=target_hash,
            input_hash=input_hash, outcome="pass", result=result,
            evaluator_version="structured-v1", evaluated_at=datetime.now(timezone.utc),
        )
        db.add(evaluation)
        await db.flush()

    existing = (await db.execute(select(ApprovalRequest).where(
        ApprovalRequest.target_type == "project_task",
        ApprovalRequest.target_id == task.id,
        ApprovalRequest.target_revision_id == execution.id,
        ApprovalRequest.approval_type == "task_completion_approval",
        ApprovalRequest.status == "pending",
    ))).scalar_one_or_none()
    if existing:
        return existing

    request = ApprovalRequest(
        target_type="project_task", target_id=task.id,
        target_revision_id=execution.id, target_hash=target_hash,
        approval_type="task_completion_approval", policy_evaluation_id=evaluation.id,
        requested_by_type="agent", requested_by_id=demand.target_agent_id,
        requested_by_name=demand.from_agent or "agent",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=int(version.rules_snapshot.get("expires_hours", 72))),
    )
    db.add(request)
    await db.flush()
    db.add(AuditEvent(
        entity_type="approval_request", entity_id=request.id, event_type="approval_requested",
        actor="system", payload={"task_id": str(task.id), "execution_id": str(execution.id)},
    ))
    db.add(_notification(
        f"approval:requested:{request.id}", "Task completion approval requested",
        f"Task #{task.number}'s execution is verified and awaiting review.",
    ))
    return request


async def decide_task_approval(
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

    task = await db.get(ProjectTask, request.target_id)
    if task is None:
        raise HTTPException(404, "Task not found")
    execution = await db.get(TaskExecution, request.target_revision_id)
    if execution is None:
        raise HTTPException(404, "Task execution not found")

    # Local import: api/routes/task.py already imports demand.py the same
    # way for the same reason (route->route cycle at module load time).
    from app.api.routes.task import _resolve_task_project_id
    project_id = await _resolve_task_project_id(db, task)
    authority_source, delegation = await authorize_action(
        db, principal, "governance.approval.decide", project_id=project_id
    )

    evaluation = await db.get(PolicyEvaluation, request.policy_evaluation_id)
    version = await db.get(PolicyVersion, evaluation.policy_version_id)
    deny_self = bool(version.rules_snapshot.get("deny_self_approval", True))
    if deny_self and principal.principal_id == request.requested_by_id and principal.principal_type == request.requested_by_type:
        raise HTTPException(403, "separation_of_duties_violation")

    # Staleness: a newer execution attempt exists for this task since the
    # request was opened (e.g. a prior changes_requested cycle already
    # redispatched it) -- this decision no longer applies to current work.
    latest_execution_id = (await db.execute(
        select(TaskExecution.id).where(TaskExecution.task_id == task.id)
        .order_by(TaskExecution.attempt_number.desc()).limit(1)
    )).scalar_one_or_none()
    if latest_execution_id != execution.id:
        request.status = "stale"
        raise HTTPException(409, "Approval request is stale because a newer execution attempt exists")

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
        if execution.status not in ("verified", "completed"):
            raise HTTPException(409, "Cannot approve: execution evidence is not verified")
        task.status = "done"
        if task.completed_at is None:
            task.completed_at = datetime.now(timezone.utc)
        db.add(AuditEvent(
            entity_type="project_task", entity_id=task.id, event_type="task_completed",
            actor=principal.display_name, payload={"via": "governed_approval", "execution_id": str(execution.id)},
        ))
    elif decision == "changes_requested":
        task.status = "in_progress"
        # Local import, same reasoning as _resolve_task_project_id above --
        # redispatches to the same agent (target_agent_id omitted resolves
        # via the still-active TaskAssignment/ResponsibilityArea), carrying
        # the reviewer's comments as extra instruction. This is the "manda
        # corrigir" loop: a brand new AgentDemand + TaskExecution attempt,
        # not a mutation of the rejected one.
        from app.api.routes.task import _dispatch_task_by_id
        from app.api.schemas.task import TaskInboxDispatchIn
        await _dispatch_task_by_id(
            task.id,
            TaskInboxDispatchIn(
                command_text=f"Revisão pediu correções: {comments}" if comments else "Revisão pediu correções.",
            ),
            db,
        )
    elif decision == "rejected":
        task.status = "blocked"

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

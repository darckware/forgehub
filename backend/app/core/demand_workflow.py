"""Execution authorization is enforced at the runner boundary, not by UI buttons."""
import hashlib
import json
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select

from app.db.models.demand import AgentDemand, INCUBATION_DEFAULT_MATURATION_DAYS
from app.db.models.governance import AuditEvent
from app.db.models.operations import AgentQuestion


# Written by confirm_inactive. Deliberately free of "uncertain": the outcome is
# now a known terminal failure, so the normal retry rules apply again.
INACTIVE_CONFIRMED_ERROR = "Operator confirmed the previous run is inactive; correct the cause and authorize a retry."


class WorkflowBlocked(HTTPException):
    def __init__(self, detail):
        super().__init__(409, detail)


def requires_reconciliation(demand):
    return demand.dispatch_status == "failed" and bool(
        (demand.agent_run_id and not demand.dispatch_error)
        or "uncertain" in (demand.dispatch_error or "").lower())


def approval_fingerprint(demand: AgentDemand) -> str:
    content = {key: str(getattr(demand, key, None)) for key in (
        "subject", "body", "origin_type", "origin_id", "target_agent_id", "from_agent_id",
        "working_path", "project_id", "command_text", "requires_response", "channel", "channel_ref",
    )}
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def assert_execution_allowed(demand: AgentDemand) -> None:
    if demand.status == "archived" or demand.consolidated_into_id is not None:
        raise WorkflowBlocked("Archived or consolidated work cannot be executed; open its current summary")
    if demand.requires_approval and (
        demand.approval_status != "approved" or demand.approved_content_hash != approval_fingerprint(demand)
    ):
        raise WorkflowBlocked("Awaiting operator approval of the current task content")


def invalidate_changed_approval(demand: AgentDemand) -> None:
    if demand.requires_approval and demand.approval_status == "approved" and demand.approved_content_hash != approval_fingerprint(demand):
        demand.approval_status = "pending"
        demand.approved_content_hash = None


def restore_demand(demand, *, status="new"):
    if demand.consolidated_into_id:
        raise WorkflowBlocked("Restore the current summary instead of its consolidated sources")
    demand.status = status
    demand.scheduled_at = None
    demand.requires_approval = True
    demand.approval_status = "pending"
    demand.approved_content_hash = None
    if demand.origin_type == "incubation" and demand.incubation_state == "dropped":
        demand.incubation_state = "incubating"
        demand.drop_reason = None
        demand.matures_at = datetime.now(timezone.utc) + timedelta(days=INCUBATION_DEFAULT_MATURATION_DAYS)
        demand.decision_reminded_at = None


def record_transition(db, demand, action, *, actor="system", extra=None):
    """Preserve attempt identity and evidence before another cycle can overwrite them."""
    db.add(AuditEvent(entity_type="agent_demand", entity_id=demand.id,
        event_type=f"demand_{action}", actor=actor, payload={
            "run_id": demand.agent_run_id, "dispatch_status": demand.dispatch_status,
            "error": demand.dispatch_error, "lifetime_attempts": demand.dispatch_attempts,
            "retry_limit": demand.retry_limit, **(extra or {}),
        }))


async def ensure_workflow_allowed(db, demand):
    assert_execution_allowed(demand)
    question = await db.scalar(select(AgentQuestion.id).where(
        AgentQuestion.origin_demand_id == demand.id, AgentQuestion.blocking.is_(True),
        AgentQuestion.status == "pending",
    ).limit(1))
    if question:
        raise WorkflowBlocked("Awaiting the operator's answer to a blocking question")


async def decide_demand(db, demand, payload, *, actor):
    from app.core.dispatch_signal import wake_scheduled_dispatch

    if demand.consolidated_into_id:
        raise WorkflowBlocked("This record was consolidated; deliberate on its summary")
    if demand.dispatch_status in ("dispatched", "running") or (demand.agent_run_id and demand.dispatch_status is None):
        raise WorkflowBlocked("An active or reserved execution must finish before deliberation")
    if payload.expected_updated_at is not None and demand.updated_at != payload.expected_updated_at:
        raise WorkflowBlocked("This message changed; refresh it before deciding")
    if demand.status == "archived" and payload.action != "restore":
        raise WorkflowBlocked("Archived work cannot be released implicitly")
    previous = {"previous_run_id": demand.agent_run_id, "previous_dispatch_status": demand.dispatch_status,
        "previous_error": demand.dispatch_error}
    now = datetime.now(timezone.utc)
    if payload.action in ("record_investigation", "confirm_inactive"):
        # A timeout or a 404 from the runner never proves the work stopped.
        # Investigating only adds evidence; the block lifts solely when the
        # operator confirms, naming the exact run, that nothing is running.
        if not requires_reconciliation(demand):
            raise WorkflowBlocked("Only an execution with an uncertain outcome can be investigated")
        if payload.action == "confirm_inactive":
            expected = demand.agent_run_id or f"#{demand.number}"
            if (payload.confirmation or "").strip() != expected:
                raise WorkflowBlocked("Type the run identifier exactly to confirm it is inactive")
            demand.dispatch_error = INACTIVE_CONFIRMED_ERROR
            demand.dispatch_deadline_at = None
            demand.scheduled_at = None
            demand.requires_approval = True
            demand.approval_status = "pending"
            demand.approved_content_hash = None
    elif payload.action == "authorize_retry":
        if demand.dispatch_status != "failed" or requires_reconciliation(demand):
            raise WorkflowBlocked("A known terminal failure must be verified before authorizing a retry")
        if demand.origin_type != "task":
            raise WorkflowBlocked("Only an executable task can be retried")
        demand.retry_limit = max(demand.retry_limit or 3, (demand.dispatch_attempts or 0) + 3)
        demand.requires_approval = True
        demand.approval_status = "approved"
        demand.approved_content_hash = approval_fingerprint(demand)
        demand.dispatch_status = None
        demand.agent_run_id = None
        demand.dispatch_deadline_at = None
        demand.dispatch_error = None
        demand.notice_sent = False
        demand.feedback_sent_at = None
        # Authorizing a new budget does not execute. Explicit approval queues it.
        demand.scheduled_at = None
    elif payload.action == "approve":
        if demand.dispatch_status is not None:
            raise WorkflowBlocked("Reconcile or reprocess the failed execution separately before release")
        if demand.target_agent_id is None or demand.from_agent_id is None or not (demand.working_path or "").startswith("/"):
            raise HTTPException(400, "Define sender, executor and absolute working directory before approving")
        demand.origin_type = "task"
        demand.incubation_owner_id = None
        demand.incubation_state = None
        demand.matures_at = None
        demand.requires_approval = True
        demand.approval_status = "approved"
        demand.approved_content_hash = approval_fingerprint(demand)
        demand.scheduled_at = now
    elif payload.action == "reject":
        if demand.dispatch_status == "completed":
            raise WorkflowBlocked("Use the governed completion review for completed executions")
        demand.requires_approval = True
        demand.approval_status = "rejected"
        demand.approved_content_hash = None
        demand.scheduled_at = None
        # The owner receives the revision request through its normal inbox.
        demand.agent_processed_at = None
    elif payload.action == "postpone":
        if demand.origin_type != "incubation" or payload.matures_at <= now:
            raise HTTPException(400, "Only incubation can be postponed, to a future date")
        demand.matures_at = payload.matures_at
        demand.incubation_state = "incubating"
        demand.decision_reminded_at = None
    elif payload.action == "restore":
        if demand.status != "archived":
            raise WorkflowBlocked("Only archived messages can be restored")
        restore_demand(demand)
    elif payload.action == "drop":
        if demand.origin_type != "incubation":
            raise WorkflowBlocked("Only incubation can be discarded")
        demand.incubation_state = "dropped"
        demand.drop_reason = payload.reason
        demand.status = "archived"
        demand.scheduled_at = None
    elif payload.action == "archive":
        demand.status = "archived"
        demand.scheduled_at = None
    else:
        demand.requires_approval = True
        demand.approval_status = "pending"
        demand.approved_content_hash = None
    demand.decision_reason = payload.reason
    record_transition(db, demand, payload.action, actor=actor, extra={
        **previous, "reason": payload.reason, "evidence_ref": payload.evidence_ref,
        "content_hash": demand.approved_content_hash,
        "matures_at": str(payload.matures_at) if payload.matures_at else None})
    await db.commit()
    await db.refresh(demand)
    if payload.action == "approve":
        wake_scheduled_dispatch()
    return demand

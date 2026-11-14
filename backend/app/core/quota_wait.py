"""A provider quota is a capacity wait, never a verdict about the work."""


from sqlalchemy import select

from app.core.agent_availability import RESCHEDULE_MARGIN, classify_infra_failure
from app.core.agent_failover import can_wait_for_reset
from app.core.demand_workflow import (
    WorkflowBlocked, approval_fingerprint, ensure_workflow_allowed, record_transition,
)
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand

EXTERNAL_RUNTIMES = {"codex", "claude", "agy", "antigravity"}


async def enter_quota_wait(db, demand, output, reset):
    agent = await db.get(Agent, demand.target_agent_id) if demand.target_agent_id else None
    if not agent or agent.runtime_type not in EXTERNAL_RUNTIMES or classify_infra_failure(output) != "usage_limit":
        return False
    from app.api.routes.demand import _add_usage_limit_wait_notification, _format_execution_header
    from datetime import datetime, timezone
    demand.dispatch_status = "waiting_quota"
    demand.dispatch_error = None
    demand.dispatch_deadline_at = None
    demand.quota_reset_at = reset
    demand.quota_wait_fingerprint = approval_fingerprint(demand)
    demand.quota_dispatch_attempts = (demand.quota_dispatch_attempts or 0) + 1
    demand.scheduled_at = None
    demand.task_execution_at = datetime.now(timezone.utc)
    demand.dispatch_result = _format_execution_header(demand, agent.name) + output
    record_transition(db, demand, "quota_wait", actor="forgehub:usage-limit", extra={
        "result": demand.dispatch_result, "content_hash": demand.quota_wait_fingerprint,
        "target_agent_id": str(demand.target_agent_id),
        "quota_reset_at": reset.isoformat() if reset else None,
    })
    await _add_usage_limit_wait_notification(db, demand)
    await db.flush()
    return True


async def release_due_quota_waits(db, now):
    """Release safe ordinary work after an explicit reset; preserve protected runs.

    Selection and release lock the demand. Reservation revalidates dependencies,
    authorizations, capacity and the pinned identity under the admission lock.
    """
    from app.core.agent_availability import unavailable_until
    from app.core.demand_dispatch_guard import ensure_task_dispatch_admissible
    from app.core.message_triage import verified_delivery
    rows = list((await db.scalars(select(AgentDemand).where(
        AgentDemand.dispatch_status == "waiting_quota",
        AgentDemand.quota_reset_at <= now - RESCHEDULE_MARGIN,
        AgentDemand.status != "archived", AgentDemand.consolidated_into_id.is_(None),
    ).order_by(AgentDemand.quota_reset_at, AgentDemand.number).limit(200)
        .with_for_update(skip_locked=True))).all())
    for demand in rows:
        if not can_wait_for_reset(demand) or demand.quota_wait_fingerprint != approval_fingerprint(demand):
            continue
        if await unavailable_until(db, demand.target_agent_id, now) or await verified_delivery(db, demand):
            continue
        try:
            await ensure_workflow_allowed(db, demand)
            await ensure_task_dispatch_admissible(db, demand)
        except WorkflowBlocked:
            continue
        record_transition(db, demand, "quota_wait_released", actor="forgehub:usage-limit", extra={
            "result": demand.dispatch_result, "content_hash": demand.quota_wait_fingerprint,
            "target_agent_id": str(demand.target_agent_id),
        })
        demand.dispatch_status = None
        demand.agent_run_id = None
        demand.scheduled_at = now
        # Keep the count to pin this task to its original executor on later passes.
        demand.quota_reset_at = None
    if rows:
        await db.commit()


def quota_resume_blocker(demand, now):
    """UI/action contract for an explicit operator-reviewed continuation."""
    if demand.quota_reset_at is None:
        return "quota_reset_unknown"
    if demand.quota_reset_at + RESCHEDULE_MARGIN > now:
        return "quota_reset_pending"
    if demand.quota_wait_fingerprint != approval_fingerprint(demand):
        return "quota_context_changed"
    if not demand.agent_run_id:
        return "quota_run_evidence_missing"
    return None


async def is_factory_quota_continuation(db, demand):
    """Factory dispatches have no agent sender; their persisted attempt owns them."""
    if not (demand.channel == "factory" and demand.task_execution_id and demand.quota_dispatch_attempts):
        return False
    from app.db.models.task import TaskExecution
    execution = await db.get(TaskExecution, demand.task_execution_id)
    return execution is not None and execution.task_id == demand.origin_id

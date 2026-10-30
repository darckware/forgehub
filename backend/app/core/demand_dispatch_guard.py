"""Serialize reservations across API instances; the external start uses a durable run ID."""
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select

from app.core.agent_runs import AgentRunDispatchError
from app.core.demand_workflow import WorkflowBlocked, ensure_workflow_allowed, requires_reconciliation
from app.db.models.demand import AgentDemand, DISPATCH_MAX_ATTEMPTS, DISPATCH_TIMEOUT_MINUTES
from app.db.models.task import ProjectTask


async def ensure_task_dispatch_admissible(db, demand):
    """M0.6b: the task's current baseline (§4.2) and its exclusive targets
    (§4.3). Both refuse with WorkflowBlocked, so a scheduled item stays queued."""
    from app.core.dispatch_targets import assert_targets_free
    from app.core.task_baseline_guard import assert_task_baseline_current

    if demand.origin_type == "task" and demand.origin_id is not None:
        task = await db.get(ProjectTask, demand.origin_id)
        if task is not None:
            await assert_task_baseline_current(db, task)
    await assert_targets_free(db, demand)


async def reserve_dispatch(db, demand, target_agent_id, command_text):
    from app.api.routes.demand import _agents_already_running, _dispatch_slots, _ensure_demand_dependencies_satisfied
    from app.core.dispatch_targets import DISPATCH_ADMISSION_LOCK

    # One short transaction serializes only the admission decision. The
    # bridge call happens after commit and does not hold this lock.
    await db.execute(select(func.pg_advisory_xact_lock(DISPATCH_ADMISSION_LOCK)))
    await db.flush()
    current = (await db.execute(select(AgentDemand).where(AgentDemand.id == demand.id)
        .with_for_update().execution_options(populate_existing=True))).scalar_one()
    if current.origin_type == "incubation":
        raise WorkflowBlocked("Promote incubation to a task before execution")
    if current.dispatch_status in ("dispatched", "running") or (current.dispatch_status is None and current.agent_run_id):
        raise WorkflowBlocked("This message already has an active or reserved execution")
    if requires_reconciliation(current):
        raise WorkflowBlocked("Reconcile the previous run before retrying")
    if current.dispatch_status == "failed" and (current.dispatch_attempts or 0) >= (current.retry_limit or DISPATCH_MAX_ATTEMPTS):
        raise WorkflowBlocked("Attempt limit reached; investigate the failure before another execution")
    if await _dispatch_slots(db) <= 0 or target_agent_id in await _agents_already_running(db):
        raise WorkflowBlocked("Execution capacity is occupied; keep this task queued")
    current.target_agent_id = target_agent_id
    current.command_text = command_text
    await ensure_workflow_allowed(db, current)
    await ensure_task_dispatch_admissible(db, current)
    await _ensure_demand_dependencies_satisfied(db, current)
    if not Path((current.working_path or "").strip()).is_absolute():
        raise AgentRunDispatchError("An explicit absolute working directory is required")
    current.agent_run_id = str(uuid.uuid4())
    current.dispatched_at = datetime.now(timezone.utc)
    current.dispatch_deadline_at = current.dispatched_at + timedelta(minutes=DISPATCH_TIMEOUT_MINUTES)
    from app.core.demand_workflow import record_transition
    record_transition(db, current, "attempt_reserved", extra={"attempt_number": (current.dispatch_attempts or 0) + 1})
    await db.commit()
    return current.agent_run_id

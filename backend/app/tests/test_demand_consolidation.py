"""Real database regressions for contextual consolidation without dispatch."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select

from app.db.base import AsyncSessionLocal
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent
from app.db.models.notification import Notification


@pytest.fixture
async def consolidation_db(test_suite_agent):
    async with AsyncSessionLocal() as db:
        failed = AgentDemand(
            from_agent="test-suite", from_agent_id=test_suite_agent, target_agent_id=test_suite_agent,
            subject=f"Failure {uuid.uuid4()}", body="Original evidence", origin_type="task",
            dispatch_status="failed", dispatch_attempts=3, agent_run_id=str(uuid.uuid4()),
            dispatch_error="Dispatch outcome is uncertain; reconcile the known run before retrying.",
        )
        incubated = AgentDemand(
            from_agent="test-suite", from_agent_id=test_suite_agent, target_agent_id=test_suite_agent,
            subject=f"Idea {uuid.uuid4()}", body="Original proposal", origin_type="incubation",
            matures_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        db.add_all([failed, incubated])
        await db.flush()
        ids = [failed.id, incubated.id]
        try:
            yield db, failed, incubated
        finally:
            await db.rollback()
            async with AsyncSessionLocal() as cleanup:
                await cleanup.execute(delete(Notification).where(
                    Notification.event_key.in_([f"incubation-due:{i}" for i in ids])
                ))
                await cleanup.execute(delete(AgentDemand).where(AgentDemand.id.in_(ids)))
                await cleanup.execute(delete(AuditEvent).where(AuditEvent.entity_id.in_(ids)))
                await cleanup.commit()


async def test_consolidation_archives_sources_and_preserves_uncertain_run(consolidation_db, test_suite_agent):
    from app.api.schemas.demand import DemandConsolidateIn
    from app.core.demand_consolidation import consolidate_demands

    db, failed, incubated = consolidation_db
    run_id, error = failed.agent_run_id, failed.dispatch_error
    payload = DemandConsolidateIn(
        source_ids=[failed.id, incubated.id], subject="Context summary", body="Pending decision",
        owner_agent_id=test_suite_agent, context_area="Infrastructure",
    )
    summary = await consolidate_demands(db, payload, actor="test")
    assert summary.origin_type == "incubation"
    assert summary.incubation_owner_id == test_suite_agent
    assert summary.dispatch_status is None
    assert summary.scheduled_at is None
    assert summary.context_area == "Infrastructure"
    assert summary.project_id is None
    for source in (failed, incubated):
        assert source.status == "archived"
        assert source.consolidated_into_id == summary.id
        assert source.context_area == "Infrastructure"
        assert f"/demands?message={source.id}" in summary.body
    assert "reconciliação" in summary.body.lower()
    assert failed.agent_run_id == run_id
    assert failed.dispatch_error == error
    assert failed.dispatch_attempts == 3
    assert failed.body == "Original evidence"
    again = await consolidate_demands(db, payload, actor="test")
    assert again.id == summary.id
    events = (await db.execute(select(AuditEvent).where(
        AuditEvent.entity_id == summary.id, AuditEvent.event_type == "demand_consolidated",
    ))).scalars().all()
    assert len(events) == 1


@pytest.mark.parametrize("invalid", ["running", "archived", "different_area"])
async def test_consolidation_rejects_invalid_sources_without_partial_archive(
    consolidation_db, test_suite_agent, invalid,
):
    from app.api.schemas.demand import DemandConsolidateIn
    from app.core.demand_consolidation import consolidate_demands

    db, failed, incubated = consolidation_db
    if invalid == "running":
        incubated.dispatch_status = "running"
    elif invalid == "archived":
        incubated.status = "archived"
    else:
        incubated.context_area = "Security"
    await db.flush()
    with pytest.raises(HTTPException) as exc:
        await consolidate_demands(db, DemandConsolidateIn(
            source_ids=[failed.id, incubated.id], subject="Invalid", body="Summary",
            owner_agent_id=test_suite_agent, context_area="Infrastructure",
        ), actor="test")
    assert exc.value.status_code == 409
    assert failed.status != "archived"
    assert failed.consolidated_into_id is None


async def test_archived_incubation_does_not_mature(consolidation_db):
    from app.api.routes.demand import run_incubation_maturation_pass

    db, _, incubated = consolidation_db
    incubated.status = "archived"
    await db.flush()
    await run_incubation_maturation_pass(db)
    await db.refresh(incubated)
    assert incubated.incubation_state == "incubating"


async def test_archived_failure_cannot_be_reprocessed(consolidation_db):
    from app.api.routes.demand import reprocess_demand

    db, failed, _ = consolidation_db
    failed.status = "archived"
    failed.dispatch_error = "Known failure"
    failed.agent_run_id = None
    failed.dispatch_attempts = 1
    await db.flush()
    with pytest.raises(HTTPException) as exc:
        await reprocess_demand(failed.id, db=db)
    assert exc.value.status_code == 409
    assert failed.dispatch_status == "failed"


async def test_concurrent_dispatch_cannot_start_the_same_work_twice(consolidation_db, test_suite_agent, monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock
    from app.api.routes import demand as routes

    db, failed, _ = consolidation_db
    failed.dispatch_status = None
    failed.agent_run_id = None
    failed.dispatch_error = None
    failed.dispatch_attempts = 0
    failed.working_path = "/tmp"
    await db.commit()
    demand_id = failed.id
    entered, release = asyncio.Event(), asyncio.Event()
    starts = []

    async def runner(run_id, *args):
        starts.append(run_id)
        if len(starts) == 1:
            entered.set()
            await release.wait()
        return {"run_id": run_id}

    monkeypatch.setattr(routes, "dispatch_agent_run", runner)
    monkeypatch.setattr(routes, "_send_notice", AsyncMock())
    monkeypatch.setattr(routes, "_dispatch_slots", AsyncMock(return_value=1))

    async def dispatch():
        async with AsyncSessionLocal() as session:
            item = await session.get(AgentDemand, demand_id)
            await routes._execute_dispatch(session, item, test_suite_agent, None)
            await session.commit()

    first = asyncio.create_task(dispatch())
    try:
        await asyncio.wait_for(entered.wait(), 5)
        with pytest.raises(HTTPException) as exc:
            await asyncio.wait_for(dispatch(), 5)
        assert exc.value.status_code == 409
    finally:
        release.set()
        await first
    assert len(starts) == 1


async def test_operator_retry_preserves_lifetime_attempts(consolidation_db):
    from app.api.schemas.demand import DemandDecisionIn
    from app.core.demand_workflow import decide_demand

    db, failed, _ = consolidation_db
    failed.agent_run_id = None
    failed.dispatch_error = "The agent run ended as 'failed'."
    failed.working_path = "/tmp"
    result = await decide_demand(db, failed, DemandDecisionIn(
        action="authorize_retry", reason="Runtime configuration fixed and verified", evidence_ref="docs/runtime-check.md",
    ), actor="operator")
    assert result.dispatch_attempts == 3
    assert result.retry_limit == 6
    assert result.dispatch_status is None
    assert result.approval_status == "approved"
    assert result.scheduled_at is None


async def test_operator_approval_is_invalidated_by_later_edits(consolidation_db):
    from app.api.schemas.demand import DemandDecisionIn, DemandUpdateIn
    from app.api.routes.demand import update_demand
    from app.core.demand_workflow import decide_demand

    db, _, incubated = consolidation_db
    incubated.working_path = "/tmp"
    approved = await decide_demand(db, incubated, DemandDecisionIn(action="approve"), actor="operator")
    assert approved.approval_status == "approved"
    assert approved.origin_type == "task"
    edited = await update_demand(incubated.id, DemandUpdateIn(body="Changed scope"), db=db)
    assert edited.approval_status == "pending"
    assert edited.approved_content_hash is None


async def test_dispatch_uses_context_refreshed_under_reservation(consolidation_db, test_suite_agent, monkeypatch):
    from unittest.mock import AsyncMock
    from app.api.routes import demand as routes
    from app.core.demand_dispatch_guard import reserve_dispatch

    db, failed, _ = consolidation_db
    failed.dispatch_status = None
    failed.agent_run_id = None
    failed.dispatch_error = None
    failed.dispatch_attempts = 0
    failed.working_path = "/tmp/old-context"
    await db.commit()
    demand_id = failed.id

    async def edited_reservation(*args):
        async with AsyncSessionLocal() as writer:
            latest = await writer.get(AgentDemand, demand_id)
            latest.body = "Updated execution context"
            latest.working_path = "/tmp/new-context"
            await writer.commit()
        return await reserve_dispatch(*args)

    runner = AsyncMock(side_effect=lambda run_id, *args: {"run_id": run_id})
    monkeypatch.setattr(routes, "reserve_dispatch", edited_reservation)
    monkeypatch.setattr(routes, "dispatch_agent_run", runner)
    monkeypatch.setattr(routes, "_send_notice", AsyncMock())
    monkeypatch.setattr(routes, "_dispatch_slots", AsyncMock(return_value=1))
    await routes._execute_dispatch(db, failed, test_suite_agent, None)
    assert "Updated execution context" in runner.call_args.args[2]
    assert runner.call_args.args[3] == "/tmp/new-context"


async def test_reservation_rechecks_task_type_after_concurrent_edit(consolidation_db, test_suite_agent):
    from app.core.demand_dispatch_guard import reserve_dispatch

    db, failed, _ = consolidation_db
    failed.dispatch_status = None
    failed.agent_run_id = None
    failed.dispatch_error = None
    failed.dispatch_attempts = 0
    failed.working_path = "/tmp"
    await db.commit()
    demand_id = failed.id
    async with AsyncSessionLocal() as writer:
        latest = await writer.get(AgentDemand, demand_id)
        latest.origin_type = "incubation"
        await writer.commit()
    with pytest.raises(HTTPException) as exc:
        await reserve_dispatch(db, failed, test_suite_agent, None)
    assert exc.value.status_code == 409


async def test_reconciliation_cannot_overwrite_a_newer_run(consolidation_db, monkeypatch):
    from types import SimpleNamespace
    from app.api.routes import demand as routes

    db, failed, _ = consolidation_db
    await db.commit()
    demand_id = failed.id
    newer_run = str(uuid.uuid4())

    async def poll(run_id):
        async with AsyncSessionLocal() as writer:
            latest = await writer.get(AgentDemand, demand_id)
            latest.agent_run_id = newer_run
            await writer.commit()
        return {"status": "running"}

    monkeypatch.setattr(routes, "poll_agent_run", poll)
    with pytest.raises(HTTPException) as exc:
        await routes.reconcile_message(demand_id, db=db, admin=SimpleNamespace(username="operator"))
    assert exc.value.status_code == 409


async def test_uncertain_run_keeps_its_agent_occupied(consolidation_db, test_suite_agent):
    from app.api.routes.demand import _agents_already_running

    db, _, _ = consolidation_db
    assert test_suite_agent in await _agents_already_running(db)


@pytest.fixture
async def recovery_db(consolidation_db, test_suite_agent):
    """Keep background sweeps in these regressions off operational messages."""
    from sqlalchemy import event
    from sqlalchemy.orm import with_loader_criteria

    db, failed, incubated = consolidation_db
    await db.commit()

    def scope_messages(state):
        if state.is_select:
            state.statement = state.statement.options(with_loader_criteria(
                AgentDemand, AgentDemand.target_agent_id == test_suite_agent,
                include_aliases=True,
            ))

    event.listen(db.sync_session, "do_orm_execute", scope_messages)
    try:
        yield db, failed, incubated
    finally:
        event.remove(db.sync_session, "do_orm_execute", scope_messages)


@pytest.mark.parametrize("run_status", ["completed", "failed", "running"])
async def test_completion_recovers_uncertain_runs(recovery_db, test_suite_agent, monkeypatch, run_status):
    from app.api.routes import demand as routes

    db, failed, _ = recovery_db
    run_id = failed.agent_run_id

    async def poll(requested):
        assert requested == run_id
        return {"run_id": run_id, "status": run_status, "output": "Checked security baseline.\nSTATUS: DONE",
                "error": "", "exit_code": 0 if run_status == "completed" else None}

    monkeypatch.setattr(routes, "poll_agent_run", poll)
    await routes.run_dispatch_completion_pass(db)
    await db.refresh(failed)
    assert failed.dispatch_status == run_status
    assert "uncertain" not in (failed.dispatch_error or "").lower()
    assert failed.agent_run_id == run_id
    assert failed.dispatch_attempts == 3
    assert (test_suite_agent in await routes._agents_already_running(db)) == (run_status == "running")
    if run_status == "completed":
        assert "Checked security baseline." in failed.dispatch_result
        assert failed.task_execution_at is not None


async def test_completion_preserves_unknown_or_unavailable_runs(recovery_db, test_suite_agent, monkeypatch):
    import httpx
    from app.api.routes import demand as routes

    db, failed, _ = recovery_db
    original_error = failed.dispatch_error
    request = httpx.Request("GET", "http://runner/run")

    async def poll(_):
        raise httpx.HTTPStatusError("missing", request=request, response=httpx.Response(404, request=request))

    monkeypatch.setattr(routes, "poll_agent_run", poll)
    await routes.run_dispatch_completion_pass(db)
    await db.refresh(failed)
    assert failed.dispatch_status == "failed"
    assert failed.dispatch_error == original_error
    assert test_suite_agent in await routes._agents_already_running(db)


async def test_completion_does_not_finalize_a_replaced_run(recovery_db, monkeypatch):
    from app.api.routes import demand as routes

    db, failed, _ = recovery_db
    await db.commit()
    demand_id = failed.id
    newer_run = str(uuid.uuid4())

    async def poll(_):
        async with AsyncSessionLocal() as writer:
            latest = await writer.get(AgentDemand, demand_id)
            latest.agent_run_id = newer_run
            latest.dispatch_status = "running"
            latest.dispatch_error = None
            await writer.commit()
        return {"status": "completed", "output": "Old result\nSTATUS: DONE"}

    monkeypatch.setattr(routes, "poll_agent_run", poll)
    await routes.run_dispatch_completion_pass(db)
    await db.refresh(failed)
    assert failed.agent_run_id == newer_run
    assert failed.dispatch_status == "running"
    assert failed.dispatch_result is None


async def test_recovered_capacity_dispatches_a_self_addressed_task(recovery_db, test_suite_agent, monkeypatch):
    from app.api.routes import demand as routes

    db, failed, queued = recovery_db
    queued.origin_type = "task"
    queued.working_path = "/tmp"
    queued.scheduled_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    queued.notice_sent = True
    await db.commit()
    queued_id = queued.id

    async def poll(run_id):
        assert run_id == failed.agent_run_id
        return {"status": "completed", "output": "Previous work finished\nSTATUS: DONE"}

    async def start(run_id, agent, prompt, project_path):
        assert agent.id == test_suite_agent
        assert project_path == "/tmp"
        assert "Original proposal" in prompt
        return {"run_id": run_id, "status": "running"}

    monkeypatch.setattr(routes, "poll_agent_run", poll)
    monkeypatch.setattr(routes, "dispatch_agent_run", start)
    await routes.run_dispatch_completion_pass(db)
    await routes.run_scheduled_dispatch_pass(db)
    queued = await db.get(AgentDemand, queued_id)
    assert queued.dispatch_status == "dispatched"
    assert queued.agent_run_id is not None
    assert queued.dispatch_attempts == 1
    assert queued.from_agent_id == queued.target_agent_id == test_suite_agent


async def test_acknowledged_return_is_archived_without_archiving_pending_task(recovery_db, monkeypatch):
    from app.api.routes import demand as routes

    db, task, reply = recovery_db
    task.dispatch_status = None
    task.agent_run_id = None
    task.dispatch_error = None
    reply.origin_type = "task"
    reply.reply_to_id = task.id
    reply.dispatch_status = "completed"
    await db.commit()
    monkeypatch.setattr(routes.settings, "CHAT_BRIDGE_TOKEN", "test-recovery-token")
    received = await routes.list_pending_for_agent("test-suite", "test-recovery-token", db)
    assert {item.id for item in received} == {task.id, reply.id}
    await db.refresh(task)
    await db.refresh(reply)
    assert task.status != "archived"
    assert task.agent_processed_at is not None
    assert reply.status == "archived"
    assert reply.agent_processed_at is not None
    event = await db.scalar(select(AuditEvent).where(
        AuditEvent.entity_id == reply.id, AuditEvent.event_type == "demand_archive",
    ))
    assert event is not None
    assert event.payload["reason"] == "Completed return acknowledged; no execution remains pending."


async def test_inactive_confirmation_preserves_archived_consolidated_evidence(recovery_db):
    from app.api.schemas.demand import DemandDecisionIn
    from app.core.demand_workflow import decide_demand

    db, failed, summary = recovery_db
    failed.status = "archived"
    failed.consolidated_into_id = summary.id
    await db.commit()
    run_id = failed.agent_run_id
    await decide_demand(db, failed, DemandDecisionIn(
        action="confirm_inactive", confirmation=run_id, reason="No matching process exists on the runner host.",
        evidence_ref="host-process-inventory.json",
    ), actor="operator")
    assert failed.status == "archived"
    assert failed.consolidated_into_id == summary.id
    assert failed.agent_run_id == run_id
    assert failed.dispatch_status == "failed"
    assert failed.scheduled_at is None
    assert failed.dispatch_attempts == 3
    from app.api.routes.demand import _agents_already_running
    assert failed.target_agent_id not in await _agents_already_running(db)


@pytest.mark.parametrize("runner_state", ["completed", "failed"])
async def test_historical_reconciliation_does_not_create_new_communication(recovery_db, monkeypatch, runner_state):
    from app.api.routes import demand as routes

    db, failed, summary = recovery_db
    failed.status = "archived"
    failed.consolidated_into_id = summary.id
    failed.requires_response = True
    failed.channel = "assistant"
    await db.commit()

    async def poll(_):
        return {"status": runner_state, "output": "Historical result\nSTATUS: DONE"}

    monkeypatch.setattr(routes, "poll_agent_run", poll)
    await routes.run_dispatch_completion_pass(db)
    await db.refresh(failed)
    assert failed.dispatch_status == runner_state
    assert failed.status == "archived"
    assert "Historical result" in failed.dispatch_result
    assert await db.scalar(select(AgentDemand.id).where(AgentDemand.reply_to_id == failed.id)) is None
    assert await db.scalar(select(Notification.id).where(Notification.event_key.like(f"%{failed.id}%"))) is None


@pytest.mark.parametrize("runner_state", ["running", "completed"])
async def test_frontend_poll_does_not_overwrite_a_newer_run(recovery_db, monkeypatch, runner_state):
    from app.api.routes import demand as routes

    db, failed, _ = recovery_db
    failed.dispatch_status = "running"
    failed.dispatch_error = None
    await db.commit()
    demand_id = failed.id
    newer_run = str(uuid.uuid4())

    async def poll(_):
        async with AsyncSessionLocal() as writer:
            latest = await writer.get(AgentDemand, demand_id)
            latest.agent_run_id = newer_run
            latest.dispatch_status = "dispatched"
            await writer.commit()
        return {"status": runner_state, "output": "Old result\nSTATUS: DONE"}

    monkeypatch.setattr(routes, "poll_agent_run", poll)
    result = await routes.get_dispatch_status(demand_id, db=db)
    await db.refresh(failed)
    assert failed.agent_run_id == newer_run
    assert failed.dispatch_status == "dispatched"
    assert failed.dispatch_result is None
    assert result.agent_run_id == newer_run


async def test_dependent_task_waits_for_predecessor_acceptance_then_dispatches(recovery_db, monkeypatch):
    from app.api.routes import demand as routes
    from app.db.models.task import ProjectTask, TaskDependency

    db, first, second = recovery_db
    predecessor = ProjectTask(title="Dependency predecessor")
    dependent = ProjectTask(title="Dependency successor")
    db.add_all([predecessor, dependent])
    await db.flush()
    dependency = TaskDependency(task_id=dependent.id, depends_on_task_id=predecessor.id)
    db.add(dependency)
    for message, task in ((first, predecessor), (second, dependent)):
        message.origin_type = "task"
        message.origin_id = task.id
        message.dispatch_status = None
        message.agent_run_id = None
        message.dispatch_error = None
        message.working_path = "/tmp"
        message.notice_sent = True
        message.scheduled_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    # The older dependent must not overtake its prerequisite.
    second.scheduled_at -= timedelta(minutes=1)
    await db.commit()
    task_ids = [predecessor.id, dependent.id]

    async def start(run_id, *_):
        return {"run_id": run_id, "status": "running"}

    async def poll(_):
        return {"status": "completed", "output": "Work reported\nSTATUS: DONE"}

    monkeypatch.setattr(routes, "dispatch_agent_run", start)
    monkeypatch.setattr(routes, "poll_agent_run", poll)
    try:
        await routes.run_scheduled_dispatch_pass(db)
        await db.refresh(first)
        await db.refresh(second)
        assert first.dispatch_status == "dispatched"
        assert second.dispatch_status is None
        assert second.dispatch_attempts == 0
        await routes.run_dispatch_completion_pass(db)
        await routes.run_scheduled_dispatch_pass(db)
        await db.refresh(second)
        # A finished process alone does not accept its deliverable.
        assert second.dispatch_status is None
        predecessor.status = "done"
        await db.commit()
        await routes.run_scheduled_dispatch_pass(db)
        await db.refresh(second)
        assert second.dispatch_status == "dispatched"
        assert second.dispatch_attempts == 1
    finally:
        await db.rollback()
        await db.execute(delete(TaskDependency).where(TaskDependency.task_id.in_(task_ids)))
        await db.execute(delete(ProjectTask).where(ProjectTask.id.in_(task_ids)))
        await db.commit()


@pytest.mark.parametrize("outcome", ["completed", "failed"])
async def test_feedback_rechecks_archive_after_another_session_updates_it(recovery_db, outcome):
    from app.core.feedback import deliver_feedback

    db, failed, _ = recovery_db
    failed.dispatch_status = outcome
    failed.dispatch_error = None
    failed.channel = "assistant"
    await db.commit()
    demand_id = failed.id
    async with AsyncSessionLocal() as writer:
        archived = await writer.get(AgentDemand, demand_id)
        archived.status = "archived"
        await writer.commit()
    assert failed.status != "archived"
    assert not await deliver_feedback(db, failed)
    assert failed.status == "archived"
    assert await db.scalar(select(AgentDemand.id).where(AgentDemand.reply_to_id == demand_id)) is None
    assert await db.scalar(select(Notification.id).where(Notification.event_key.like(f"%{demand_id}%"))) is None

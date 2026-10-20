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

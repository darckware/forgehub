"""Real database regressions for contextual consolidation without dispatch."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.db.base import AsyncSessionLocal
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent


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
        yield db, failed, incubated
        await db.rollback()


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

"""A failed attempt hands its context to one diagnostic task before archive."""
import uuid

import pytest_asyncio
from sqlalchemy import delete, select

from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand


@pytest_asyncio.fixture
async def world():
    async with AsyncSessionLocal() as db:
        owner = Agent(name=f"Check owner {uuid.uuid4().hex[:8]}", agent_type="coordinator", runtime_type="hermes", profile_slug="test-check-owner")
        db.add(owner)
        await db.flush()
        original = AgentDemand(from_agent="requester", from_agent_id=owner.id, target_agent_id=owner.id,
            subject="Review delivery", body="Original acceptance criteria", command_text="Check tests",
            origin_type="task", status="read", working_path="/tmp/project", context_area="Operations",
            dispatch_status="failed", dispatch_error="The agent run ended as 'failed'.",
            agent_run_id=str(uuid.uuid4()), dispatch_result="Partial evidence", dispatch_attempts=1)
        db.add(original)
        await db.commit()
        original_id, owner_id = original.id, owner.id
    yield original_id
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AgentDemand).where(AgentDemand.target_agent_id == owner_id, AgentDemand.id != original_id))
        await db.execute(delete(AgentDemand).where(AgentDemand.id == original_id))
        await db.execute(delete(Agent).where(Agent.id == owner_id))
        await db.commit()


async def test_failure_creates_one_check_with_context_then_archives(world):
    from app.core.demand_failure_check import ensure_failure_check
    async with AsyncSessionLocal() as db:
        check = await ensure_failure_check(db, world)
        await db.commit()
        assert check.failure_check_source_id == world
        assert check.scheduled_at is not None
        assert check.working_path == "/tmp/project"
        assert check.dispatch_status is None
        assert check.origin_id is None
        for content in ("Original acceptance criteria", "Check tests", "Partial evidence", "The agent run ended as 'failed'."):
            assert content in check.body
        source = await db.get(AgentDemand, world)
        assert source.status == "archived"
        assert source.agent_run_id in check.body
        assert source.dispatch_result == "Partial evidence"
        first_id = check.id
        again = await ensure_failure_check(db, world)
        assert again.id == first_id
        await db.commit()
    async with AsyncSessionLocal() as db:
        assert len((await db.scalars(select(AgentDemand).where(AgentDemand.failure_check_source_id == world))).all()) == 1


async def test_check_and_archive_rollback_together(world):
    from app.core.demand_failure_check import ensure_failure_check
    async with AsyncSessionLocal() as db:
        await ensure_failure_check(db, world)
        await db.rollback()
    async with AsyncSessionLocal() as db:
        assert (await db.get(AgentDemand, world)).status == "read"
        assert await db.scalar(select(AgentDemand.id).where(AgentDemand.failure_check_source_id == world)) is None


async def test_unknown_outcome_is_not_archived_or_retried(world):
    from app.core.demand_failure_check import ensure_failure_check
    async with AsyncSessionLocal() as db:
        source = await db.get(AgentDemand, world)
        source.dispatch_error = "Dispatch outcome is uncertain; reconcile the known run before retrying."
        await db.flush()
        assert await ensure_failure_check(db, world) is None
        assert source.status == "read"
        assert source.agent_run_id


async def test_failed_check_does_not_spawn_another_check(world):
    from app.core.demand_failure_check import ensure_failure_check
    async with AsyncSessionLocal() as db:
        check = await ensure_failure_check(db, world)
        check.dispatch_status = "failed"
        check.dispatch_error = "The agent reported STATUS: BLOCKED; the work is not finished."
        await db.flush()
        assert await ensure_failure_check(db, check.id) is None
        assert check.status != "archived"
        await db.rollback()


async def test_existing_approval_gate_is_not_bypassed(world):
    from app.core.demand_failure_check import ensure_failure_check
    async with AsyncSessionLocal() as db:
        source = await db.get(AgentDemand, world)
        source.requires_approval = True
        source.approval_status = "approved"
        source.approved_content_hash = "old-content-only"
        await db.flush()
        check = await ensure_failure_check(db, world)
        assert check.requires_approval is True
        assert check.approval_status == "pending"
        assert check.approved_content_hash is None
        await db.rollback()


async def test_quota_check_is_scheduled_after_provider_reset(world):
    from datetime import datetime, timezone
    from app.core.demand_failure_check import ensure_failure_check
    async with AsyncSessionLocal() as db:
        source = await db.get(AgentDemand, world)
        source.dispatch_result = "You've hit your 5-hour limit · resets 1:30pm (America/Sao_Paulo)"
        source.task_execution_at = datetime(2026, 10, 29, 14, 0, tzinfo=timezone.utc)
        owner = await db.get(Agent, source.target_agent_id)
        owner.runtime_type = "claude"
        await db.flush()
        check = await ensure_failure_check(db, world)
        assert check.scheduled_at >= datetime(2026, 10, 29, 16, 35, tzinfo=timezone.utc)
        assert check.target_agent_id == source.target_agent_id
        assert "2026-10-29T13:30:00-03:00" in check.body
        await db.rollback()


async def test_quota_without_reset_goes_to_requester_for_diagnosis(world):
    from app.core.demand_failure_check import ensure_failure_check
    async with AsyncSessionLocal() as db:
        source = await db.get(AgentDemand, world)
        source.dispatch_result = "Usage limit exceeded."
        await db.flush()
        check = await ensure_failure_check(db, world)
        assert check.target_agent_id == source.from_agent_id
        assert "Não invente horários" in check.body
        await db.rollback()


async def test_check_cannot_bypass_original_blocking_question(world):
    import pytest
    from datetime import datetime, timezone
    from app.core.demand_failure_check import ensure_failure_check
    from app.core.demand_workflow import ensure_workflow_allowed, WorkflowBlocked
    from app.db.models.operations import AgentQuestion
    async with AsyncSessionLocal() as db:
        source = await db.get(AgentDemand, world)
        question = AgentQuestion(agent_id=source.from_agent_id, question="Authorize this scope?", blocking=True,
            origin_demand_id=world, notify_after=datetime.now(timezone.utc))
        db.add(question)
        await db.flush()
        check = await ensure_failure_check(db, world)
        with pytest.raises(WorkflowBlocked, match="blocking question"):
            await ensure_workflow_allowed(db, check)
        await db.rollback()


async def test_pending_endpoint_holds_check_until_approval(world):
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    from app.core.config import settings
    from app.core.demand_failure_check import ensure_failure_check
    from app.core.demand_workflow import approval_fingerprint
    async with AsyncSessionLocal() as db:
        source = await db.get(AgentDemand, world)
        source.requires_approval = True
        source.approval_status = "approved"
        source.approved_content_hash = approval_fingerprint(source)
        await db.flush()
        check = await ensure_failure_check(db, world)
        check_id = check.id
        await db.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/demands/pending", params={"agent": "test-check-owner"}, headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN})
        assert response.status_code == 200, response.text
        assert response.json() == []
        async with AsyncSessionLocal() as db:
            check = await db.get(AgentDemand, check_id)
            assert check.agent_processed_at is None
            check.approval_status = "approved"
            check.approved_content_hash = approval_fingerprint(check)
            await db.commit()
        response = await client.get("/api/v1/demands/pending", params={"agent": "test-check-owner"}, headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN})
        assert response.status_code == 200, response.text
        assert [item["id"] for item in response.json()] == [str(check_id)]


async def test_uncertain_failures_do_not_starve_known_failure(world):
    from datetime import datetime, timezone
    from app.core.demand_failure_check import run_failure_check_pass
    async with AsyncSessionLocal() as db:
        source = await db.get(AgentDemand, world)
        for _ in range(50):
            db.add(AgentDemand(from_agent="tester", from_agent_id=source.from_agent_id,
                target_agent_id=source.target_agent_id, subject="Unknown earlier run", body="Inspect only",
                origin_type="task", dispatch_status="failed", agent_run_id=str(uuid.uuid4()),
                dispatch_error="Outcome uncertain", created_at=datetime(2000, 1, 1, tzinfo=timezone.utc)))
        await db.commit()
        await run_failure_check_pass(db)
        assert await db.scalar(select(AgentDemand.id).where(AgentDemand.failure_check_source_id == world)) is not None


async def test_concurrent_finalizers_create_only_one_check(world):
    import asyncio
    from app.core.demand_failure_check import ensure_failure_check

    async def finalize():
        async with AsyncSessionLocal() as db:
            check = await ensure_failure_check(db, world)
            check_id = check.id
            await db.commit()
            return check_id

    first, second = await asyncio.gather(finalize(), finalize())
    assert first == second


async def test_failed_run_finalizer_archives_after_linked_check(world):
    from app.api.routes.demand import _finalize_dispatch
    async with AsyncSessionLocal() as db:
        source = await db.get(AgentDemand, world)
        source.dispatch_status = "dispatched"
        run_id = source.agent_run_id
        await db.commit()
        await _finalize_dispatch(db, world, {"status": "failed", "error": "Actual CLI error"}, expected_run_id=run_id)
        await db.commit()
        source = await db.get(AgentDemand, world)
        assert source.status == "archived"
        check = await db.scalar(select(AgentDemand).where(AgentDemand.failure_check_source_id == world))
        assert "Actual CLI error" in check.body
        await _finalize_dispatch(db, world, {"status": "failed", "error": "Actual CLI error"}, expected_run_id=run_id)
        await db.commit()
        assert len((await db.scalars(select(AgentDemand.id).where(AgentDemand.failure_check_source_id == world))).all()) == 1


async def test_linked_evidence_cannot_be_deleted_via_api(world, auth_headers):
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    from app.core.demand_failure_check import ensure_failure_check
    async with AsyncSessionLocal() as db:
        check = await ensure_failure_check(db, world)
        check_id = check.id
        await db.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=auth_headers) as client:
        for item_id in (world, check_id):
            response = await client.delete(f"/api/v1/demands/{item_id}")
            assert response.status_code == 409, response.text
            assert "source evidence" in response.text


async def test_approving_a_check_preserves_future_reset_schedule(world):
    from datetime import datetime, timedelta, timezone
    from app.api.schemas.demand import DemandDecisionIn
    from app.core.demand_failure_check import ensure_failure_check
    from app.core.demand_workflow import decide_demand
    async with AsyncSessionLocal() as db:
        check = await ensure_failure_check(db, world)
        scheduled = datetime.now(timezone.utc) + timedelta(days=1)
        check.scheduled_at = scheduled
        await db.flush()
        await decide_demand(db, check, DemandDecisionIn(action="approve", reason="Approve existing scheduled check"), actor="test")
        assert check.scheduled_at == scheduled
        await db.rollback()


async def test_linked_source_attachment_cannot_be_deleted(world, auth_headers):
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    from app.core.demand_failure_check import ensure_failure_check
    from app.db.models.demand import DemandAttachment
    async with AsyncSessionLocal() as db:
        attachment = DemandAttachment(demand_id=world, filename="proof.txt", path="test-check-proof.txt", size_bytes=1)
        db.add(attachment)
        await db.flush()
        attachment_id = attachment.id
        await ensure_failure_check(db, world)
        await db.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=auth_headers) as client:
        response = await client.delete(f"/api/v1/demands/{world}/attachments/{attachment_id}")
        assert response.status_code == 409, response.text

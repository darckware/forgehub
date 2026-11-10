"""The existing periodic dispatcher recovers persisted executor waits."""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete

from app.api.routes import demand as demand_routes
from app.core.demand_workflow import dispatch_intent_fingerprint
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent
from app.db.models.mission_cycle import AgentAvailability
from app.tests.test_dispatch_contingency import isolated_dispatch_queue  # noqa: F401


@pytest.fixture
async def recovery_world(isolated_dispatch_queue):  # noqa: F811 -- imported pytest fixture
    suffix = uuid.uuid4().hex[:10]
    agent = Agent(name=f"Recovery {suffix}", agent_type="executor", runtime_type="codex",
                  profile_slug=f"recovery-{suffix}", autonomous_runs=True)
    rows = []
    async with AsyncSessionLocal() as db:
        db.add(agent)
        await db.commit()
        await db.refresh(agent)
        agent_id = agent.id
        try:
            yield db, agent, rows
        finally:
            await db.rollback()
            ids = list(rows)
            if ids:
                await db.execute(delete(AuditEvent).where(AuditEvent.entity_id.in_(ids)))
                await db.execute(delete(AgentDemand).where(AgentDemand.id.in_(ids)))
            await db.execute(delete(AgentAvailability).where(AgentAvailability.agent_id == agent_id))
            await db.execute(delete(Agent).where(Agent.id == agent_id))
            await db.commit()


async def _quota_wait(db, agent, *, reset_at, scheduled_at):
    row = AgentDemand(from_agent="operator", from_agent_id=agent.id, target_agent_id=agent.id,
        subject="Resume after quota", body="Already authorized bounded work", origin_type="task",
        status="new", working_path="/root/project/fixture", requires_approval=False,
        dispatch_status=None, agent_run_id=None, dispatch_attempts=1, scheduled_at=scheduled_at)
    db.add(row)
    await db.flush()
    db.add(AuditEvent(entity_type="agent_demand", entity_id=row.id, event_type="demand_reprocess",
        actor="forgehub:usage-limit", payload={"automatic_wait_reason": "quota",
            "automatic_resume_at": scheduled_at.isoformat(), "quota_reset_at": reset_at.isoformat(),
            "content_hash": dispatch_intent_fingerprint(row), "target_agent_id": str(row.target_agent_id)}))
    db.add(AgentAvailability(agent_id=agent.id, unavailable_until=reset_at,
        reason="test quota", recorded_by="forgehub:usage-limit"))
    await db.commit()
    await db.refresh(row)
    return row


@pytest.mark.asyncio
async def test_periodic_pass_recovers_early_quota_reset_and_dispatches_once(recovery_world, monkeypatch):
    db, agent, rows = recovery_world
    now = datetime.now(timezone.utc)
    reset_at = now - timedelta(seconds=5)
    due_at = now + timedelta(hours=2)
    row = await _quota_wait(db, agent, reset_at=reset_at, scheduled_at=due_at)
    rows.append(row.id)
    started = []

    async def slots(_db): return 2
    async def busy(_db): return set()
    async def dispatch(_db, demand, target_id, _command):
        if demand.id != rows[0]:
            return
        started.append((demand.id, target_id))
        demand.dispatch_status = "dispatched"
        demand.agent_run_id = "recovered-run"
    monkeypatch.setattr(demand_routes, "_dispatch_slots", slots)
    monkeypatch.setattr(demand_routes, "_agents_already_running", busy)
    monkeypatch.setattr(demand_routes, "_execute_dispatch", dispatch)

    await demand_routes.run_scheduled_dispatch_pass(db)
    await demand_routes.run_scheduled_dispatch_pass(db)
    assert started == [(rows[0], agent.id)]
    assert row.dispatch_status == "dispatched"


@pytest.mark.asyncio
async def test_deliberate_future_schedule_is_not_released(recovery_world):
    from app.core.message_triage import reconcile_queued_demand
    db, agent, rows = recovery_world
    now = datetime.now(timezone.utc)
    row = await _quota_wait(db, agent, reset_at=now - timedelta(seconds=5),
                            scheduled_at=now + timedelta(hours=2))
    rows.append(row.id)
    row.scheduled_at = now + timedelta(days=3)
    await db.commit()
    result = await reconcile_queued_demand(db, row, now=now)
    assert result == "unchanged"
    assert row.scheduled_at == now + timedelta(days=3)


@pytest.mark.asyncio
async def test_unassigned_quota_wait_resumes_after_compatible_assignment(recovery_world):
    from app.core.message_triage import reconcile_queued_demand
    db, limited_agent, rows = recovery_world
    now = datetime.now(timezone.utc)
    row = await _quota_wait(db, limited_agent, reset_at=now + timedelta(hours=2),
                            scheduled_at=now + timedelta(hours=3))
    rows.append(row.id)

    row.target_agent_id = None
    await db.commit()
    assert await reconcile_queued_demand(db, row, now=now) == "waiting"
    assert row.scheduled_at == now + timedelta(hours=3)

    available_agent = Agent(name=f"Available {uuid.uuid4().hex[:10]}", agent_type="executor",
                            runtime_type="codex", profile_slug=f"available-{uuid.uuid4().hex[:10]}",
                            autonomous_runs=True)
    db.add(available_agent)
    await db.flush()
    row.target_agent_id = available_agent.id
    await db.commit()

    assert await reconcile_queued_demand(db, row, now=now) == "ready"
    assert row.target_agent_id == available_agent.id
    assert row.scheduled_at == now
    await db.delete(available_agent)
    await db.commit()


@pytest.mark.asyncio
async def test_concurrent_periodic_passes_after_restart_reserve_one_run(recovery_world, monkeypatch):
    from app.core.demand_dispatch_guard import reserve_dispatch
    db, agent, rows = recovery_world
    now = datetime.now(timezone.utc)
    row = await _quota_wait(db, agent, reset_at=now - timedelta(seconds=5),
                            scheduled_at=now + timedelta(hours=2))
    demand_id = row.id
    rows.append(demand_id)
    await db.rollback()
    started = []

    async def slots(_db): return 2
    async def busy(_db): return set()
    async def dispatch(session, demand, target_id, command):
        if demand.id != demand_id:
            return
        run_id = await reserve_dispatch(session, demand, target_id, command)
        started.append(run_id)
        demand.dispatch_status = "dispatched"

    monkeypatch.setattr(demand_routes, "_dispatch_slots", slots)
    monkeypatch.setattr(demand_routes, "_agents_already_running", busy)
    monkeypatch.setattr(demand_routes, "_execute_dispatch", dispatch)

    async def periodic_pass():
        # Fresh sessions model restart; no dispatch wake or model worker runs.
        async with AsyncSessionLocal() as session:
            await demand_routes.run_scheduled_dispatch_pass(session)

    await asyncio.gather(periodic_pass(), periodic_pass())
    async with AsyncSessionLocal() as session:
        persisted = await session.get(AgentDemand, demand_id)
        assert persisted.agent_run_id == started[0]
        assert persisted.dispatch_status == "dispatched"
    assert len(started) == 1


@pytest.mark.asyncio
async def test_quota_recovery_preserves_current_approval_requirement(recovery_world):
    from app.core.message_triage import reconcile_queued_demand
    db, agent, rows = recovery_world
    now = datetime.now(timezone.utc)
    row = await _quota_wait(db, agent, reset_at=now - timedelta(seconds=5),
                            scheduled_at=now + timedelta(hours=2))
    rows.append(row.id)
    row.requires_approval = True
    row.approval_status = "pending"
    await db.commit()
    assert await reconcile_queued_demand(db, row, now=now) == "waiting"
    assert row.scheduled_at == now + timedelta(hours=2)
    assert row.agent_run_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["content", "uncertain", "delivered"])
async def test_changed_uncertain_or_delivered_work_is_never_released(recovery_world, monkeypatch, change):
    from app.core import message_triage
    db, agent, rows = recovery_world
    now = datetime.now(timezone.utc)
    row = await _quota_wait(db, agent, reset_at=now - timedelta(seconds=5),
                            scheduled_at=now + timedelta(hours=2))
    rows.append(row.id)
    if change == "content":
        row.body = "Changed scope needs separate assessment"
    elif change == "uncertain":
        row.agent_run_id = "possibly-accepted-run"
        row.dispatch_status = "failed"
        row.dispatch_error = "uncertain outcome"
    else:
        async def delivered(_db, _demand): return True
        monkeypatch.setattr(message_triage, "verified_delivery", delivered)
    await db.commit()
    outcome = await message_triage.reconcile_queued_demand(db, row, now=now)
    assert outcome == ("resolved" if change == "delivered" else "unchanged")
    assert row.scheduled_at != now


@pytest.mark.asyncio
async def test_busy_executor_release_is_discovered_without_a_wake(recovery_world, monkeypatch):
    from app.core.demand_dispatch_guard import reserve_dispatch
    db, agent, rows = recovery_world
    now = datetime.now(timezone.utc)
    row = await _quota_wait(db, agent, reset_at=now - timedelta(seconds=5),
                            scheduled_at=now + timedelta(hours=2))
    rows.append(row.id)
    occupied = {agent.id}
    started = []

    async def slots(_db): return 2
    async def busy(_db): return occupied.copy()
    async def dispatch(session, demand, target_id, command):
        if demand.id != rows[0]: return
        started.append(await reserve_dispatch(session, demand, target_id, command))
        demand.dispatch_status = "dispatched"

    monkeypatch.setattr(demand_routes, "_dispatch_slots", slots)
    monkeypatch.setattr(demand_routes, "_agents_already_running", busy)
    monkeypatch.setattr(demand_routes, "_execute_dispatch", dispatch)
    await demand_routes.run_scheduled_dispatch_pass(db)
    assert started == []
    assert row.agent_run_id is None
    occupied.clear()
    await demand_routes.run_scheduled_dispatch_pass(db)
    assert len(started) == 1


@pytest.mark.asyncio
async def test_bounded_scan_reaches_later_waits_after_restart(recovery_world, monkeypatch):
    db, agent, rows = recovery_world
    due = datetime.now(timezone.utc) + timedelta(days=7)
    demands = [AgentDemand(from_agent="operator", from_agent_id=agent.id, target_agent_id=agent.id,
        subject=f"Fair wait {i}", body="bounded work", origin_type="task", status="new",
        scheduled_at=due) for i in range(201)]
    db.add_all(demands)
    await db.flush()
    rows.extend(d.id for d in demands)
    db.add_all([AuditEvent(entity_type="agent_demand", entity_id=d.id, event_type="demand_reprocess",
        actor="forgehub:usage-limit", payload={"automatic_wait_reason": "quota"}) for d in demands])
    await db.commit()
    original_updated = demands[0].updated_at
    seen = []

    async def waiting(_db, demand, *, now=None):
        if demand.id in rows: seen.append(demand.id)
        return "waiting"
    async def no_capacity(_db): return 0
    monkeypatch.setattr("app.core.message_triage.reconcile_queued_demand", waiting)
    monkeypatch.setattr(demand_routes, "_dispatch_slots", no_capacity)
    await demand_routes.run_scheduled_dispatch_pass(db)
    assert len(seen) <= 200
    # Progress through a bounded scan must survive a fresh session/restart.
    async with AsyncSessionLocal() as restarted:
        await demand_routes.run_scheduled_dispatch_pass(restarted)
        first = await restarted.get(AgentDemand, rows[0])
        assert first.updated_at == original_updated
    assert set(seen) == set(rows)


@pytest.mark.asyncio
async def test_inbox_acknowledgement_crash_keeps_original_dispatch_intent(recovery_world, monkeypatch):
    db, agent, rows = recovery_world
    now = datetime.now(timezone.utc)
    row = AgentDemand(from_agent="operator", target_agent_id=agent.id, subject="Acknowledged work",
        body="One authorized execution", origin_type="task", status="new", working_path="/tmp",
        scheduled_at=now - timedelta(seconds=1))
    db.add(row)
    await db.commit()
    await db.refresh(row)
    rows.append(row.id)
    monkeypatch.setattr(demand_routes.settings, "CHAT_BRIDGE_TOKEN", "ack-test")
    received = await demand_routes.list_pending_for_agent(agent.profile_slug, "ack-test", db)
    assert [item.id for item in received] == [row.id]
    assert row.agent_processed_at is not None
    # The consumer disappears here; the dispatcher still owns the original intent.
    starts = []
    async def slots(_db): return 1
    async def busy(_db): return set()
    async def start(_db, demand, target_id, command):
        starts.append(demand.id)
        demand.agent_run_id = "ack-recovery-run"
        demand.dispatch_status = "dispatched"
        await _db.commit()
    monkeypatch.setattr(demand_routes, "_dispatch_slots", slots)
    monkeypatch.setattr(demand_routes, "_agents_already_running", busy)
    monkeypatch.setattr(demand_routes, "_execute_dispatch", start)
    await demand_routes.run_scheduled_dispatch_pass(db)
    await demand_routes.run_scheduled_dispatch_pass(db)
    assert starts == [row.id]
    assert row.agent_run_id == "ack-recovery-run"

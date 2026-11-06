"""A usage limit is recognised, and plain work moves to a free external agent."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.api.routes import demand as demand_routes
from app.core.agent_availability import (
    HOST_TIMEZONE, RESCHEDULE_MARGIN, classify_infra_failure, describe_reset, parse_usage_limit,
)
from app.core.agent_failover import can_switch, substitute_for
from app.core.demand_dispatch_guard import reserve_dispatch
from app.core.demand_workflow import WorkflowBlocked
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent
from app.db.models.mission_cycle import AgentAvailability
from app.db.models.notification import Notification

NOW = datetime(2026, 11, 3, 23, 0, tzinfo=timezone.utc)
CODEX_DATED = ("You\u2019ve hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit "
               "https://chatgpt.com/settings/usage to purchase more credits or try again at Nov 4th, 2026 6:30 AM.")
AGY = ('"short_error":"RESOURCE_EXHAUSTED (code 429): Individual quota reached. Please upgrade your '
       'subscription to increase your limits. Resets in 22h39m9s."')


def test_real_codex_message_with_a_date_is_recognised():
    until = parse_usage_limit("codex", CODEX_DATED, NOW)
    assert until == datetime(2026, 11, 4, 9, 30, tzinfo=timezone.utc)


def test_real_agy_message_is_recognised():
    assert parse_usage_limit("agy", AGY, NOW) == NOW + timedelta(hours=22, minutes=39, seconds=9)
    assert classify_infra_failure("Individual quota reached.") == "usage_limit"


def test_earlier_formats_still_work():
    text = "You've hit your usage limit. try again at 3:39 PM."
    assert parse_usage_limit("codex", text, NOW) is not None
    assert parse_usage_limit("agy", "work finished", NOW) is None


@pytest.mark.parametrize("field", [
    {"fixed_agent": True}, {"requires_approval": True}, {"task_execution_id": uuid.uuid4()},
    {"mission_context_version_id": uuid.uuid4()}, {"failure_check_source_id": uuid.uuid4()},
])
def test_protected_work_keeps_its_agent(field):
    base = dict(fixed_agent=False, requires_approval=False, task_execution_id=None,
                mission_context_version_id=None, failure_check_source_id=None)
    assert can_switch(SimpleNamespace(**base)) is True
    assert can_switch(SimpleNamespace(**{**base, **field})) is False


@pytest_asyncio.fixture
async def world():
    suffix = uuid.uuid4().hex[:8]
    limited = Agent(id=uuid.uuid4(), name=f"Limitado {suffix}", profile_slug=f"lim-{suffix}",
                    runtime_type="codex", autonomous_runs=True)
    free = Agent(id=uuid.uuid4(), name=f"Livre {suffix}", profile_slug=f"liv-{suffix}",
                 runtime_type="codex", autonomous_runs=True)
    hermes = Agent(id=uuid.uuid4(), name=f"Hermes {suffix}", profile_slug=f"her-{suffix}", runtime_type="hermes")
    demand_ids: list[uuid.UUID] = []
    async with AsyncSessionLocal() as db:
        db.add_all([limited, free, hermes])
        await db.flush()
        db.add(AgentAvailability(agent_id=limited.id, reason="teste", recorded_by="teste",
                                 unavailable_until=datetime.now(timezone.utc) + timedelta(hours=2)))
        await db.commit()

    async def message(target: Agent, **fields) -> AgentDemand:
        row = AgentDemand(from_agent="teste", from_agent_id=free.id, target_agent_id=target.id, subject="Tarefa",
                          body="corpo", origin_type="task", status="new",
                          scheduled_at=datetime.now(timezone.utc) - timedelta(minutes=1), **fields)
        async with AsyncSessionLocal() as db:
            db.add(row)
            await db.commit()
            await db.refresh(row)
        demand_ids.append(row.id)
        return row

    yield SimpleNamespace(limited=limited, free=free, hermes=hermes, message=message)
    ids = [limited.id, free.id, hermes.id]
    async with AsyncSessionLocal() as db:
        checks = (await db.scalars(select(AgentDemand.id).where(
            AgentDemand.failure_check_source_id.in_(demand_ids)))).all()
        await db.execute(delete(AuditEvent).where(AuditEvent.entity_id.in_([*demand_ids, *checks])))
        await db.execute(delete(Notification).where(Notification.event_key.in_(
            [f"demand-usage-limit-wait:{demand_id}:{attempt}" for demand_id in demand_ids for attempt in range(4)]
            + [f"demand-dispatch-failed:{demand_id}:{attempt}" for demand_id in demand_ids for attempt in range(4)])))
        await db.execute(delete(AgentDemand).where(AgentDemand.id.in_(checks)))
        await db.execute(delete(AgentDemand).where(AgentDemand.id.in_(demand_ids)))
        await db.execute(delete(AgentAvailability).where(AgentAvailability.agent_id.in_(ids)))
        await db.execute(delete(Agent).where(Agent.id.in_(ids)))
        await db.commit()


@pytest.mark.asyncio
async def test_only_external_agents_are_replaced(world):
    async with AsyncSessionLocal() as db:
        row = await world.message(world.hermes)
        assert await substitute_for(db, row, {world.hermes.id}, set()) is None
        row = await world.message(world.limited)
        chosen = await substitute_for(db, row, {world.limited.id}, set())
        assert chosen is not None and chosen.id != world.limited.id
        assert chosen.runtime_type in ("codex", "agy", "claude")


async def _pass(monkeypatch) -> list[uuid.UUID]:
    started: list[uuid.UUID] = []

    async def fake_slots(_db):
        return 20

    async def fake_busy(_db):
        return set()

    async def fake_dispatch(_db, demand, target_agent_id, _command):
        started.append(target_agent_id)
        demand.dispatch_status = "dispatched"
        demand.agent_run_id = str(uuid.uuid4())

    monkeypatch.setattr(demand_routes, "_dispatch_slots", fake_slots)
    monkeypatch.setattr(demand_routes, "_agents_already_running", fake_busy)
    monkeypatch.setattr(demand_routes, "_execute_dispatch", fake_dispatch)
    async with AsyncSessionLocal() as db:
        await demand_routes.run_scheduled_dispatch_pass(db)
    return started


@pytest.mark.asyncio
async def test_queued_work_moves_off_the_limited_agent(world, monkeypatch):
    row = await world.message(world.limited)
    await _pass(monkeypatch)
    async with AsyncSessionLocal() as db:
        fresh = await db.get(AgentDemand, row.id)
    assert fresh.target_agent_id != world.limited.id
    assert fresh.body.startswith("## Troca de agente por limite de uso")


@pytest.mark.asyncio
async def test_a_review_waits_for_its_own_agent(world, monkeypatch):
    row = await world.message(world.limited, fixed_agent=True)
    await _pass(monkeypatch)
    async with AsyncSessionLocal() as db:
        fresh = await db.get(AgentDemand, row.id)
    assert fresh.target_agent_id == world.limited.id


def _ended_on_a_limit(ended: datetime, reset: datetime) -> tuple[dict, str]:
    """A failed run as the bridge reports it: a naive host-time end, and a limit
    message with a clock time."""
    zone = ZoneInfo(HOST_TIMEZONE)
    clock = reset.astimezone(zone).strftime("%I:%M %p")
    run_id = str(uuid.uuid4())
    return {"run_id": run_id, "status": "failed", "error": "exit 1",
            "output": f"You've hit your usage limit. try again at {clock}.",
            "finished_at": ended.astimezone(zone).replace(tzinfo=None).isoformat()}, run_id


async def _no_availability_row(agent: Agent) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AgentAvailability).where(AgentAvailability.agent_id == agent.id))
        await db.commit()


async def _availability(agent: Agent) -> datetime | None:
    async with AsyncSessionLocal() as db:
        row = await db.get(AgentAvailability, agent.id)
        return row.unavailable_until if row else None


@pytest.mark.asyncio
@pytest.mark.parametrize("ended_hours_ago, reset_hours_ago", [(4.5, 2.5), (1, -1)])
async def test_reconciling_an_old_result_marks_nobody_unavailable(world, monkeypatch, ended_hours_ago, reset_hours_ago):
    """#42186, whose reset had passed, and one whose reset is still ahead."""
    await _no_availability_row(world.limited)
    now = datetime.now(timezone.utc)
    run, run_id = _ended_on_a_limit(now - timedelta(hours=ended_hours_ago), now - timedelta(hours=reset_hours_ago))
    row = await world.message(world.limited, agent_run_id=run_id, dispatch_status="failed",
                              dispatch_error="The agent run ended as 'failed'.", fixed_agent=True)

    async def fake_poll(_run_id):
        return run

    monkeypatch.setattr(demand_routes, "poll_agent_run", fake_poll)
    async with AsyncSessionLocal() as db:
        await demand_routes.reconcile_message(row.id, db, SimpleNamespace(username="teste"))
    assert await _availability(world.limited) is None


@pytest.mark.asyncio
async def test_the_completion_pass_reconciling_an_uncertain_run_marks_nobody_unavailable(world, monkeypatch):
    await _no_availability_row(world.limited)
    now = datetime.now(timezone.utc)
    run, run_id = _ended_on_a_limit(now - timedelta(hours=1), now + timedelta(hours=1))
    await world.message(world.limited, agent_run_id=run_id, dispatch_status="failed",
                        dispatch_error=demand_routes.RECONCILIATION_REQUIRED_ERROR, fixed_agent=True)

    async def fake_poll(_run_id):
        return run

    monkeypatch.setattr(demand_routes, "poll_agent_run", fake_poll)
    async with AsyncSessionLocal() as db:
        await demand_routes.run_dispatch_completion_pass(db)
    assert await _availability(world.limited) is None


@pytest.mark.asyncio
async def test_a_live_finish_read_late_keeps_the_reset_of_the_end_of_the_run(world, monkeypatch):
    """The pass was late (backend down), the run isn't under reconciliation: a
    reset still ahead is real and stays the one the run announced."""
    await _no_availability_row(world.limited)
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    reset = now + timedelta(hours=1)
    run, run_id = _ended_on_a_limit(now - timedelta(hours=1), reset)
    row = await world.message(world.limited, agent_run_id=run_id, dispatch_status="running", fixed_agent=True)
    async with AsyncSessionLocal() as db:
        await demand_routes._finalize_dispatch(db, row.id, run, expected_run_id=run_id)
        await db.commit()
    assert await _availability(world.limited) == reset


async def _finish_on_a_limit(world, **fields) -> tuple[AgentDemand, datetime]:
    """A message of the limited agent whose run has just ended on a limit."""
    await _no_availability_row(world.limited)
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    reset = now + timedelta(hours=2)
    run, run_id = _ended_on_a_limit(now, reset)
    row = await world.message(world.limited, agent_run_id=run_id, dispatch_status="running",
                              dispatch_attempts=1, working_path="/tmp", **fields)
    async with AsyncSessionLocal() as db:
        await demand_routes._finalize_dispatch(db, row.id, run, expected_run_id=run_id)
        await db.commit()
    async with AsyncSessionLocal() as db:
        return await db.get(AgentDemand, row.id), reset


@pytest.mark.asyncio
async def test_a_fixed_agent_message_waits_for_the_reset_and_then_runs(world, monkeypatch):
    fresh, reset = await _finish_on_a_limit(world, fixed_agent=True)
    assert fresh.dispatch_status is None and fresh.agent_run_id is None
    assert fresh.target_agent_id == world.limited.id
    assert fresh.scheduled_at == reset + RESCHEDULE_MARGIN
    assert describe_reset(reset) in fresh.dispatch_error
    async with AsyncSessionLocal() as db:
        assert await db.scalar(select(AgentDemand.id).where(AgentDemand.failure_check_source_id == fresh.id)) is None
        notice = await db.scalar(select(Notification).where(
            Notification.event_key == f"demand-usage-limit-wait:{fresh.id}:1"))
    assert notice.severity == "warning"

    # Before the reset: not due, and the pass leaves it alone.
    assert await _pass(monkeypatch) == []
    # Due, but the agent is still out of quota: skipped, no attempt spent.
    async with AsyncSessionLocal() as db:
        row = await db.get(AgentDemand, fresh.id)
        row.scheduled_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await db.commit()
    assert await _pass(monkeypatch) == []
    async with AsyncSessionLocal() as db:
        row = await db.get(AgentDemand, fresh.id)
        assert row.dispatch_attempts == 1 and row.target_agent_id == world.limited.id
        with pytest.raises(WorkflowBlocked, match="AGENT_UNAVAILABLE"):
            await reserve_dispatch(db, row, world.limited.id, None)
        await db.rollback()
    # After the reset: it runs, on the same agent.
    await _no_availability_row(world.limited)
    assert await _pass(monkeypatch) == [world.limited.id]


@pytest.mark.asyncio
async def test_a_failure_check_waits_for_the_reset(world):
    source = await world.message(world.free, dispatch_status="failed", dispatch_error="x")
    fresh, reset = await _finish_on_a_limit(world, failure_check_source_id=source.id)
    assert fresh.dispatch_status is None and fresh.scheduled_at == reset + RESCHEDULE_MARGIN
    assert fresh.target_agent_id == world.limited.id


@pytest.mark.asyncio
async def test_without_fixed_agent_the_failover_is_unchanged(world, monkeypatch):
    fresh, reset = await _finish_on_a_limit(world)
    assert fresh.dispatch_status is None and fresh.dispatch_error is None and fresh.scheduled_at < reset
    await _pass(monkeypatch)
    async with AsyncSessionLocal() as db:
        assert (await db.get(AgentDemand, fresh.id)).target_agent_id != world.limited.id


@pytest.mark.asyncio
async def test_an_approved_text_stays_failed_and_names_the_limit(world):
    fresh, reset = await _finish_on_a_limit(world, requires_approval=True, approval_status="approved")
    assert fresh.dispatch_status == "failed" and describe_reset(reset) in fresh.dispatch_error


@pytest.mark.asyncio
async def test_a_run_with_no_limit_stays_failed(world):
    run_id = str(uuid.uuid4())
    row = await world.message(world.limited, agent_run_id=run_id, dispatch_status="running",
                              dispatch_attempts=1, fixed_agent=True)
    async with AsyncSessionLocal() as db:
        await demand_routes._finalize_dispatch(
            db, row.id, {"run_id": run_id, "status": "failed", "output": "exit 1"}, expected_run_id=run_id)
        await db.commit()
    async with AsyncSessionLocal() as db:
        fresh = await db.get(AgentDemand, row.id)
    assert fresh.dispatch_status == "failed" and fresh.dispatch_error == "The agent run ended as 'failed'."

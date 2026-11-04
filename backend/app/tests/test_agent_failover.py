"""A usage limit is recognised, and plain work moves to a free external agent."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.api.routes import demand as demand_routes
from app.core.agent_availability import classify_infra_failure, parse_usage_limit
from app.core.agent_failover import can_switch, substitute_for
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent
from app.db.models.mission_cycle import AgentAvailability

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
        await db.execute(delete(AuditEvent).where(AuditEvent.entity_id.in_(demand_ids)))
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

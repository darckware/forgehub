"""Failure contingency: deadline, concurrency cap, attempt limit, reprocess.

Agreed 2026-08-13 (Marcelo: "notificação de todas as falhas ao usuário, e
prazo para retorno e adicionar um icone de reprocessamento das falhas",
"no máximo 5. Vai depender no computador", "no máximo 3" attempts).

What these protect:
  - a run that hangs is failed by its deadline instead of waiting forever
    at "running", which never reaches a terminal state and so never fires
    the feedback that only triggers on completed/failed;
  - every failure notifies, not just the one path that used to;
  - the concurrency cap counts runs already in flight, not just the ones a
    single pass is about to start -- otherwise each 30s cycle stacks another
    batch on top and the cap bounds nothing;
  - reprocessing is bounded, so nobody re-runs forever something whose cause
    was never fixed.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.api.routes.demand import _dispatch_slots, run_dispatch_timeout_pass
from app.core.config import settings
from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.demand import DISPATCH_MAX_ATTEMPTS, AgentDemand
from app.db.models.notification import Notification


@pytest_asyncio.fixture
async def client():
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {create_access_token('test-contingency')}"},
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def agent():
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        a = Agent(
            name=f"Contingency {suffix}", agent_type="executor",
            runtime_type="claude", profile_slug=f"conting-{suffix}",
        )
        session.add(a)
        await session.commit()
        agent_id = a.id

    yield agent_id

    async with AsyncSessionLocal() as session:
        ids = (
            await session.execute(
                select(AgentDemand.id).where(AgentDemand.target_agent_id == agent_id)
            )
        ).scalars().all()
        for did in ids:
            await session.execute(
                delete(Notification).where(
                    Notification.event_key.like(f"demand-dispatch-failed:{did}%")
                )
            )
        await session.execute(delete(AgentDemand).where(AgentDemand.target_agent_id == agent_id))
        await session.execute(delete(Agent).where(Agent.id == agent_id))
        await session.commit()


async def _dispatched(agent_id, *, deadline_in: timedelta, status: str = "running",
                      attempts: int = 1) -> uuid.UUID:
    async with AsyncSessionLocal() as session:
        d = AgentDemand(
            from_agent="tester",
            from_agent_id=agent_id,
            target_agent_id=agent_id,
            subject=f"despacho {uuid.uuid4().hex[:6]}",
            body="rodando",
            origin_type="task",
            dispatch_status=status,
            dispatch_attempts=attempts,
            dispatch_deadline_at=datetime.now(timezone.utc) + deadline_in,
        )
        session.add(d)
        await session.commit()
        return d.id


async def test_a_hung_run_is_failed_when_its_deadline_passes(agent):
    demand_id = await _dispatched(agent, deadline_in=timedelta(minutes=-1))

    async with AsyncSessionLocal() as session:
        assert await run_dispatch_timeout_pass(session) >= 1

    async with AsyncSessionLocal() as session:
        d = await session.get(AgentDemand, demand_id)
        assert d.dispatch_status == "failed"
        assert "45 minutes" in d.dispatch_error
        # Cleared, so the sweep can't re-fail an already-terminal row.
        assert d.dispatch_deadline_at is None


async def test_a_run_inside_its_deadline_is_left_alone(agent):
    demand_id = await _dispatched(agent, deadline_in=timedelta(minutes=30))

    async with AsyncSessionLocal() as session:
        await run_dispatch_timeout_pass(session)

    async with AsyncSessionLocal() as session:
        d = await session.get(AgentDemand, demand_id)
        assert d.dispatch_status == "running"


async def test_every_failure_notifies(agent):
    demand_id = await _dispatched(agent, deadline_in=timedelta(minutes=-1))

    async with AsyncSessionLocal() as session:
        await run_dispatch_timeout_pass(session)

    async with AsyncSessionLocal() as session:
        notes = (
            await session.execute(
                select(Notification).where(
                    Notification.event_key.like(f"demand-dispatch-failed:{demand_id}%")
                )
            )
        ).scalars().all()
        assert len(notes) == 1
        assert notes[0].severity == "error"


async def test_the_cap_counts_runs_already_in_flight(agent):
    """The cap is about the host, so it must count what is already running --
    a per-pass limit would let every cycle stack another batch on top."""
    async with AsyncSessionLocal() as session:
        before = await _dispatch_slots(session)

    await _dispatched(agent, deadline_in=timedelta(minutes=30), status="running")

    async with AsyncSessionLocal() as session:
        after = await _dispatch_slots(session)
    assert after == before - 1

    # And it never goes negative, however many are in flight.
    for _ in range(settings.MAX_CONCURRENT_DISPATCHES + 2):
        await _dispatched(agent, deadline_in=timedelta(minutes=30), status="dispatched")
    async with AsyncSessionLocal() as session:
        assert await _dispatch_slots(session) == 0


async def test_reprocess_requeues_without_dispatching_inline(client: AsyncClient, agent):
    """Reprocessing clears the execution state and lets the scheduled pass
    pick it up -- so a bulk reprocess still goes through the cap instead of
    starting dozens of runs at once."""
    demand_id = await _dispatched(agent, deadline_in=timedelta(minutes=-1))
    async with AsyncSessionLocal() as session:
        await run_dispatch_timeout_pass(session)

    response = await client.post(f"/api/v1/demands/{demand_id}:reprocess")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["dispatch_status"] is None
    assert body["dispatch_deadline_at"] is None
    assert body["scheduled_at"] is not None
    # The attempt history is kept -- resetting it would make the limit
    # unreachable by construction.
    assert body["dispatch_attempts"] == 1


async def test_reprocess_is_refused_once_attempts_are_exhausted(client: AsyncClient, agent):
    demand_id = await _dispatched(
        agent, deadline_in=timedelta(minutes=-1), attempts=DISPATCH_MAX_ATTEMPTS
    )
    async with AsyncSessionLocal() as session:
        await run_dispatch_timeout_pass(session)

    response = await client.post(f"/api/v1/demands/{demand_id}:reprocess")
    assert response.status_code == 409, response.text
    assert str(DISPATCH_MAX_ATTEMPTS) in response.json()["detail"]


async def test_only_a_failed_dispatch_can_be_reprocessed(client: AsyncClient, agent):
    demand_id = await _dispatched(agent, deadline_in=timedelta(minutes=30), status="running")
    response = await client.post(f"/api/v1/demands/{demand_id}:reprocess")
    assert response.status_code == 400, response.text


async def test_one_run_per_agent_never_overlaps(agent):
    """The global cap alone doesn't prevent five free slots all landing on
    the same agent -- which would run five sessions of one CLI against the
    same profile and working path, overlapping their contexts."""
    from app.api.routes.demand import _agents_already_running

    async with AsyncSessionLocal() as session:
        assert agent not in await _agents_already_running(session)

    await _dispatched(agent, deadline_in=timedelta(minutes=30), status="running")

    async with AsyncSessionLocal() as session:
        busy = await _agents_already_running(session)
    assert agent in busy, "an agent with a run in flight must be reported busy"


async def test_a_finished_run_frees_its_agent(agent):
    """Busy is about in-flight work only: once a run reaches a terminal
    state the agent is available again, otherwise one dispatch would block
    that agent forever."""
    from app.api.routes.demand import _agents_already_running

    demand_id = await _dispatched(agent, deadline_in=timedelta(minutes=30), status="running")
    async with AsyncSessionLocal() as session:
        d = await session.get(AgentDemand, demand_id)
        d.dispatch_status = "completed"
        d.dispatch_deadline_at = None
        await session.commit()

    async with AsyncSessionLocal() as session:
        assert agent not in await _agents_already_running(session)

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

import httpx
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.api.routes.demand import (
    RECONCILIATION_REQUIRED_ERROR,
    _dispatch_slots,
    run_dispatch_completion_pass,
    run_dispatch_timeout_pass,
)
from app.core.config import settings
from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.demand import DISPATCH_MAX_ATTEMPTS, AgentDemand
from app.db.models.notification import Notification


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2001, 1, 1, tzinfo=timezone.utc)
        return value if tz is not None else value.replace(tzinfo=None)


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
        assert d.dispatch_error == RECONCILIATION_REQUIRED_ERROR
        # Cleared, so the sweep can't re-fail an already-terminal row.
        assert d.dispatch_deadline_at is None


async def test_deadline_expiry_requires_reconciliation_before_reprocess(client: AsyncClient, agent):
    """Removing the reconciliation marker would let a possibly-live run be replaced."""
    demand_id = await _dispatched(agent, deadline_in=timedelta(minutes=-1))
    async with AsyncSessionLocal() as session:
        demand = await session.get(AgentDemand, demand_id)
        demand.agent_run_id = str(uuid.uuid4())
        await session.commit()
        await run_dispatch_timeout_pass(session)

    response = await client.post(f"/api/v1/demands/{demand_id}:reprocess")

    assert response.status_code == 409, response.text
    async with AsyncSessionLocal() as session:
        demand = await session.get(AgentDemand, demand_id)
        assert demand.agent_run_id is not None
        assert demand.dispatch_error == RECONCILIATION_REQUIRED_ERROR


async def test_lost_known_run_requires_reconciliation_before_reprocess(client: AsyncClient, agent, monkeypatch):
    """A bridge 404 cannot prove that the old run never performed work."""
    from app.api.routes import demand as demand_routes

    demand_id = await _dispatched(agent, deadline_in=timedelta(minutes=30), status="dispatched")
    run_id = str(uuid.uuid4())
    async with AsyncSessionLocal() as session:
        demand = await session.get(AgentDemand, demand_id)
        demand.agent_run_id = run_id
        await session.commit()

    async def lost_run(_run_id):
        request = httpx.Request("GET", "http://bridge/v1/agent-runs/lost")
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("not found", request=request, response=response)

    monkeypatch.setattr(demand_routes, "poll_agent_run", lost_run)
    async with AsyncSessionLocal() as session:
        await run_dispatch_completion_pass(session)

    response = await client.post(f"/api/v1/demands/{demand_id}:reprocess")

    assert response.status_code == 409, response.text
    async with AsyncSessionLocal() as session:
        demand = await session.get(AgentDemand, demand_id)
        assert demand.agent_run_id == run_id
        assert demand.dispatch_error == RECONCILIATION_REQUIRED_ERROR


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


async def test_connect_failure_isolated_from_next_agent_and_backed_off(monkeypatch):
    """One broken runtime must not expire the remaining queue or hot-loop."""
    from app.api.routes import demand as demand_routes

    suffix = uuid.uuid4().hex[:8]
    due = FrozenDateTime(2000, 12, 31, tzinfo=timezone.utc)
    agent_ids: list[uuid.UUID] = []
    demand_ids: list[uuid.UUID] = []
    async with AsyncSessionLocal() as session:
        agents = [
            Agent(name=f"Broken runtime {suffix}", agent_type="executor", runtime_type="codex"),
            Agent(name=f"Healthy runtime {suffix}", agent_type="executor", runtime_type="hermes", profile_slug=f"healthy-{suffix}"),
        ]
        session.add_all(agents)
        await session.flush()
        agent_ids = [item.id for item in agents]
        demands = [
            AgentDemand(
                from_agent="tester", from_agent_id=agents[0].id, target_agent_id=agents[0].id,
                subject=f"first fails {suffix}", body="fail", origin_type="task", scheduled_at=due,
                working_path="/root/project/test-fixture",
            ),
            AgentDemand(
                from_agent="tester", from_agent_id=agents[1].id, target_agent_id=agents[1].id,
                subject=f"second runs {suffix}", body="run", origin_type="task", scheduled_at=due + timedelta(seconds=1),
                working_path="/root/project/test-fixture",
            ),
        ]
        session.add_all(demands)
        await session.commit()
        demand_ids = [item.id for item in demands]

    calls: list[uuid.UUID] = []

    async def fake_dispatch(_run_id, target, _prompt, _path):
        calls.append(target.id)
        if target.id == agent_ids[0]:
            request = httpx.Request("POST", "http://bridge/v1/agent-runs")
            raise httpx.ConnectError("bridge unavailable", request=request)
        return {"run_id": "healthy-run"}

    monkeypatch.setattr(demand_routes, "datetime", FrozenDateTime)
    monkeypatch.setattr(demand_routes, "dispatch_agent_run", fake_dispatch)
    async def no_notice(*_args, **_kwargs):
        return None

    monkeypatch.setattr(demand_routes, "_send_notice", no_notice)

    try:
        async with AsyncSessionLocal() as session:
            await demand_routes.run_scheduled_dispatch_pass(session)

        async with AsyncSessionLocal() as session:
            failed = await session.get(AgentDemand, demand_ids[0])
            healthy = await session.get(AgentDemand, demand_ids[1])
            assert calls == agent_ids
            assert failed.dispatch_status is None
            assert failed.dispatch_attempts == 1
            assert failed.dispatch_error == "Host bridge temporarily unavailable"
            assert failed.scheduled_at > FrozenDateTime.now(timezone.utc)
            assert healthy.dispatch_status == "dispatched"
            assert healthy.dispatch_attempts == 1

        # A second poll before the retry deadline must not launch either
        # the backed-off message or the already running healthy message.
        async with AsyncSessionLocal() as session:
            await demand_routes.run_scheduled_dispatch_pass(session)
        assert calls == agent_ids
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(Notification).where(Notification.event_key.like(f"demand-dispatch-failed:%{suffix}%")))
            await session.execute(delete(AgentDemand).where(AgentDemand.id.in_(demand_ids)))
            await session.execute(delete(Agent).where(Agent.id.in_(agent_ids)))
            await session.commit()


async def test_transient_start_failure_becomes_terminal_after_three_attempts(agent, monkeypatch):
    from app.api.routes import demand as demand_routes

    due = FrozenDateTime(2000, 12, 31, tzinfo=timezone.utc)
    async with AsyncSessionLocal() as session:
        item = AgentDemand(
            from_agent="tester",
            from_agent_id=agent,
            target_agent_id=agent,
            subject=f"bounded retry {uuid.uuid4().hex[:8]}",
            working_path="/root/project/test-fixture",
            body="fail safely",
            origin_type="task",
            scheduled_at=due,
        )
        session.add(item)
        await session.commit()
        demand_id = item.id

    async def unavailable(*_args, **_kwargs):
        request = httpx.Request("POST", "http://bridge/v1/agent-runs")
        raise httpx.ConnectError("bridge unavailable", request=request)

    monkeypatch.setattr(demand_routes, "datetime", FrozenDateTime)
    monkeypatch.setattr(demand_routes, "dispatch_agent_run", unavailable)

    try:
        for expected_attempts in (1, 2, 3):
            async with AsyncSessionLocal() as session:
                queued = await session.get(AgentDemand, demand_id)
                queued.scheduled_at = due
                await session.commit()
            async with AsyncSessionLocal() as session:
                await demand_routes.run_scheduled_dispatch_pass(session)
            async with AsyncSessionLocal() as session:
                queued = await session.get(AgentDemand, demand_id)
                assert queued.dispatch_attempts == expected_attempts

        async with AsyncSessionLocal() as session:
            queued = await session.get(AgentDemand, demand_id)
            notices = (
                await session.execute(
                    select(Notification).where(
                        Notification.event_key == f"demand-dispatch-failed:{demand_id}:3"
                    )
                )
            ).scalars().all()
            assert queued.dispatch_status == "failed"
            assert queued.dispatch_error == "Host bridge temporarily unavailable"
            assert len(notices) == 1
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(Notification).where(
                    Notification.event_key.like(f"demand-dispatch-failed:{demand_id}%")
                )
            )
            await session.execute(delete(AgentDemand).where(AgentDemand.id == demand_id))
            await session.commit()


async def test_response_timeout_is_failed_without_automatic_retry(client: AsyncClient, agent, monkeypatch):
    """A read timeout can happen after the bridge accepted the run, so retrying
    would start the same work twice. The generated run id stays available for
    reconciliation instead."""
    from app.api.routes import demand as demand_routes

    due = FrozenDateTime(2000, 12, 31, tzinfo=timezone.utc)
    async with AsyncSessionLocal() as session:
        item = AgentDemand(
            from_agent="tester", from_agent_id=agent, target_agent_id=agent,
            subject=f"ambiguous timeout {uuid.uuid4().hex[:8]}", body="do once",
            origin_type="task", scheduled_at=due,
            working_path="/root/project/test-fixture",
        )
        session.add(item)
        await session.commit()
        demand_id = item.id

    calls: list[str] = []

    async def accepted_but_timed_out(run_id, *_args):
        calls.append(run_id)
        raise httpx.ReadTimeout(
            "bridge response timed out",
            request=httpx.Request("POST", "http://bridge/v1/agent-runs"),
        )

    monkeypatch.setattr(demand_routes, "datetime", FrozenDateTime)
    monkeypatch.setattr(demand_routes, "dispatch_agent_run", accepted_but_timed_out)
    monkeypatch.setattr(demand_routes, "_send_notice", lambda *_args: None)

    try:
        async with AsyncSessionLocal() as session:
            await demand_routes.run_scheduled_dispatch_pass(session)
        async with AsyncSessionLocal() as session:
            item = await session.get(AgentDemand, demand_id)
            assert item.dispatch_status == "failed"
            assert item.agent_run_id == calls[0]
            assert item.dispatch_attempts == 1
            assert "reconcile" in item.dispatch_error.lower()
            assert item.scheduled_at == due

        async with AsyncSessionLocal() as session:
            await demand_routes.run_scheduled_dispatch_pass(session)
        assert calls == [calls[0]]

        # A manual reprocess cannot erase the retained identity and turn an
        # uncertain execution back into a second automatic start.
        response = await client.post(f"/api/v1/demands/{demand_id}:reprocess")
        assert response.status_code == 409, response.text
        assert "reconcile" in response.json()["detail"].lower()
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(Notification).where(Notification.event_key.like(f"demand-dispatch-failed:{demand_id}%")))
            await session.execute(delete(AgentDemand).where(AgentDemand.id == demand_id))
            await session.commit()


async def test_exception_after_bridge_response_is_failed_without_automatic_retry(agent, monkeypatch):
    """A local exception after an accepted response is equally ambiguous and
    must retain the accepted run identity instead of reissuing it."""
    from app.api.routes import demand as demand_routes

    due = FrozenDateTime(2000, 12, 31, tzinfo=timezone.utc)
    async with AsyncSessionLocal() as session:
        item = AgentDemand(
            from_agent="tester", from_agent_id=agent, target_agent_id=agent,
            subject=f"post-response failure {uuid.uuid4().hex[:8]}", body="do once",
            origin_type="task", scheduled_at=due,
            working_path="/root/project/test-fixture",
        )
        session.add(item)
        await session.commit()
        demand_id = item.id

    calls: list[str] = []

    async def accepted(run_id, *_args):
        calls.append(run_id)
        return {"run_id": run_id}

    async def fail_after_response(*_args):
        raise RuntimeError("commit-side failure after bridge acceptance")

    monkeypatch.setattr(demand_routes, "datetime", FrozenDateTime)
    monkeypatch.setattr(demand_routes, "dispatch_agent_run", accepted)
    monkeypatch.setattr(demand_routes, "_send_notice", fail_after_response)

    try:
        async with AsyncSessionLocal() as session:
            await demand_routes.run_scheduled_dispatch_pass(session)
        async with AsyncSessionLocal() as session:
            item = await session.get(AgentDemand, demand_id)
            assert item.dispatch_status == "failed"
            assert item.agent_run_id == calls[0]
            assert item.dispatch_attempts == 1
            assert "reconcile" in item.dispatch_error.lower()
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(Notification).where(Notification.event_key.like(f"demand-dispatch-failed:{demand_id}%")))
            await session.execute(delete(AgentDemand).where(AgentDemand.id == demand_id))
            await session.commit()


async def test_reprocess_resets_failure_feedback_for_the_next_authorized_attempt(client: AsyncClient, agent):
    demand_id = await _dispatched(agent, deadline_in=timedelta(minutes=-1))
    async with AsyncSessionLocal() as session:
        first = await session.get(AgentDemand, demand_id)
        first.channel = "agent"
        await session.commit()
        await run_dispatch_timeout_pass(session)

    async with AsyncSessionLocal() as session:
        first_replies = list((await session.execute(
            select(AgentDemand).where(AgentDemand.reply_to_id == demand_id)
        )).scalars())
        assert len(first_replies) == 1
        assert (await session.get(AgentDemand, demand_id)).feedback_sent_at is not None

    response = await client.post(f"/api/v1/demands/{demand_id}:reprocess")
    assert response.status_code == 200, response.text
    assert response.json()["feedback_sent_at"] is None

    async with AsyncSessionLocal() as session:
        retry = await session.get(AgentDemand, demand_id)
        retry.dispatch_status = "running"
        retry.dispatch_attempts = 2
        retry.dispatch_deadline_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await session.commit()
        await run_dispatch_timeout_pass(session)
        replies = list((await session.execute(
            select(AgentDemand).where(AgentDemand.reply_to_id == demand_id)
        )).scalars())
        assert len(replies) == 2

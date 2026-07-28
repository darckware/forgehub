"""Backlog work is only dispatchable once it has a registered sender.

`backlog` is parked work: not a task yet, nobody has taken it on. Dispatching
one with no `from_agent_id` produces a run with no agent on the record to
answer for it -- a `requires_response` reply has nowhere to route back to, and
the execution ends up owned by a free-text label ("marcelo") that resolves to
no agent at all.

Both entry points are covered: the manual route refuses with a 400 the operator
can act on, and the scheduled loop simply never picks the item up (skipped, not
marked failed -- nothing was attempted).
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand


@pytest_asyncio.fixture
async def client():
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {create_access_token('test-backlog')}"},
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def scenario():
    """A target agent, plus backlog items with and without a registered sender."""
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        target = Agent(
            name=f"Backlog Target {suffix}", agent_type="executor",
            runtime_type="claude", profile_slug=f"backlog-target-{suffix}",
        )
        sender = Agent(
            name=f"Backlog Sender {suffix}", agent_type="executor",
            runtime_type="claude", profile_slug=f"backlog-sender-{suffix}",
        )
        session.add_all([target, sender])
        await session.flush()

        due = datetime.now(timezone.utc) - timedelta(minutes=1)
        orphan = AgentDemand(
            from_agent="marcelo",  # free text, resolves to no agent
            subject=f"backlog sem from {suffix}", body="parked",
            origin_type="backlog", target_agent_id=target.id, scheduled_at=due,
        )
        owned = AgentDemand(
            from_agent=sender.profile_slug,
            subject=f"backlog com from {suffix}", body="parked but owned",
            origin_type="backlog", from_agent_id=sender.id, target_agent_id=target.id,
        )
        session.add_all([orphan, owned])
        await session.commit()
        data = {
            "target_id": target.id,
            "sender_id": sender.id,
            "orphan_id": orphan.id,
            "owned_id": owned.id,
        }

    yield data

    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(AgentDemand).where(AgentDemand.id.in_([data["orphan_id"], data["owned_id"]]))
        )
        await session.execute(
            delete(Agent).where(Agent.id.in_([data["target_id"], data["sender_id"]]))
        )
        await session.commit()


async def test_backlog_without_sender_is_refused(client: AsyncClient, scenario):
    response = await client.post(
        f"/api/v1/demands/{scenario['orphan_id']}/dispatch",
        json={"target_agent_id": str(scenario["target_id"])},
    )
    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert "Backlog" in detail and "From" in detail

    async with AsyncSessionLocal() as session:
        demand = await session.get(AgentDemand, scenario["orphan_id"])
        # Refused before anything ran: no dispatch state was written.
        assert demand.dispatch_status is None
        assert demand.agent_run_id is None


async def test_scheduled_loop_skips_backlog_without_sender(scenario):
    """The orphan is due and addressed, so only the rule keeps it parked --
    and it must stay NULL, not become 'failed': nothing was attempted."""
    from app.api.routes.demand import run_scheduled_dispatch_pass

    async with AsyncSessionLocal() as session:
        await run_scheduled_dispatch_pass(session)

    async with AsyncSessionLocal() as session:
        demand = await session.get(AgentDemand, scenario["orphan_id"])
        assert demand.dispatch_status is None


async def test_backlog_with_sender_passes_the_rule(client: AsyncClient, scenario, monkeypatch):
    """With a registered From the item is dispatchable like any other -- the
    rule is about ownership, not about backlog being frozen forever."""
    from app.api.routes import demand as demand_routes

    async def fake_dispatch(*args, **kwargs):
        return {"run_id": "fake-run-id"}

    monkeypatch.setattr(demand_routes, "dispatch_agent_run", fake_dispatch)

    response = await client.post(
        f"/api/v1/demands/{scenario['owned_id']}/dispatch",
        json={"target_agent_id": str(scenario["target_id"])},
    )
    assert response.status_code == 200, response.text
    assert response.json()["dispatch_status"] == "dispatched"


async def test_non_backlog_without_sender_still_dispatches(client: AsyncClient, scenario, monkeypatch):
    """An operator filing a Task for an agent is the ordinary case and must
    not be caught by this rule."""
    from app.api.routes import demand as demand_routes

    async def fake_dispatch(*args, **kwargs):
        return {"run_id": "fake-run-id"}

    monkeypatch.setattr(demand_routes, "dispatch_agent_run", fake_dispatch)

    async with AsyncSessionLocal() as session:
        task = AgentDemand(
            from_agent="marcelo",
            subject=f"task sem from {uuid.uuid4().hex[:6]}",
            body="do it",
            origin_type="task",
            target_agent_id=scenario["target_id"],
        )
        session.add(task)
        await session.commit()
        task_id = task.id

    try:
        response = await client.post(
            f"/api/v1/demands/{task_id}/dispatch",
            json={"target_agent_id": str(scenario["target_id"])},
        )
        assert response.status_code == 200, response.text
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(AgentDemand).where(AgentDemand.id == task_id))
            await session.commit()


async def test_orphan_backlog_is_still_listed(client: AsyncClient, scenario):
    """Blocked from running, not hidden: it stays visible in the Backlog
    folder so someone can set a sender on it."""
    response = await client.get("/api/v1/demands")
    assert response.status_code == 200
    ids = [d["id"] for d in response.json()]
    assert str(scenario["orphan_id"]) in ids

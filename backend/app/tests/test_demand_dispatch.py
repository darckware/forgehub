"""Tests for the Inbox agent-dispatch endpoints (POST .../dispatch, GET
.../dispatch-status) added to the demand domain -- see
core/agent_runs.py / core/demand_thread.py and
PROPOSTA-INBOX-DISPATCH-E-DIALOGO-ENTRE-AGENTES.md for the design this
implements.

DB strategy matches test_demand.py: each test creates its own rows (agent
included, UUID-suffixed) and removes them in a finally block. The actual
live POST to the host-bridge's /v1/agent-runs isn't exercised here (no
existing test in this repo mocks that external call either -- see
test_execution_runtime.py) -- these tests cover validation/error paths that
never reach the network call, plus the target_agent_id assignment path.
"""
import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand
from app.db.models.notification import Notification


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('test-demand-dispatch')}"}


@pytest_asyncio.fixture
async def client():
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=_auth_headers()) as ac:
        yield ac


@pytest_asyncio.fixture
async def dispatchable_agent():
    """A throwaway agent with runtime_type set but no ForgeRouter
    credential -- enough to exercise the "no credential" 409 path without
    ever reaching the host-bridge."""
    async with AsyncSessionLocal() as session:
        agent = Agent(
            name=f"Test Dispatch Agent {uuid.uuid4().hex[:8]}",
            agent_type="executor",
            runtime_type="claude",
        )
        session.add(agent)
        await session.commit()
        await session.refresh(agent)
        agent_id = agent.id

    yield agent_id

    async with AsyncSessionLocal() as session:
        await session.execute(delete(Agent).where(Agent.id == agent_id))
        await session.commit()


@pytest_asyncio.fixture
async def non_dispatchable_agent():
    """An agent with no runtime_type (e.g. Athos-like) -- can't be a
    dispatch target at all."""
    async with AsyncSessionLocal() as session:
        agent = Agent(name=f"Test Non-Dispatch Agent {uuid.uuid4().hex[:8]}", agent_type="coordinator")
        session.add(agent)
        await session.commit()
        await session.refresh(agent)
        agent_id = agent.id

    yield agent_id

    async with AsyncSessionLocal() as session:
        await session.execute(delete(Agent).where(Agent.id == agent_id))
        await session.commit()


async def _create_demand(client: AsyncClient, **overrides) -> dict:
    payload = {
        "from_agent": "test-suite",
        "subject": f"Test dispatch demand {uuid.uuid4().hex[:8]}",
        "body": "Please do the thing.",
        **overrides,
    }
    resp = await client.post("/api/v1/demands", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _delete_demand(demand_id: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(delete(AgentDemand).where(AgentDemand.id == uuid.UUID(demand_id)))
        await session.execute(delete(Notification).where(Notification.event_key == f"demand:{demand_id}"))
        await session.commit()


async def test_assign_target_agent_without_dispatching(client: AsyncClient, dispatchable_agent):
    demand = await _create_demand(client)
    try:
        resp = await client.patch(
            f"/api/v1/demands/{demand['id']}", json={"target_agent_id": str(dispatchable_agent)}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["target_agent_id"] == str(dispatchable_agent)
        assert resp.json()["dispatch_status"] is None  # not dispatched yet, just assigned
    finally:
        await _delete_demand(demand["id"])


async def test_dispatch_requires_target_or_reply_flag(client: AsyncClient):
    demand = await _create_demand(client)
    try:
        resp = await client.post(f"/api/v1/demands/{demand['id']}/dispatch", json={})
        assert resp.status_code == 400
    finally:
        await _delete_demand(demand["id"])


async def test_dispatch_rejects_both_target_and_reply_flag(client: AsyncClient, dispatchable_agent):
    demand = await _create_demand(client)
    try:
        resp = await client.post(
            f"/api/v1/demands/{demand['id']}/dispatch",
            json={"target_agent_id": str(dispatchable_agent), "reply_to_sender": True},
        )
        assert resp.status_code == 400
    finally:
        await _delete_demand(demand["id"])


async def test_dispatch_reply_to_sender_without_origin_fails(client: AsyncClient):
    demand = await _create_demand(client)
    try:
        resp = await client.post(
            f"/api/v1/demands/{demand['id']}/dispatch", json={"reply_to_sender": True}
        )
        assert resp.status_code == 400
    finally:
        await _delete_demand(demand["id"])


async def test_dispatch_unknown_agent_404s(client: AsyncClient):
    demand = await _create_demand(client)
    try:
        resp = await client.post(
            f"/api/v1/demands/{demand['id']}/dispatch",
            json={"target_agent_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404
    finally:
        await _delete_demand(demand["id"])


async def test_dispatch_agent_without_runtime_type_rejected(client: AsyncClient, non_dispatchable_agent):
    demand = await _create_demand(client)
    try:
        resp = await client.post(
            f"/api/v1/demands/{demand['id']}/dispatch",
            json={"target_agent_id": str(non_dispatchable_agent)},
        )
        assert resp.status_code == 409
    finally:
        await _delete_demand(demand["id"])


async def test_dispatch_agent_without_credential_rejected(client: AsyncClient, dispatchable_agent):
    """dispatchable_agent has runtime_type but no forgerouter_api_key_encrypted
    -- fails before ever reaching the host-bridge network call."""
    demand = await _create_demand(client)
    try:
        resp = await client.post(
            f"/api/v1/demands/{demand['id']}/dispatch",
            json={"target_agent_id": str(dispatchable_agent)},
        )
        assert resp.status_code == 409
    finally:
        await _delete_demand(demand["id"])


async def test_dispatch_status_requires_dispatch_first(client: AsyncClient):
    demand = await _create_demand(client)
    try:
        resp = await client.get(f"/api/v1/demands/{demand['id']}/dispatch-status")
        assert resp.status_code == 400
    finally:
        await _delete_demand(demand["id"])

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
    """A throwaway agent with runtime_type set -- used by the tests that
    only assign/read a target agent, never the ones that actually POST
    .../dispatch (a claude-runtime agent now dispatches for real, credential
    or not; see hermes_agent_without_profile for the 409 path)."""
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
async def hermes_agent_without_profile():
    """A hermes-runtime agent with no profile_slug -- enough to exercise the
    remaining AgentRunDispatchError 409 path without ever reaching the
    host-bridge (see test_dispatch_hermes_agent_without_profile_rejected)."""
    async with AsyncSessionLocal() as session:
        agent = Agent(
            name=f"Test Hermes No-Profile Agent {uuid.uuid4().hex[:8]}",
            agent_type="executor",
            runtime_type="hermes",
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


async def test_dispatch_reply_to_sender_without_origin_fails(
    client: AsyncClient, dispatchable_agent
):
    """No sender to reply *to* -- the message is addressed to an agent but
    came from no registered one.

    The message needs `target_agent_id` for a reason unrelated to what is
    under test: since 2026-08-13 every incubation needs an owner, and with
    no registered sender the target is the only thing left to own it. Using
    a from_agent that resolves to nobody is the point here -- it is exactly
    what makes reply_to_sender impossible."""
    demand = await _create_demand(
        client,
        from_agent=f"nao-registrado-{uuid.uuid4().hex[:8]}",
        target_agent_id=str(dispatchable_agent),
    )
    try:
        resp = await client.post(
            f"/api/v1/demands/{demand['id']}/dispatch", json={"reply_to_sender": True}
        )
        assert resp.status_code == 400
    finally:
        await _delete_demand(demand["id"])


async def test_dispatch_unknown_agent_404s(client: AsyncClient, dispatchable_agent):
    # Backlog (Tipo default since 2026-07-28) needs a registered sender to
    # be dispatchable at all -- see _assert_dispatchable -- so this needs
    # a real from_agent_id to reach the target-agent lookup this test is
    # actually about, rather than 400ing on that guard first.
    demand = await _create_demand(client, from_agent_id=str(dispatchable_agent))
    try:
        resp = await client.post(
            f"/api/v1/demands/{demand['id']}/dispatch",
            json={"target_agent_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404
    finally:
        await _delete_demand(demand["id"])


async def test_dispatch_agent_without_runtime_type_rejected(
    client: AsyncClient, non_dispatchable_agent, dispatchable_agent
):
    # See test_dispatch_unknown_agent_404s -- Backlog needs a real sender
    # to clear _assert_dispatchable before reaching this test's own check.
    demand = await _create_demand(client, from_agent_id=str(dispatchable_agent))
    try:
        resp = await client.post(
            f"/api/v1/demands/{demand['id']}/dispatch",
            json={"target_agent_id": str(non_dispatchable_agent)},
        )
        assert resp.status_code == 409
    finally:
        await _delete_demand(demand["id"])


async def test_dispatch_hermes_agent_without_profile_rejected(
    client: AsyncClient, hermes_agent_without_profile, dispatchable_agent
):
    """A hermes agent with no profile_slug can't be dispatched -- host-bridge
    scopes the run with HERMES_HOME=/root/.hermes/profiles/<slug>, so there's
    nothing to run without one. Fails before ever reaching the host-bridge
    network call.

    Replaced test_dispatch_agent_without_credential_rejected (2026-07-25):
    that one asserted a missing ForgeRouter credential still 409s, which
    stopped being true when dispatch_agent_run made the credential optional
    (agents fall back to their CLI's own native auth -- see that function's
    docstring). Left as-is, the test not only failed, it *dispatched a real
    agent run to the host-bridge on every suite run*, since the guard it
    relied on to stop short of the network was exactly the one that was
    removed. A missing profile_slug is the AgentRunDispatchError path that's
    still real, so the 409 contract stays covered without spawning a CLI.

    See test_dispatch_unknown_agent_404s -- Backlog needs a real sender to
    clear _assert_dispatchable before reaching this test's own check."""
    demand = await _create_demand(client, from_agent_id=str(dispatchable_agent))
    try:
        resp = await client.post(
            f"/api/v1/demands/{demand['id']}/dispatch",
            json={"target_agent_id": str(hermes_agent_without_profile)},
        )
        assert resp.status_code == 409
    finally:
        await _delete_demand(demand["id"])


async def test_scheduled_at_locked_once_dispatched(client: AsyncClient, dispatchable_agent):
    """"Send at" is history on a message that already went out. The
    scheduled-send loop only picks up dispatch_status IS NULL, so rewriting
    the time can't re-send anything -- it would only falsify the record of
    when the message was actually sent."""
    demand = await _create_demand(client)
    try:
        resp = await client.patch(
            f"/api/v1/demands/{demand['id']}",
            json={"target_agent_id": str(dispatchable_agent), "scheduled_at": "2030-01-01T00:00:00Z"},
        )
        assert resp.status_code == 200, resp.text

        async with AsyncSessionLocal() as session:
            row = await session.get(AgentDemand, uuid.UUID(demand["id"]))
            row.dispatch_status = "completed"
            await session.commit()

        resp = await client.patch(
            f"/api/v1/demands/{demand['id']}", json={"scheduled_at": "2031-01-01T00:00:00Z"}
        )
        assert resp.status_code == 400, resp.text
        assert "already dispatched" in resp.json()["detail"]

        # Editar o resto continua livre -- só a data de envio congela.
        resp = await client.patch(f"/api/v1/demands/{demand['id']}", json={"subject": "novo assunto"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["subject"] == "novo assunto"
    finally:
        await _delete_demand(demand["id"])


async def test_dispatch_status_requires_dispatch_first(client: AsyncClient):
    demand = await _create_demand(client)
    try:
        resp = await client.get(f"/api/v1/demands/{demand['id']}/dispatch-status")
        assert resp.status_code == 400
    finally:
        await _delete_demand(demand["id"])

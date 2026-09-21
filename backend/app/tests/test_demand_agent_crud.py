"""The MCP's write surface for a message's own sender (2026-08-15).

The read tools (list_agent_messages/get_agent_message/check_agent_inbox)
were already agent-parameterized for any agent, but there was no way for
an agent to edit or archive its own mail except the human-only JWT API.
These two routes close that gap, bridge-token only, scoped to the
message's own sender.

Also guards the auth boundary itself: these are dynamic-segment routes
(`/{demand_id}/agent`, `/{demand_id}/agent-archive`), which
`_PUBLIC_API_PATHS` can't cover (exact-match only) -- they need the
`demands_bridge_action` carve-out in main.py's `RequireAuthMiddleware`.
Without it, a caller sending only `X-Bridge-Token` (no `Authorization`
header at all, exactly what the forgehub MCP does) gets a 401
before the route's own bridge-token check ever runs -- which is exactly
what `receive_incubation`/`drop_incubation`/`reprocess_demand` had been
silently suffering since they were written, unnoticed because every test
of them also carried a JWT. `client_bridge_only` below carries no JWT at
all, on purpose, to catch a regression of that gap.
"""
import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand


@pytest_asyncio.fixture
async def client_bridge_only():
    """No Authorization header at all -- the real shape of an MCP call."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def pair():
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        sender = Agent(
            name=f"CRUD Sender {suffix}", agent_type="executor",
            runtime_type="claude", profile_slug=f"crud-sender-{suffix}",
        )
        stranger = Agent(
            name=f"CRUD Stranger {suffix}", agent_type="executor",
            runtime_type="claude", profile_slug=f"crud-stranger-{suffix}",
        )
        session.add_all([sender, stranger])
        await session.commit()
        data = {
            "sender_id": sender.id, "sender_slug": sender.profile_slug,
            "stranger_id": stranger.id, "stranger_slug": stranger.profile_slug,
        }

    yield data

    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(AgentDemand).where(
                AgentDemand.from_agent_id.in_([data["sender_id"], data["stranger_id"]])
            )
        )
        await session.execute(
            delete(Agent).where(Agent.id.in_([data["sender_id"], data["stranger_id"]]))
        )
        await session.commit()


def _bridge_headers() -> dict[str, str]:
    return {"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN or ""}


async def _send(pair) -> uuid.UUID:
    async with AsyncSessionLocal() as session:
        demand = AgentDemand(
            from_agent=pair["sender_slug"],
            from_agent_id=pair["sender_id"],
            subject="rascunho original",
            body="corpo original",
            origin_type="incubation",
        )
        session.add(demand)
        await session.commit()
        return demand.id


async def test_sender_edits_its_own_message_via_bridge_token_alone(client_bridge_only: AsyncClient, pair):
    demand_id = await _send(pair)
    response = await client_bridge_only.patch(
        f"/api/v1/demands/{demand_id}/agent",
        json={"agent": pair["sender_slug"], "subject": "assunto revisado"},
        headers=_bridge_headers(),
    )
    assert response.status_code == 200, response.text
    assert response.json()["subject"] == "assunto revisado"


async def test_stranger_cannot_edit_someone_elses_message(client_bridge_only: AsyncClient, pair):
    demand_id = await _send(pair)
    response = await client_bridge_only.patch(
        f"/api/v1/demands/{demand_id}/agent",
        json={"agent": pair["stranger_slug"], "subject": "sequestro"},
        headers=_bridge_headers(),
    )
    assert response.status_code == 403


async def test_bridge_token_alone_without_any_token_at_all_is_rejected(client_bridge_only: AsyncClient, pair):
    demand_id = await _send(pair)
    response = await client_bridge_only.patch(
        f"/api/v1/demands/{demand_id}/agent",
        json={"agent": pair["sender_slug"], "subject": "sem token"},
    )
    assert response.status_code == 401


async def test_sender_archives_its_own_message_via_bridge_token_alone(client_bridge_only: AsyncClient, pair):
    demand_id = await _send(pair)
    response = await client_bridge_only.post(
        f"/api/v1/demands/{demand_id}/agent-archive",
        params={"agent": pair["sender_slug"]},
        headers=_bridge_headers(),
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "archived"


async def test_stranger_cannot_archive_someone_elses_message(client_bridge_only: AsyncClient, pair):
    demand_id = await _send(pair)
    response = await client_bridge_only.post(
        f"/api/v1/demands/{demand_id}/agent-archive",
        params={"agent": pair["stranger_slug"]},
        headers=_bridge_headers(),
    )
    assert response.status_code == 403

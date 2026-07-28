"""Tests for GET /api/v1/demands/for-agent — an agent listing its own
messages by status without consuming them.

The distinction from /pending is the whole point of this endpoint and is what
these tests protect: /pending is a queue (reading stamps agent_processed_at
and the message never comes back), so it cannot answer "what is the state of
my messages" without destroying the answer. Every filter test therefore also
asserts nothing was consumed.

DB strategy: own rows, UUID-suffixed, deleted in fixture teardown — same
pattern as test_demand_dispatch.py.
"""
import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand

BRIDGE = "/api/v1/demands/for-agent"


def _bridge_headers() -> dict[str, str]:
    return {"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN}


@pytest_asyncio.fixture
async def client():
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def scenario():
    """Two agents and four messages covering both status axes and both
    directions, so one fixture exercises every filter."""
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        sender = Agent(
            name=f"ForAgent Sender {suffix}",
            agent_type="executor",
            runtime_type="claude",
            profile_slug=f"for-agent-sender-{suffix}",
        )
        other = Agent(
            name=f"ForAgent Other {suffix}",
            agent_type="executor",
            runtime_type="claude",
            profile_slug=f"for-agent-other-{suffix}",
        )
        session.add_all([sender, other])
        await session.flush()

        rows = [
            # outgoing, dispatched and finished
            AgentDemand(
                from_agent=sender.profile_slug,
                subject=f"outgoing completed {suffix}",
                body="ran",
                from_agent_id=sender.id,
                target_agent_id=other.id,
                dispatch_status="completed",
                status="new",
            ),
            # outgoing, dispatch blew up
            AgentDemand(
                from_agent=sender.profile_slug,
                subject=f"outgoing failed {suffix}",
                body="broke",
                from_agent_id=sender.id,
                target_agent_id=other.id,
                dispatch_status="failed",
                status="read",
            ),
            # outgoing plain note: never dispatched, no target
            AgentDemand(
                from_agent=sender.profile_slug,
                subject=f"outgoing note {suffix}",
                body="just a note",
                from_agent_id=sender.id,
                status="new",
            ),
            # incoming, unread and unconsumed
            AgentDemand(
                from_agent=other.profile_slug,
                subject=f"incoming {suffix}",
                body="for you",
                from_agent_id=other.id,
                target_agent_id=sender.id,
                status="new",
            ),
        ]
        session.add_all(rows)
        await session.commit()
        data = {
            "slug": sender.profile_slug,
            "other_slug": other.profile_slug,
            "sender_id": sender.id,
            "other_id": other.id,
            "numbers": {row.subject.split()[1]: row.number for row in rows},
        }

    yield data

    async with AsyncSessionLocal() as session:
        # Rows are created through the session, not the route, so no
        # Notification is ever emitted for them (create_demand_and_notify is
        # the only writer) -- nothing to clean up there.
        await session.execute(
            delete(AgentDemand).where(
                AgentDemand.from_agent_id.in_([data["sender_id"], data["other_id"]])
            )
        )
        await session.execute(
            delete(Agent).where(Agent.id.in_([data["sender_id"], data["other_id"]]))
        )
        await session.commit()


async def _subjects(client: AsyncClient, **params) -> list[str]:
    response = await client.get(BRIDGE, params=params, headers=_bridge_headers())
    assert response.status_code == 200, response.text
    return [item["subject"] for item in response.json()]


async def test_lists_both_directions_by_default(client: AsyncClient, scenario):
    subjects = await _subjects(client, agent=scenario["slug"])
    assert len(subjects) == 4
    # Newest first.
    assert subjects[0].startswith("incoming")


async def test_filter_by_dispatch_status(client: AsyncClient, scenario):
    subjects = await _subjects(client, agent=scenario["slug"], dispatch_status="completed")
    assert [s.split()[1] for s in subjects] == ["completed"]

    subjects = await _subjects(client, agent=scenario["slug"], dispatch_status="failed")
    assert [s.split()[1] for s in subjects] == ["failed"]


async def test_dispatch_status_none_means_never_dispatched(client: AsyncClient, scenario):
    """NULL is a real state (a plain note, or one still waiting on a target),
    so it needs a spelling of its own rather than being "no filter"."""
    subjects = await _subjects(client, agent=scenario["slug"], dispatch_status="none")
    assert sorted(s.split()[0] for s in subjects) == ["incoming", "outgoing"]


async def test_filter_by_read_status(client: AsyncClient, scenario):
    subjects = await _subjects(client, agent=scenario["slug"], status_filter="read")
    assert [s.split()[1] for s in subjects] == ["failed"]


async def test_direction_filters(client: AsyncClient, scenario):
    outgoing = await _subjects(client, agent=scenario["slug"], direction="outgoing")
    assert len(outgoing) == 3
    assert all(s.startswith("outgoing") for s in outgoing)

    incoming = await _subjects(client, agent=scenario["slug"], direction="incoming")
    assert [s.split()[0] for s in incoming] == ["incoming"]


async def test_number_filter_returns_one(client: AsyncClient, scenario):
    number = scenario["numbers"]["completed"]
    subjects = await _subjects(client, agent=scenario["slug"], number=number)
    assert [s.split()[1] for s in subjects] == ["completed"]


async def test_listing_does_not_consume_pending_mail(client: AsyncClient, scenario):
    """The guarantee that separates this from /pending: after any number of
    listings, the incoming message is still undelivered."""
    await _subjects(client, agent=scenario["slug"])
    await _subjects(client, agent=scenario["slug"], direction="incoming")

    async with AsyncSessionLocal() as session:
        processed = (
            await session.execute(
                select(AgentDemand.agent_processed_at).where(
                    AgentDemand.target_agent_id == scenario["sender_id"]
                )
            )
        ).scalars().all()
    assert processed == [None]


async def test_other_agents_messages_are_not_visible(client: AsyncClient, scenario):
    """Scoped to the named agent: a message between two third parties must not
    leak in just because the caller holds the shared bridge token."""
    subjects = await _subjects(client, agent=scenario["other_slug"], direction="incoming")
    assert all(s.startswith("outgoing") for s in subjects)


async def test_limit_is_clamped_not_rejected(client: AsyncClient, scenario):
    subjects = await _subjects(client, agent=scenario["slug"], limit=1)
    assert len(subjects) == 1


async def test_invalid_filters_are_rejected(client: AsyncClient, scenario):
    for params in (
        {"agent": scenario["slug"], "status_filter": "nope"},
        {"agent": scenario["slug"], "dispatch_status": "nope"},
        {"agent": scenario["slug"], "direction": "sideways"},
    ):
        response = await client.get(BRIDGE, params=params, headers=_bridge_headers())
        assert response.status_code == 400, response.text


async def test_unknown_agent_404s(client: AsyncClient):
    response = await client.get(
        BRIDGE, params={"agent": "no-such-agent-slug"}, headers=_bridge_headers()
    )
    assert response.status_code == 404


async def test_bridge_token_required(client: AsyncClient, scenario):
    response = await client.get(BRIDGE, params={"agent": scenario["slug"]})
    assert response.status_code == 401

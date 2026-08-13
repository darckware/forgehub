"""The owning agent's decision surface: receive an incubated thought or drop it.

These two routes are what closes the loop the maturation sweep opens
(2026-08-13). Without them an agent handed a "decide this" has no way to
answer, and the item goes back to sitting parked -- the exact failure the
incubation redesign exists to remove.

What they protect:
  - only the owner decides (another agent gets 403, not a silent no-op);
  - a decision is final (deciding twice is 409, not a second state change);
  - a drop always carries a reason and never deletes the row;
  - receiving needs both agents, since the result is a Task.
"""
import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.config import settings
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
        headers={"Authorization": f"Bearer {create_access_token('test-incubation')}"},
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def pair():
    """An owner agent and a stranger, plus cleanup of anything they own."""
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        owner = Agent(
            name=f"Incubation Owner {suffix}", agent_type="executor",
            runtime_type="claude", profile_slug=f"incub-owner-{suffix}",
        )
        stranger = Agent(
            name=f"Incubation Stranger {suffix}", agent_type="executor",
            runtime_type="claude", profile_slug=f"incub-stranger-{suffix}",
        )
        session.add_all([owner, stranger])
        await session.commit()
        data = {
            "owner_id": owner.id, "owner_slug": owner.profile_slug,
            "stranger_id": stranger.id, "stranger_slug": stranger.profile_slug,
        }

    yield data

    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(AgentDemand).where(
                AgentDemand.incubation_owner_id.in_([data["owner_id"], data["stranger_id"]])
            )
        )
        await session.execute(
            delete(AgentDemand).where(
                AgentDemand.target_agent_id.in_([data["owner_id"], data["stranger_id"]])
            )
        )
        await session.execute(
            delete(Agent).where(Agent.id.in_([data["owner_id"], data["stranger_id"]]))
        )
        await session.commit()


def _bridge_headers() -> dict[str, str]:
    return {"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN or ""}


async def _incubate(pair, *, with_sender: bool = True) -> uuid.UUID:
    """An incubation owned by `owner`, optionally with a registered sender
    (needed only when the test goes on to receive it)."""
    async with AsyncSessionLocal() as session:
        demand = AgentDemand(
            from_agent=pair["stranger_slug"] if with_sender else "ninguem",
            from_agent_id=pair["stranger_id"] if with_sender else None,
            target_agent_id=pair["owner_id"],
            subject=f"pensamento {uuid.uuid4().hex[:6]}",
            body="vale a pena?",
            origin_type="incubation",
        )
        session.add(demand)
        await session.commit()
        return demand.id


async def test_owner_receives_thought_and_it_becomes_a_task(client: AsyncClient, pair):
    demand_id = await _incubate(pair)
    response = await client.post(
        f"/api/v1/demands/{demand_id}/incubation:receive",
        params={"agent": pair["owner_slug"]},
        headers=_bridge_headers(),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["origin_type"] == "task"
    # The incubation fields stop applying once it is work.
    assert body["incubation_state"] is None
    assert body["incubation_owner_id"] is None
    assert body["matures_at"] is None
    # A received thought is work that should actually run.
    assert body["scheduled_at"] is not None


async def test_owner_drops_thought_with_reason_and_row_survives(client: AsyncClient, pair):
    demand_id = await _incubate(pair)
    response = await client.post(
        f"/api/v1/demands/{demand_id}/incubation:drop",
        params={"agent": pair["owner_slug"], "reason": "já resolvido em outro lugar"},
        headers=_bridge_headers(),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["incubation_state"] == "dropped"
    assert body["drop_reason"] == "já resolvido em outro lugar"
    assert body["status"] == "archived"

    # Never a DELETE -- the record that this was considered and declined is
    # the only way to notice an agent discarding what mattered.
    async with AsyncSessionLocal() as session:
        assert await session.get(AgentDemand, demand_id) is not None


async def test_a_drop_without_a_reason_is_refused(client: AsyncClient, pair):
    demand_id = await _incubate(pair)
    response = await client.post(
        f"/api/v1/demands/{demand_id}/incubation:drop",
        params={"agent": pair["owner_slug"], "reason": "   "},
        headers=_bridge_headers(),
    )
    assert response.status_code == 400, response.text


async def test_another_agent_cannot_decide_someone_elses_thought(client: AsyncClient, pair):
    demand_id = await _incubate(pair)
    response = await client.post(
        f"/api/v1/demands/{demand_id}/incubation:receive",
        params={"agent": pair["stranger_slug"]},
        headers=_bridge_headers(),
    )
    assert response.status_code == 403, response.text
    assert "owning agent" in response.json()["detail"]


async def test_deciding_twice_is_refused(client: AsyncClient, pair):
    demand_id = await _incubate(pair)
    first = await client.post(
        f"/api/v1/demands/{demand_id}/incubation:drop",
        params={"agent": pair["owner_slug"], "reason": "não agora"},
        headers=_bridge_headers(),
    )
    assert first.status_code == 200, first.text
    second = await client.post(
        f"/api/v1/demands/{demand_id}/incubation:drop",
        params={"agent": pair["owner_slug"], "reason": "de novo"},
        headers=_bridge_headers(),
    )
    assert second.status_code == 409, second.text


async def test_receiving_without_a_sender_is_refused(client: AsyncClient, pair):
    """A Task needs both agents (2026-07-28). Refused with an explanation
    rather than promoted into a Task nobody can run."""
    demand_id = await _incubate(pair, with_sender=False)
    response = await client.post(
        f"/api/v1/demands/{demand_id}/incubation:receive",
        params={"agent": pair["owner_slug"]},
        headers=_bridge_headers(),
    )
    assert response.status_code == 400, response.text

    async with AsyncSessionLocal() as session:
        still = await session.get(AgentDemand, demand_id)
        assert still.origin_type == "incubation"  # unchanged, not half-promoted


async def test_owner_lists_only_what_it_owns(client: AsyncClient, pair):
    await _incubate(pair)
    response = await client.get(
        "/api/v1/demands/for-agent",
        params={
            "agent": pair["owner_slug"],
            "origin_type": "incubation",
            "owned_only": True,
        },
        headers=_bridge_headers(),
    )
    assert response.status_code == 200, response.text
    items = response.json()
    assert items and all(i["incubation_owner_id"] == str(pair["owner_id"]) for i in items)

    # The sender sees it in its own outgoing, but does not *own* it.
    stranger_view = await client.get(
        "/api/v1/demands/for-agent",
        params={
            "agent": pair["stranger_slug"],
            "origin_type": "incubation",
            "owned_only": True,
        },
        headers=_bridge_headers(),
    )
    assert stranger_view.status_code == 200, stranger_view.text
    assert stranger_view.json() == []

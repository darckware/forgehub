"""The maturation sweep: what turns `matures_at` from a column into a promise.

Invariant 3 says every incubation has a deadline and the system hands the
decision over when it passes. Without this pass the deadline is decorative
and a thought still waits to be remembered -- the failure the redesign
exists to remove (#8971 sat parked for four days, unnoticed).

Delivery works by clearing `agent_processed_at`, putting the item back into
the pull queue agents already read from their own cron loop, rather than
spawning an agent run to ask a question or creating a second message that
would itself need an owner and a deadline.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest_asyncio
from sqlalchemy import delete, select

from app.api.routes.demand import run_incubation_maturation_pass
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand
from app.db.models.notification import Notification


@pytest_asyncio.fixture
async def owner():
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        agent = Agent(
            name=f"Maturation Owner {suffix}", agent_type="executor",
            runtime_type="claude", profile_slug=f"matur-owner-{suffix}",
        )
        session.add(agent)
        await session.commit()
        agent_id = agent.id

    yield agent_id

    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(AgentDemand.id).where(AgentDemand.incubation_owner_id == agent_id)
            )
        ).scalars().all()
        for demand_id in rows:
            await session.execute(
                delete(Notification).where(Notification.event_key == f"incubation-due:{demand_id}")
            )
        await session.execute(delete(AgentDemand).where(AgentDemand.incubation_owner_id == agent_id))
        await session.execute(delete(Agent).where(Agent.id == agent_id))
        await session.commit()


async def _incubate(
    owner_id, *, matures_in: timedelta, state: str = "incubating", drop_reason: str | None = None
) -> uuid.UUID:
    async with AsyncSessionLocal() as session:
        demand = AgentDemand(
            from_agent="tester",
            target_agent_id=owner_id,
            subject=f"pensamento {uuid.uuid4().hex[:6]}",
            body="decidir depois",
            origin_type="incubation",
            incubation_owner_id=owner_id,
            incubation_state=state,
            drop_reason=drop_reason,
            matures_at=datetime.now(timezone.utc) + matures_in,
            # Pretend the agent already took delivery once, so the sweep
            # clearing this is observable rather than a no-op.
            agent_processed_at=datetime.now(timezone.utc),
        )
        session.add(demand)
        await session.commit()
        return demand.id


async def test_matured_thought_is_handed_to_its_owner(owner):
    demand_id = await _incubate(owner, matures_in=timedelta(minutes=-1))

    async with AsyncSessionLocal() as session:
        assert await run_incubation_maturation_pass(session) >= 1

    async with AsyncSessionLocal() as session:
        demand = await session.get(AgentDemand, demand_id)
        assert demand.incubation_state == "decision_pending"
        # Back in the pull queue the agent's own cron already reads.
        assert demand.agent_processed_at is None
        # matures_at stays as the record of when it was due.
        assert demand.matures_at is not None


async def test_a_thought_still_incubating_is_left_alone(owner):
    demand_id = await _incubate(owner, matures_in=timedelta(days=2))

    async with AsyncSessionLocal() as session:
        await run_incubation_maturation_pass(session)

    async with AsyncSessionLocal() as session:
        demand = await session.get(AgentDemand, demand_id)
        assert demand.incubation_state == "incubating"
        assert demand.agent_processed_at is not None  # delivery untouched


async def test_the_human_is_notified_once_per_thought(owner):
    demand_id = await _incubate(owner, matures_in=timedelta(minutes=-1))

    async with AsyncSessionLocal() as session:
        await run_incubation_maturation_pass(session)
    # A second pass must not duplicate the notification, nor re-hand the item.
    async with AsyncSessionLocal() as session:
        assert await run_incubation_maturation_pass(session) == 0

    async with AsyncSessionLocal() as session:
        notes = (
            await session.execute(
                select(Notification).where(
                    Notification.event_key == f"incubation-due:{demand_id}"
                )
            )
        ).scalars().all()
        assert len(notes) == 1
        assert notes[0].severity == "warning"


async def test_an_already_decided_thought_is_never_reopened(owner):
    """A dropped thought whose deadline has passed stays dropped -- the sweep
    keys off state, not time, so a decision is final."""
    # drop_reason at creation, not after: the constraint refuses a dropped
    # row without one, which is invariant 2 doing its job.
    demand_id = await _incubate(
        owner, matures_in=timedelta(days=-5), state="dropped", drop_reason="não vale a pena"
    )

    async with AsyncSessionLocal() as session:
        await run_incubation_maturation_pass(session)

    async with AsyncSessionLocal() as session:
        demand = await session.get(AgentDemand, demand_id)
        assert demand.incubation_state == "dropped"

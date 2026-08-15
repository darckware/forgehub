"""60-day retention sweep for terminal mail (2026-08-15, Marcelo: "as
messages precisam ter um plano de limpeza podendo ficar até 60 dias").

What it protects:
  - only terminal mail (completed/failed) past DEMAND_RETENTION_DAYS is
    touched -- an open thread never ages out just because nobody looked;
  - it archives, never deletes -- the record survives;
  - a row still inside the window is left alone, whatever its state.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest_asyncio
from sqlalchemy import delete, select, update

from app.api.routes.demand import run_demand_retention_sweep
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.demand import DEMAND_RETENTION_DAYS, AgentDemand


@pytest_asyncio.fixture
async def agent():
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        a = Agent(
            name=f"Retention {suffix}", agent_type="executor",
            runtime_type="claude", profile_slug=f"retention-{suffix}",
        )
        session.add(a)
        await session.commit()
        agent_id = a.id

    yield agent_id

    async with AsyncSessionLocal() as session:
        await session.execute(delete(AgentDemand).where(AgentDemand.target_agent_id == agent_id))
        await session.execute(delete(Agent).where(Agent.id == agent_id))
        await session.commit()


async def _demand(agent_id, *, dispatch_status: str, age_days: int) -> uuid.UUID:
    async with AsyncSessionLocal() as session:
        d = AgentDemand(
            from_agent="tester",
            from_agent_id=agent_id,
            target_agent_id=agent_id,
            subject=f"retenção {uuid.uuid4().hex[:6]}",
            body="conteúdo",
            origin_type="task",
            dispatch_status=dispatch_status,
        )
        session.add(d)
        await session.commit()
        demand_id = d.id
        # Backdate updated_at (Core-level UPDATE, bypasses the ORM's
        # own onupdate=func.now() default) to simulate mail that became
        # terminal `age_days` ago.
        await session.execute(
            update(AgentDemand)
            .where(AgentDemand.id == demand_id)
            .values(updated_at=datetime.now(timezone.utc) - timedelta(days=age_days))
        )
        await session.commit()
        return demand_id


async def test_archives_terminal_mail_past_the_window(agent):
    old_completed = await _demand(agent, dispatch_status="completed", age_days=DEMAND_RETENTION_DAYS + 1)
    old_failed = await _demand(agent, dispatch_status="failed", age_days=DEMAND_RETENTION_DAYS + 5)

    async with AsyncSessionLocal() as db:
        archived = await run_demand_retention_sweep(db)

    assert archived == 2
    async with AsyncSessionLocal() as session:
        statuses = (
            await session.execute(
                select(AgentDemand.status).where(AgentDemand.id.in_([old_completed, old_failed]))
            )
        ).scalars().all()
    assert set(statuses) == {"archived"}


async def test_leaves_recent_terminal_mail_alone(agent):
    recent = await _demand(agent, dispatch_status="completed", age_days=DEMAND_RETENTION_DAYS - 1)

    async with AsyncSessionLocal() as db:
        await run_demand_retention_sweep(db)

    async with AsyncSessionLocal() as session:
        status = (
            await session.execute(select(AgentDemand.status).where(AgentDemand.id == recent))
        ).scalar_one()
    assert status != "archived"


async def test_never_touches_active_mail_no_matter_how_old(agent):
    stale_running = await _demand(agent, dispatch_status="running", age_days=DEMAND_RETENTION_DAYS + 30)

    async with AsyncSessionLocal() as db:
        await run_demand_retention_sweep(db)

    async with AsyncSessionLocal() as session:
        status = (
            await session.execute(select(AgentDemand.status).where(AgentDemand.id == stale_running))
        ).scalar_one()
    assert status != "archived"

# ruff: noqa: F811
"""Executor substitution respects the registered contract and source boundaries."""
import pytest
from sqlalchemy import update

from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.tests.test_agent_failover import world  # noqa: F401


@pytest.mark.asyncio
@pytest.mark.parametrize("case, expected", [
    ("role", "EXECUTOR_ROLE_MISMATCH"),
    ("unknown", "EXECUTOR_CONTRACT_UNKNOWN"),
    ("private", "PRIVATE_CONTEXT_BOUND"),
    ("fixed", "EXECUTOR_BOUND"),
    ("approval", "EXECUTOR_BOUND"),
])
async def test_available_candidate_is_not_automatically_eligible(world, case, expected):
    from app.core.agent_failover import executor_eligibility
    fields = {"fixed_agent": True} if case == "fixed" else (
        {"requires_approval": True} if case == "approval" else
        {"channel": "whatsapp_group"} if case == "private" else {})
    row = await world.message(world.limited, **fields)
    async with AsyncSessionLocal() as db:
        await db.execute(update(Agent).where(Agent.id == world.limited.id).values(
            default_role=None if case == "unknown" else "developer"))
        await db.execute(update(Agent).where(Agent.id == world.free.id).values(
            default_role="reviewer" if case == "role" else "developer"))
        await db.commit()
        reasons = await executor_eligibility(db, row, world.free.id)
    assert expected in {r["code"] for r in reasons}

"""Shared fixtures for the API test suite.

main.py's RequireAuthMiddleware guards every /api/v1/* route with a bearer
token (it validates the JWT itself, not a user row), so every test client
must send one. Domain test files keep their own `client` fixture (some add
extra setup) and take `auth_headers` from here to build it.
"""
import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent

# The free-text `from_agent` most demand tests post with. create_demand
# auto-resolves it to a real Agent row by profile_slug (_find_agent_by_slug),
# which is what gives those messages an owner.
TEST_SUITE_SLUG = "test-suite"


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('test-suite')}"}


@pytest_asyncio.fixture(autouse=True)
async def test_suite_agent():
    """Registers the `test-suite` agent for the whole session.

    Since 2026-08-13 a message with no Tipo defaults to incubation, and an
    incubation must have an owning agent (invariant 1) -- a message from
    nobody, to nobody, has no one to ever decide its fate. Most demand tests
    post `from_agent: "test-suite"` as free text, which resolved to no Agent
    and so had no owner to fall back on.

    Registering the slug rather than rewriting every test keeps those tests
    exercising what they were written for (conversion, attachments, groups,
    dispatch) instead of turning each into an incidental agent-plumbing
    test. Idempotent: reuses the row if a previous run left one behind, and
    only deletes what it created."""
    async with AsyncSessionLocal() as session:
        existing = (
            await session.execute(select(Agent).where(Agent.profile_slug == TEST_SUITE_SLUG))
        ).scalar_one_or_none()
        if existing is not None:
            yield existing.id
            return
        agent = Agent(
            name="Test Suite",
            agent_type="executor",
            runtime_type="claude",
            profile_slug=TEST_SUITE_SLUG,
        )
        session.add(agent)
        await session.commit()
        agent_id = agent.id

    yield agent_id

    async with AsyncSessionLocal() as session:
        await session.execute(delete(Agent).where(Agent.id == agent_id))
        await session.commit()

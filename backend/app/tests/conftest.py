"""Shared fixtures for the API test suite.

main.py's RequireAuthMiddleware guards every /api/v1/* route with a bearer
token (it validates the JWT itself, not a user row), so every test client
must send one. Domain test files keep their own `client` fixture (some add
extra setup) and take `auth_headers` from here to build it.
"""
import pytest
import pytest_asyncio
from sqlalchemy import delete, select, text

from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent

# The free-text `from_agent` most demand tests post with. create_demand
# auto-resolves it to a real Agent row by profile_slug (_find_agent_by_slug),
# which is what gives those messages an owner.
TEST_SUITE_SLUG = "test-suite"

# Exact signatures owned by automated fixtures. A killed pytest process can
# skip yield-fixture teardown; cleaning these at the next session boundary
# prevents those records from remaining in the operational roster forever.
_STALE_AGENT_FIXTURE_PREDICATE = """
    profile_slug = 'test-suite'
    OR profile_slug LIKE 'channel-test-a-%'
    OR profile_slug LIKE 'channel-test-b-%'
    OR profile_slug LIKE 'chat-group-test-%'
    OR profile_slug LIKE 'fb-%'
"""


async def _cleanup_stale_agent_fixtures() -> None:
    async with AsyncSessionLocal() as session:
        fixture_ids = text(
            f"SELECT id FROM company.agents WHERE {_STALE_AGENT_FIXTURE_PREDICATE}"
        )
        session_ids = text(
            f"SELECT id FROM company.chat_sessions WHERE agent_id IN ({fixture_ids.text})"
        )
        await session.execute(
            text(f"DELETE FROM company.chat_artifacts WHERE session_id IN ({session_ids.text})")
        )
        await session.execute(
            text(f"DELETE FROM company.chat_messages WHERE session_id IN ({session_ids.text})")
        )
        await session.execute(
            text(f"DELETE FROM company.chat_session_participants WHERE session_id IN ({session_ids.text})")
        )
        await session.execute(
            text(f"DELETE FROM company.chat_sessions WHERE id IN ({session_ids.text})")
        )
        await session.execute(
            text(f"DELETE FROM company.responsibility_areas WHERE owner_agent_id IN ({fixture_ids.text})")
        )
        await session.execute(
            text(f"DELETE FROM company.task_assignments WHERE agent_id IN ({fixture_ids.text})")
        )
        await session.execute(
            text(f"DELETE FROM company.agents WHERE id IN ({fixture_ids.text})")
        )
        await session.commit()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def clean_stale_agent_fixtures():
    await _cleanup_stale_agent_fixtures()
    yield
    await _cleanup_stale_agent_fixtures()


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

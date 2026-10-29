"""Shared fixtures for the API test suite.

main.py's RequireAuthMiddleware guards every /api/v1/* route with a bearer
token (it validates the JWT itself, not a user row), so every test client
must send one. Domain test files keep their own `client` fixture (some add
extra setup) and take `auth_headers` from here to build it.

The suite only ever runs against the isolated test Postgres (test-env/,
Plano Integrado T.1). The guard below runs while this file is imported --
before app.db.base exists and before any fixture -- and ends the whole
session unless ENVIRONMENT=test and the target is on the test allowlist.
Run it as `ENVIRONMENT=test pytest` (see CLAUDE.md, Backend tests).
"""
import uuid

import pytest


def _abort_unless_test_database() -> None:
    try:
        from app.core.config import (
            assert_test_database_target,
            is_test_environment,
            settings,
        )
    except Exception as exc:  # Settings itself refused the target
        pytest.exit(f"Test database guard: {exc}", returncode=4)
    if not is_test_environment(settings.ENVIRONMENT):
        pytest.exit(
            "Test database guard: the suite runs only with ENVIRONMENT=test "
            f"(got {settings.ENVIRONMENT!r}); it never runs against production.",
            returncode=4,
        )
    try:
        assert_test_database_target(
            settings.POSTGRES_HOST, settings.POSTGRES_PORT, settings.POSTGRES_DB, settings.POSTGRES_USER
        )
    except Exception as exc:
        pytest.exit(f"Test database guard: {exc}", returncode=4)


_abort_unless_test_database()

import pytest_asyncio  # noqa: E402
from sqlalchemy import delete, select, text  # noqa: E402

from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db.base import AsyncSessionLocal  # noqa: E402
from app.db.models.agent import Agent  # noqa: E402
from app.db.models.user import User  # noqa: E402

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


@pytest_asyncio.fixture
async def admin_headers():
    """Bearer headers for a throwaway admin created for this test and
    deleted afterwards. Routes behind get_current_admin look the token's
    subject up in `users` (active + is_admin), so an arbitrary subject like
    auth_headers' won't pass -- and borrowing a seeded user ('admin', or
    "the first admin") made tests pass or 401 depending on whether that row
    was still active, which is how 10 system_control tests broke once the
    seeded 'admin' account was deactivated."""
    username = f"test-admin-{uuid.uuid4().hex[:12]}"
    async with AsyncSessionLocal() as db:
        db.add(User(username=username, hashed_password=hash_password(uuid.uuid4().hex), is_admin=True))
        await db.commit()
    yield {"Authorization": f"Bearer {create_access_token(username)}"}
    async with AsyncSessionLocal() as db:
        await db.execute(delete(User).where(User.username == username))
        await db.commit()


@pytest_asyncio.fixture
async def restore_hermes_agent_statuses():
    """Protect the operational roster from sync tests that replace the
    canonical registry with a deliberately tiny fake registry."""
    async with AsyncSessionLocal() as session:
        rows = list((await session.execute(
            select(Agent).where(Agent.runtime_type == "hermes")
        )).scalars())
        snapshot = {row.id: (row.status, row.is_active) for row in rows}

    yield

    async with AsyncSessionLocal() as session:
        rows = list((await session.execute(
            select(Agent).where(Agent.id.in_(snapshot))
        )).scalars())
        for row in rows:
            row.status, row.is_active = snapshot[row.id]
        await session.commit()


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


@pytest.fixture
def bind_evidence_bridge(monkeypatch):
    """Binds core/evidence_bridge.py to the real host-bridge evidence router
    (host-bridge/evidence_probe.py, M0.6a) in process, accepting only the
    given roots -- file/git evidence is then checked for real against
    temporary folders and repositories. Only the transport is replaced; the
    running integration stub doesn't know a test's tmp_path."""
    import sys
    from pathlib import Path

    import httpx
    from fastapi import FastAPI, HTTPException

    from app.core import evidence_bridge
    from app.core.config import settings

    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "host-bridge"))
    import evidence_probe

    real_client = httpx.AsyncClient

    def bind(*roots) -> None:
        def check(token):
            if token != settings.CHAT_BRIDGE_TOKEN:
                raise HTTPException(status_code=401)

        bridge_app = FastAPI()
        bridge_app.include_router(evidence_probe.make_evidence_router(check, roots=tuple(str(r) for r in roots)))
        monkeypatch.setattr(
            evidence_bridge, "_client",
            lambda: real_client(transport=httpx.ASGITransport(app=bridge_app), timeout=20),
        )

    return bind

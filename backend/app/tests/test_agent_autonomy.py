"""Agent.autonomous_runs: dispatched runs without permission prompts.

Only an admin may change it (it lets a run act with no approval at all); a
PATCH that doesn't touch it keeps working for any authenticated caller.
"""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.security import create_access_token, hash_password
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.user import User
from app.main import app


@pytest_asyncio.fixture
async def non_admin_headers():
    """A real, active, non-admin user: `auth_headers`' "test-suite" subject
    is promoted to admin for the whole session by test_agent.py and
    test_server_key_vault.py, so it can't stand in for a non-admin here."""
    username = f"test-user-{uuid.uuid4().hex[:12]}"
    async with AsyncSessionLocal() as db:
        db.add(User(username=username, hashed_password=hash_password(uuid.uuid4().hex), is_admin=False))
        await db.commit()
    yield {"Authorization": f"Bearer {create_access_token(username)}"}
    async with AsyncSessionLocal() as db:
        await db.execute(delete(User).where(User.username == username))
        await db.commit()


@pytest_asyncio.fixture
async def agent_id():
    async with AsyncSessionLocal() as db:
        agent = Agent(name=f"autonomy-test-{uuid.uuid4().hex[:8]}", runtime_type="agy", status="inactive", is_active=False)
        db.add(agent)
        await db.commit()
        created = agent.id
    yield created
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Agent).where(Agent.id == created))
        await db.commit()


@pytest.mark.asyncio
async def test_new_agent_is_not_autonomous(agent_id, admin_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=admin_headers) as client:
        response = await client.get(f"/api/v1/agents/{agent_id}")
    assert response.status_code == 200
    assert response.json()["autonomous_runs"] is False


@pytest.mark.asyncio
async def test_only_an_admin_turns_autonomy_on(agent_id, non_admin_headers, admin_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        refused = await client.patch(
            f"/api/v1/agents/{agent_id}", json={"autonomous_runs": True}, headers=non_admin_headers
        )
        allowed = await client.patch(
            f"/api/v1/agents/{agent_id}", json={"autonomous_runs": True}, headers=admin_headers
        )
    assert refused.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json()["autonomous_runs"] is True


@pytest.mark.asyncio
async def test_other_edits_still_work_without_admin(agent_id, auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=auth_headers) as client:
        response = await client.patch(
            f"/api/v1/agents/{agent_id}", json={"description": "changed", "autonomous_runs": None}
        )
    assert response.status_code == 200
    assert response.json()["description"] == "changed"
    assert response.json()["autonomous_runs"] is False

"""MCP split Fase 2b: an agent calling a sensitive MCP route with its own credential needs the
delegation for it (business rule MCP-023). People and bridge-token-only calls are not affected yet."""
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent, AgentServiceCredential
from app.db.models.governance import AuthorityDelegation
from app.db.models.user import User


@pytest_asyncio.fixture
async def client():
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def agent_with(request):
    """An agent with an agt_ credential and, optionally, delegations (marker param: actions)."""
    created: dict[str, list] = {"agents": [], "users": []}

    async def make(*actions: str, expired: bool = False) -> str:
        suffix = uuid.uuid4().hex[:8]
        token = f"agt_{uuid.uuid4().hex}{uuid.uuid4().hex}"
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as db:
            agent = Agent(name=f"Deleg {suffix}", agent_type="executor", runtime_type="hermes",
                          profile_slug=f"deleg-{suffix}")
            db.add(agent)
            await db.flush()
            db.add(AgentServiceCredential(agent_id=agent.id, label="delegation-test",
                                          token_hash=hashlib.sha256(token.encode()).hexdigest()))
            if actions:
                grantor = User(username=f"deleg-grantor-{suffix}", hashed_password="x", is_admin=True)
                db.add(grantor)
                await db.flush()
                created["users"].append(grantor.id)
                db.add(AuthorityDelegation(
                    grantor_user_id=grantor.id, grantee_type="agent", grantee_id=agent.id,
                    scope_type="organization", allowed_actions=list(actions), max_risk="low",
                    valid_from=now - timedelta(hours=2),
                    expires_at=now - timedelta(minutes=1) if expired else now + timedelta(hours=1),
                ))
            await db.commit()
            created["agents"].append(agent.id)
        return token

    yield make
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AuthorityDelegation).where(AuthorityDelegation.grantee_id.in_(created["agents"])))
        await db.execute(delete(AgentServiceCredential).where(AgentServiceCredential.agent_id.in_(created["agents"])))
        await db.execute(delete(Agent).where(Agent.id.in_(created["agents"])))
        await db.execute(delete(User).where(User.id.in_(created["users"])))
        await db.commit()


def _headers(token: str | None = None) -> dict[str, str]:
    headers = {"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN or ""}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def test_agent_without_delegation_is_refused(client, agent_with):
    token = await agent_with()
    response = await client.get("/api/v1/audit/checks", headers=_headers(token))
    assert response.status_code == 403, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "AGENT_DELEGATION_REQUIRED" and detail["action"] == "ops.read"


async def test_agent_with_the_delegation_passes(client, agent_with):
    token = await agent_with("ops.read")
    response = await client.get("/api/v1/audit/checks", headers=_headers(token))
    assert response.status_code == 200, response.text


async def test_one_action_does_not_open_another(client, agent_with):
    token = await agent_with("ops.read")
    response = await client.post("/api/v1/database/query", json={"sql": "select 1", "instance": "forgehub_postgres"},
                                 headers=_headers(token))
    assert response.status_code == 403, response.text
    assert response.json()["detail"]["action"] == "ops.database.query"


async def test_expired_delegation_counts_as_none(client, agent_with):
    token = await agent_with("ops.read", expired=True)
    response = await client.get("/api/v1/audit/checks", headers=_headers(token))
    assert response.status_code == 403, response.text


async def test_registry_credentials_need_their_own_action(client, agent_with):
    token = await agent_with("ops.read", "registry.read")
    target = uuid.uuid4()
    issue = await client.post(f"/api/v1/agents/{target}/credentials", json={"label": "x"}, headers=_headers(token))
    assert issue.status_code == 403, issue.text
    assert issue.json()["detail"]["action"] == "registry.credential.request"


async def test_bridge_token_alone_still_passes_until_2d(client):
    response = await client.get("/api/v1/audit/checks", headers=_headers())
    assert response.status_code == 200, response.text


async def test_messages_are_never_gated(client, agent_with):
    token = await agent_with()
    response = await client.get("/api/v1/agents", headers=_headers(token))
    assert response.status_code == 200, response.text

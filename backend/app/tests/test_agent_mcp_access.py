"""Agentes e MCP do ForgeHub (D4 screen): admin-only list/save of each agent's servers and
sensitive-action modes; the modes drive the approval gate at once (MCP-005, MCP-023)."""
import hashlib
import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent, AgentServiceCredential
from app.db.models.agent_mcp_access import AgentMcpAccess
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent
from app.db.models.notification import Notification
from app.db.models.user import User


@pytest_asyncio.fixture
async def client():
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def setup():
    suffix = uuid.uuid4().hex[:8]
    token = f"agt_{uuid.uuid4().hex}{uuid.uuid4().hex}"
    async with AsyncSessionLocal() as db:
        admin = User(username=f"mcp-admin-{suffix}", hashed_password=hash_password("x"), is_admin=True, is_active=True)
        plain = User(username=f"mcp-plain-{suffix}", hashed_password=hash_password("x"), is_admin=False, is_active=True)
        agent = Agent(name=f"Mcp {suffix}", agent_type="executor", runtime_type="hermes",
                      profile_slug=f"mcp-{suffix}", department="Documentation")
        db.add_all([admin, plain, agent])
        await db.flush()
        db.add(AgentServiceCredential(agent_id=agent.id, label="mcp-access-test",
                                      token_hash=hashlib.sha256(token.encode()).hexdigest()))
        await db.commit()
        data = {"agent_id": agent.id, "token": token, "admin": admin.username, "plain": plain.username,
                "users": [admin.id, plain.id]}
    yield data
    async with AsyncSessionLocal() as db:
        ids = (await db.execute(select(AgentDemand.id).where(AgentDemand.from_agent_id == data["agent_id"]))).scalars().all()
        await db.execute(delete(Notification).where(Notification.event_key.in_([f"agent-action:{i}" for i in ids])))
        await db.execute(delete(AgentDemand).where(AgentDemand.from_agent_id == data["agent_id"]))
        await db.execute(delete(AuditEvent).where(AuditEvent.entity_id == data["agent_id"]))
        await db.execute(delete(AgentMcpAccess).where(AgentMcpAccess.agent_id == data["agent_id"]))
        await db.execute(delete(AgentServiceCredential).where(AgentServiceCredential.agent_id == data["agent_id"]))
        await db.execute(delete(Agent).where(Agent.id == data["agent_id"]))
        await db.execute(delete(User).where(User.id.in_(data["users"])))
        await db.commit()


def _jwt(username: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(username)}"}


def _agent(token: str) -> dict[str, str]:
    return {"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN or "", "Authorization": f"Bearer {token}"}


async def test_list_shows_function_defaults_until_saved(client, setup):
    response = await client.get("/api/v1/mcp-access", headers=_jwt(setup["admin"]))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["core_server"] == "forgehub" and "forgehub_remote" in body["servers"]
    row = next(a for a in body["agents"] if a["agent_id"] == str(setup["agent_id"]))
    assert row["saved"] is False and row["department"] == "Documentation"
    assert row["servers"] == ["forgehub_factory", "forgehub_missions", "forgehub_ops"]
    assert row["restart_mode"] == row["query_mode"] == "approval"


async def test_only_admins(client, setup):
    assert (await client.get("/api/v1/mcp-access", headers=_jwt(setup["plain"]))).status_code == 403
    put = await client.put(f"/api/v1/mcp-access/{setup['agent_id']}", headers=_jwt(setup["plain"]),
                           json={"servers": [], "restart_mode": "direct", "query_mode": "direct"})
    assert put.status_code == 403


async def test_save_records_history_and_drives_the_gate(client, setup):
    # Before: Documentation queries need approval.
    before = await client.post("/api/v1/deploy/containers/demo/restart", headers=_agent(setup["token"]))
    assert before.status_code == 202, before.text
    saved = await client.put(f"/api/v1/mcp-access/{setup['agent_id']}", headers=_jwt(setup["admin"]),
                             json={"servers": ["forgehub_ops", "forgehub_factory"], "restart_mode": "direct",
                                   "query_mode": "approval"})
    assert saved.status_code == 200, saved.text
    assert saved.json()["servers"] == ["forgehub_factory", "forgehub_ops"] and saved.json()["saved"] is True
    after = await client.post("/api/v1/deploy/containers/demo/restart", headers=_agent(setup["token"]))
    assert after.status_code != 202, after.text  # now runs at once
    async with AsyncSessionLocal() as db:
        events = (await db.execute(select(AuditEvent).where(
            AuditEvent.entity_id == setup["agent_id"], AuditEvent.event_type == "agent_mcp_access_saved"))).scalars().all()
    assert len(events) == 1 and events[0].payload["after"]["restart_mode"] == "direct"


async def test_personal_only_for_the_maia_and_unknown_servers_refused(client, setup):
    personal = await client.put(f"/api/v1/mcp-access/{setup['agent_id']}", headers=_jwt(setup["admin"]),
                                json={"servers": ["forgehub_personal"], "restart_mode": "approval", "query_mode": "approval"})
    assert personal.status_code == 422 and personal.json()["detail"]["code"] == "PERSONAL_NOT_ALLOWED"
    unknown = await client.put(f"/api/v1/mcp-access/{setup['agent_id']}", headers=_jwt(setup["admin"]),
                               json={"servers": ["forgehub_everything"], "restart_mode": "approval", "query_mode": "approval"})
    assert unknown.status_code == 422


async def test_a_stale_screen_is_refused(client, setup):
    url = f"/api/v1/mcp-access/{setup['agent_id']}"
    first = await client.put(url, headers=_jwt(setup["admin"]),
                             json={"servers": [], "restart_mode": "approval", "query_mode": "approval"})
    stale = first.json()["updated_at"]
    await client.put(url, headers=_jwt(setup["admin"]),
                     json={"servers": ["forgehub_ops"], "restart_mode": "approval", "query_mode": "approval"})
    again = await client.put(url, headers=_jwt(setup["admin"]),
                             json={"servers": [], "restart_mode": "direct", "query_mode": "direct",
                                   "expected_updated_at": stale})
    assert again.status_code == 409, again.text

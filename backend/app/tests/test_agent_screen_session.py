"""An agent opens the screens with its own credential: read-only, limited, revocable."""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.agent_session import AGENT_SESSION_MINUTES, SERVICE_USERNAME, agent_session_refusal
from app.core.security import create_access_token, decode_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent, AgentServiceCredential
from app.db.models.governance import AuditEvent
from app.db.models.user import User
from app.main import app

SESSION = "/api/v1/auth/agent-session"


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def credential():
    agent_id, credential_id = uuid.uuid4(), uuid.uuid4()
    raw = f"agt_{secrets.token_urlsafe(32)}"
    async with AsyncSessionLocal() as db:
        db.add(Agent(id=agent_id, name=f"Sessao {agent_id.hex[:8]}", profile_slug=f"sessao-{agent_id.hex[:8]}",
                     screen_access_enabled=True))
        await db.flush()
        db.add(AgentServiceCredential(id=credential_id, agent_id=agent_id, label="teste",
                                      token_hash=hashlib.sha256(raw.encode()).hexdigest()))
        await db.commit()
    yield {"raw": raw, "id": credential_id, "agent_id": agent_id}
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AuditEvent).where(AuditEvent.entity_id == agent_id))
        await db.execute(delete(AgentServiceCredential).where(AgentServiceCredential.id == credential_id))
        await db.execute(delete(Agent).where(Agent.id == agent_id))
        await db.commit()


async def _session(client, credential) -> str:
    response = await client.post(SESSION, headers=_bearer(credential["raw"]))
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.mark.asyncio
async def test_credential_opens_a_short_audited_session_as_svc_agente(client, credential):
    response = await client.post(SESSION, headers=_bearer(credential["raw"]))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user"]["username"] == SERVICE_USERNAME
    assert body["user"]["is_admin"] is False
    assert body["permissions"]["tasks"]["can_view"] is True
    assert body["permissions"]["tasks"]["can_write"] is False
    assert body["permissions"]["database"]["can_view"] is False
    payload = decode_access_token(body["access_token"])
    lifetime = datetime.fromtimestamp(payload["exp"], timezone.utc) - datetime.now(timezone.utc)
    assert lifetime <= timedelta(minutes=AGENT_SESSION_MINUTES)
    async with AsyncSessionLocal() as db:
        events = (await db.execute(select(AuditEvent).where(AuditEvent.entity_id == credential["agent_id"]))).scalars().all()
    assert [event.event_type for event in events] == ["session_opened"]
    assert events[0].entity_type == "agent_screen_access"
    assert "ip_address" in events[0].payload and "user_agent" in events[0].payload


@pytest.mark.asyncio
async def test_bad_or_revoked_credential_opens_nothing(client, credential):
    for headers in ({}, _bearer("agt_errada"), _bearer("nao-e-credencial")):
        assert (await client.post(SESSION, headers=headers)).status_code == 401
    async with AsyncSessionLocal() as db:
        row = await db.get(AgentServiceCredential, credential["id"])
        row.revoked_at = datetime.now(timezone.utc)
        await db.commit()
    assert (await client.post(SESSION, headers=_bearer(credential["raw"]))).status_code == 401


@pytest.mark.asyncio
async def test_session_reads_but_never_writes(client, credential):
    token = await _session(client, credential)
    assert (await client.get("/api/v1/products", headers=_bearer(token))).status_code == 200
    for method, path in (("POST", "/api/v1/products"), ("PUT", f"/api/v1/products/{uuid.uuid4()}"),
                         ("PATCH", f"/api/v1/tasks/{uuid.uuid4()}"), ("DELETE", f"/api/v1/products/{uuid.uuid4()}")):
        response = await client.request(method, path, headers=_bearer(token), json={})
        assert response.status_code == 403, (method, path, response.text)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [
    "/api/v1/personal/tasks", "/api/v1/chat/sessions", "/api/v1/users", "/api/v1/database/tables",
    "/api/v1/file-explorer/list", "/api/v1/vault/secrets", "/api/v1/servers", "/api/v1/terminal/sessions",
    "/api/v1/client-ops/clients", "/api/v1/host-executions", "/api/v1/forgerouter/status",
])
async def test_private_areas_are_closed(client, credential, path):
    token = await _session(client, credential)
    assert (await client.get(path, headers=_bearer(token))).status_code == 403


def test_unknown_area_is_refused_by_default():
    assert agent_session_refusal("GET", "/api/v1/area-nova/itens") is not None
    assert agent_session_refusal("GET", "/api/v1/auth/totp/setup") is not None
    assert agent_session_refusal("GET", "/api/v1/auth/me") is None


@pytest.mark.asyncio
async def test_me_does_not_renew_the_session(client, credential):
    token = await _session(client, credential)
    response = await client.get("/api/v1/auth/me", headers=_bearer(token))
    assert response.status_code == 200, response.text
    assert response.json()["access_token"] == token


@pytest.mark.asyncio
async def test_revoking_the_credential_ends_an_open_session(client, credential):
    token = await _session(client, credential)
    async with AsyncSessionLocal() as db:
        row = await db.get(AgentServiceCredential, credential["id"])
        row.revoked_at = datetime.now(timezone.utc)
        await db.commit()
    assert (await client.get("/api/v1/products", headers=_bearer(token))).status_code == 401


@pytest.mark.asyncio
async def test_disabling_svc_agente_closes_the_door(client, credential):
    token = await _session(client, credential)
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.username == SERVICE_USERNAME))).scalar_one()
        user.is_active = False
        await db.commit()
    try:
        assert (await client.post(SESSION, headers=_bearer(credential["raw"]))).status_code == 403
        assert (await client.get("/api/v1/products", headers=_bearer(token))).status_code == 401
    finally:
        async with AsyncSessionLocal() as db:
            user = (await db.execute(select(User).where(User.username == SERVICE_USERNAME))).scalar_one()
            user.is_active = True
            await db.commit()


@pytest.mark.asyncio
async def test_person_session_is_unchanged(client, admin_headers):
    response = await client.post("/api/v1/service-lines", headers=admin_headers, json={})
    assert response.status_code != 403
    assert decode_access_token(create_access_token(subject="alguem")).get("purpose") is None


@pytest.mark.asyncio
async def test_agent_needs_the_admin_switch(client, credential, admin_headers):
    token = await _session(client, credential)
    url = f"/api/v1/agent-access/{credential['agent_id']}"
    response = await client.put(url, headers=admin_headers, json={"enabled": False})
    assert response.status_code == 200, response.text
    assert response.json()["enabled"] is False
    assert (await client.get("/api/v1/products", headers=_bearer(token))).status_code == 401
    refused = await client.post(SESSION, headers=_bearer(credential["raw"]))
    assert refused.status_code == 403, refused.text


@pytest.mark.asyncio
async def test_audit_shows_opened_read_denied_and_refused(client, credential, admin_headers):
    token = await _session(client, credential)
    await client.get("/api/v1/products", headers=_bearer(token))
    await client.get("/api/v1/products", headers=_bearer(token))
    await client.get("/api/v1/personal/tasks", headers=_bearer(token))
    await client.post("/api/v1/products", headers=_bearer(token), json={})
    await client.put(f"/api/v1/agent-access/{credential['agent_id']}", headers=admin_headers, json={"enabled": False})
    await client.post(SESSION, headers=_bearer(credential["raw"]))
    response = await client.get("/api/v1/agent-access/audit", headers=admin_headers,
                                params={"agent_id": str(credential["agent_id"])})
    assert response.status_code == 200, response.text
    events = [row["event"] for row in response.json()]
    assert events.count("session_opened") == 1
    assert events.count("area_read") == 1
    assert events.count("request_denied") == 2
    assert events.count("session_refused") == 1
    assert events.count("access_changed") == 1
    denied = next(row for row in response.json() if row["event"] == "request_denied")
    assert "path" in denied["details"] and "reason" in denied["details"]


@pytest.mark.asyncio
async def test_unknown_credential_attempt_is_audited(client, admin_headers):
    marker = f"navegador-{uuid.uuid4().hex}"
    await client.post(SESSION, headers={**_bearer("agt_inexistente"), "User-Agent": marker})
    rows = (await client.get("/api/v1/agent-access/audit", headers=admin_headers,
                             params={"event": "session_refused", "limit": 50})).json()
    assert any(row["details"].get("user_agent") == marker for row in rows)


@pytest.mark.asyncio
async def test_agent_access_screen_is_admin_only(client, credential):
    token = await _session(client, credential)
    assert (await client.get("/api/v1/agent-access", headers=_bearer(token))).status_code == 403
    assert (await client.get("/api/v1/agent-access/audit", headers=_bearer(token))).status_code == 403
    assert (await client.get("/api/v1/agent-access")).status_code == 401

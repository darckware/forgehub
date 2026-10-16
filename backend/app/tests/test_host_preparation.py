"""Preparation scripts per OS and the "Prepare" route (bridge mocked)."""
import uuid
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.api.routes import server as server_routes
from app.core.host_preparation import PreparationError, preparation_script
from app.core.secrets import decrypt_secret
from app.db.base import AsyncSessionLocal
from app.db.models.governance import AuditEvent
from app.db.models.server import Server

KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMQ97vnwnBBhgd4AiT2WLx7Z5qEVdq6sB3KPgSX3fd7C forgehub@pc01"
PRIV = "-----BEGIN OPENSSH PRIVATE KEY-----\nAAAA\n-----END OPENSSH PRIVATE KEY-----\n"


@pytest.mark.parametrize("os_family, language, must_have", [
    ("windows", "powershell", ["OpenSSH.Server~~~~0.0.1.0", "-RemoteAddress 100.64.0.0/10", "administrators_authorized_keys", "Select-String", "DefaultShell"]),
    ("linux", "sh", ["systemctl enable --now", "grep -qxF", "100.64.0.0/10"]),
    ("macos", "sh", ["systemsetup -setremotelogin on", "grep -qxF"]),
])
def test_scripts_carry_key_and_are_idempotent(os_family, language, must_have):
    script, lang = preparation_script(os_family, "administrador", KEY)
    assert lang == language
    assert KEY in script and "administrador" in script
    for fragment in must_have:
        assert fragment in script


@pytest.mark.parametrize("os_family", ["windows", "linux", "macos"])
def test_scripts_have_no_control_characters(os_family):
    # Regression (2026-10-16): "\\v1.0" in an f-string became a vertical tab,
    # the station's OpenSSH DefaultShell pointed nowhere and sshd refused
    # every login on it.
    script, _ = preparation_script(os_family, "darckware", KEY)
    assert not [c for c in script if ord(c) < 32 and c not in "\n\r\t"]
    if os_family == "windows":
        assert r'"$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"' in script


@pytest.mark.parametrize("login, key, os_family", [
    ("adm'; rm -rf /", KEY, "linux"),
    ("", KEY, "windows"),
    ("administrador", "ssh-ed25519 AAAA'; evil", "windows"),
    ("administrador", KEY, None),
])
def test_scripts_refuse_unsafe_input(login, key, os_family):
    with pytest.raises(PreparationError):
        preparation_script(os_family, login, key)


@pytest_asyncio.fixture
async def client(admin_headers):
    app = FastAPI()
    app.include_router(server_routes.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=admin_headers) as ac:
        yield ac


@pytest_asyncio.fixture
async def station():
    row = Server(name=f"prep-{uuid.uuid4().hex[:8]}", ip_address="100.127.8.1", remote_user="administrador",
                 kind="workstation", os_family="windows")
    async with AsyncSessionLocal() as db:
        db.add(row)
        await db.commit()
    yield row
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AuditEvent).where(AuditEvent.entity_id == row.id))
        await db.execute(delete(Server).where(Server.id == row.id))
        await db.commit()


def _resp(payload, code=200):
    return httpx.Response(code, json=payload, request=httpx.Request("POST", "http://bridge"))


@pytest.mark.asyncio
async def test_prepare_creates_key_vaults_it_and_returns_script(client, station):
    calls = []

    async def bridge(path, payload, timeout=20.0):
        calls.append(path)
        if path == "/v1/servers/ensure-key":
            return _resp({"key_path": "/root/agents/aegis/server-management/ssh_keys/100_127_8_1_key", "public_key": KEY, "created": True})
        return _resp({"private_key": PRIV, "public_key": KEY, "key_path": "x"})

    with patch.object(server_routes, "_bridge_post", AsyncMock(side_effect=bridge)):
        resp = await client.post(f"/api/v1/servers/{station.id}/preparation")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["language"] == "powershell" and body["key_created"] is True
        assert KEY in body["script"] and PRIV not in resp.text

        # Second call reuses the key: no new pair, no bridge call.
        calls.clear()
        again = await client.post(f"/api/v1/servers/{station.id}/preparation")
        assert again.json()["key_created"] is False and calls == []

    async with AsyncSessionLocal() as db:
        row = await db.get(Server, station.id)
        assert row.ssh_key_path.endswith("100_127_8_1_key")
        assert decrypt_secret(row.private_key_encrypted) == PRIV
        events = (await db.execute(select(AuditEvent).where(AuditEvent.entity_id == station.id))).scalars().all()
        assert len(events) == 2


@pytest.mark.asyncio
async def test_prepare_needs_os_and_login(client, station):
    async with AsyncSessionLocal() as db:
        row = await db.get(Server, station.id)
        row.os_family = None
        await db.commit()
    assert (await client.post(f"/api/v1/servers/{station.id}/preparation")).status_code == 422

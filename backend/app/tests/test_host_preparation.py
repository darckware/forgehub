"""Preparation scripts per OS and the "Prepare" route (bridge mocked)."""
import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.api.routes import host_execution as exec_routes
from app.api.routes import server as server_routes
from app.core import host_exec_runner
from app.db.models.host_execution import HostExecution
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
        execs = list((await db.execute(select(HostExecution.id).where(HostExecution.target_summary == row.name))).scalars())
        await db.execute(delete(AuditEvent).where(AuditEvent.entity_id.in_([row.id, *execs])))
        if execs:
            await db.execute(delete(HostExecution).where(HostExecution.id.in_(execs)))
        await db.execute(delete(Server).where(Server.id == row.id))
        await db.commit()


def _resp(payload, code=200):
    return httpx.Response(code, json=payload, request=httpx.Request("POST", "http://bridge"))


VAULT: dict[str, str] = {}


async def _fake_store(name, value, description, secret_type="Password"):
    VAULT[name] = value
    return f"{abs(hash(name)) % 10**8:08d}-0000-0000-0000-000000000000"


async def _bridge(path, payload, timeout=20.0):
    if path == "/v1/servers/ensure-key":
        return _resp({"key_path": f"/root/agents/aegis/server-management/ssh_keys/{payload['key_name']}_key", "public_key": KEY, "created": True})
    return _resp({"private_key": PRIV, "public_key": KEY, "key_path": "x"})


@pytest.mark.asyncio
async def test_copy_mode_creates_key_stores_password_in_vault_and_returns_script(client, station):
    VAULT.clear()
    with (
        patch.object(server_routes, "_bridge_post", AsyncMock(side_effect=_bridge)),
        patch.object(server_routes, "vault_store", AsyncMock(side_effect=_fake_store)),
    ):
        resp = await client.post(f"/api/v1/servers/{station.id}/preparation", json={"mode": "copy", "admin_user": "administrador"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["language"] == "powershell" and body["key_created"] is True and body["execution_id"] is None
    (name, password), = VAULT.items()
    assert name == f"WS_SEM_CLIENTE_{station.name.upper().replace('-', '_')}_LOGIN"
    assert password in body["script"] and KEY in body["script"] and "New-LocalUser" in body["script"]
    assert PRIV not in resp.text
    async with AsyncSessionLocal() as db:
        row = await db.get(Server, station.id)
        assert row.remote_user == "darckware" and row.admin_user == "administrador"
        assert row.login_password_ref and row.login_password_encrypted is None
        assert decrypt_secret(row.private_key_encrypted) == PRIV


async def _run_ssh(client, station, outcomes, disable=True):
    calls = []

    async def fake_exec(**kw):
        calls.append((kw["user"], kw["password"] is not None, kw["script"][:40]))
        return outcomes.pop(0)

    with (
        patch.object(server_routes, "_bridge_post", AsyncMock(side_effect=_bridge)),
        patch.object(server_routes, "vault_store", AsyncMock(side_effect=_fake_store)),
        patch.object(server_routes, "call_bridge_exec_as", fake_exec),
    ):
        resp = await client.post(f"/api/v1/servers/{station.id}/preparation", json={
            "mode": "ssh", "admin_user": "administrador", "admin_password": "Segredo#2026", "disable_admin": disable})
        assert resp.status_code == 200, resp.text
        execution_id = resp.json()["execution_id"]
        await asyncio.wait_for(host_exec_runner._running[uuid.UUID(execution_id)], timeout=10)
    async with AsyncSessionLocal() as db:
        detail = await exec_routes._detail(db, await db.get(HostExecution, uuid.UUID(execution_id)))
    return calls, detail


OK = {"exit_code": 0, "stdout": "pronto", "stderr": "", "duration_ms": 10, "failure": None}


@pytest.mark.asyncio
async def test_ssh_mode_prepares_checks_key_then_locks_admin(client, station):
    calls, detail = await _run_ssh(client, station, [
        OK, {**OK, "stdout": "88480281099\\darckware"}, {**OK, "stdout": "False"}])
    assert [c[0] for c in calls] == ["administrador", "darckware", "darckware"]
    assert calls[0][1] is True and calls[1][1] is False  # admin by password, darckware by key
    assert "Disable-LocalUser -Name 'administrador'" in calls[2][2] or calls[2][2].startswith("Disable-LocalUser")
    result = detail.results[0]
    assert result.status == "succeeded" and "3/3 Bloqueio de administrador: ok" in result.stdout
    assert "Segredo#2026" not in (detail.command or "") and "Segredo#2026" not in (result.stdout or "")
    assert detail.script_name == "Preparar estação"
    async with AsyncSessionLocal() as db:
        assert (await db.get(Server, station.id)).remote_user == "darckware"


@pytest.mark.asyncio
async def test_ssh_mode_never_locks_admin_when_the_new_login_fails(client, station):
    calls, detail = await _run_ssh(client, station, [
        OK, {"exit_code": 255, "stdout": "", "stderr": "Permission denied", "duration_ms": 1, "failure": "auth"}])
    assert [c[0] for c in calls] == ["administrador", "darckware"]  # no lock step
    result = detail.results[0]
    assert result.status == "failed" and "2/3 Login de darckware pela chave: FALHOU" in result.stdout


@pytest.mark.asyncio
async def test_prepare_validations(client, station):
    bad = await client.post(f"/api/v1/servers/{station.id}/preparation", json={"mode": "ssh", "admin_user": "administrador"})
    assert bad.status_code == 422
    darck = await client.post(f"/api/v1/servers/{station.id}/preparation", json={"mode": "ssh", "admin_user": "darckware", "admin_password": "x"})
    assert darck.status_code == 422
    async with AsyncSessionLocal() as db:
        row = await db.get(Server, station.id)
        row.os_family = None
        await db.commit()
    assert (await client.post(f"/api/v1/servers/{station.id}/preparation")).status_code == 422

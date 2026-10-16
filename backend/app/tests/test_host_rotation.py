"""Rotation on demand (darckware password, SSH key) and moving keys to
ForgeVault. Bridge and vault are faked; rows created here are deleted."""
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
from app.db.base import AsyncSessionLocal
from app.db.models.governance import AuditEvent
from app.db.models.host_execution import HostExecution
from app.db.models.server import Server

OLD_PUB = "ssh-ed25519 AAAAOLDKEYOLDKEY forgehub@old"
NEW_PUB = "ssh-ed25519 AAAANEWKEYNEWKEY forgehub@new"


@pytest_asyncio.fixture
async def client(admin_headers):
    app = FastAPI()
    app.include_router(server_routes.router)
    app.include_router(exec_routes.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=admin_headers) as ac:
        yield ac


@pytest_asyncio.fixture
async def station():
    row = Server(name=f"rot-{uuid.uuid4().hex[:8]}", ip_address="100.127.4.1", remote_user="darckware",
                 kind="workstation", os_family="windows", ssh_key_path="/root/agents/aegis/server-management/ssh_keys/old_key",
                 login_password_ref="00000000-0000-0000-0000-00000000aaaa")
    row.public_key = OLD_PUB
    async with AsyncSessionLocal() as db:
        db.add(row)
        await db.commit()
    yield row
    for task in list(host_exec_runner._running.values()):
        await asyncio.wait_for(task, timeout=10)
    async with AsyncSessionLocal() as db:
        execs = list((await db.execute(select(HostExecution.id).where(HostExecution.target_summary.like(f"%{row.name}%")))).scalars())
        await db.execute(delete(AuditEvent).where(AuditEvent.entity_id.in_([row.id, *execs])))
        if execs:
            await db.execute(delete(HostExecution).where(HostExecution.id.in_(execs)))
        await db.execute(delete(Server).where(Server.id == row.id))
        await db.commit()


class FakeVault:
    def __init__(self):
        self.versions: dict[str, list[str]] = {}

    async def store(self, name, value, description, secret_type="Password"):
        self.versions.setdefault(name, []).append(value)
        return "00000000-0000-0000-0000-00000000bbbb"

    async def reveal(self, ref):
        return "SenhaAntiga#2026"


def _resp(payload, code=200):
    return httpx.Response(code, json=payload, request=httpx.Request("POST", "http://bridge"))


async def _rotate(client, station, kind, outcomes, vault):
    calls = []

    async def fake_exec(**kw):
        calls.append(kw)
        return outcomes.pop(0)

    async def bridge(path, payload, timeout=20.0):
        if path == "/v1/servers/ensure-key":
            return _resp({"key_path": "/root/agents/aegis/server-management/ssh_keys/new_key", "public_key": NEW_PUB, "created": True})
        return _resp({"private_key": "NEW-PRIVATE", "public_key": NEW_PUB, "key_path": "x"})

    with (
        patch.object(server_routes, "call_bridge_exec_as", fake_exec),
        patch.object(server_routes, "_bridge_post", AsyncMock(side_effect=bridge)),
        patch.object(server_routes, "vault_store", vault.store),
        patch.object(server_routes, "vault_reveal", vault.reveal),
    ):
        resp = await client.post("/api/v1/servers/rotations", json={"server_ids": [str(station.id)], "kind": kind})
        assert resp.status_code == 201, resp.text
        execution_id = uuid.UUID(resp.json()["execution_id"])
        await asyncio.wait_for(host_exec_runner._running[execution_id], timeout=10)
    async with AsyncSessionLocal() as db:
        detail = await exec_routes._detail(db, await db.get(HostExecution, execution_id))
        row = await db.get(Server, station.id)
    return calls, detail.results[0], row


OK = {"exit_code": 0, "stdout": "ok", "stderr": "", "duration_ms": 5, "failure": None}
FAIL = {"exit_code": 255, "stdout": "", "stderr": "Permission denied", "duration_ms": 5, "failure": "auth"}


@pytest.mark.asyncio
async def test_password_rotation_stores_first_applies_then_verifies(client, station):
    vault = FakeVault()
    calls, result, row = await _rotate(client, station, "login_password", [OK, OK], vault)
    (name, values), = vault.versions.items()
    new = values[0]
    assert name.endswith("_LOGIN") and new != "SenhaAntiga#2026"
    assert "Set-LocalUser -Name 'darckware'" in calls[0]["script"] and calls[0]["key_ref"] is None or calls[0]["key_path"]
    assert calls[1]["password"] == new and calls[1]["script"] == "whoami"
    assert result.status == "succeeded" and "3/3 Login com a nova senha: ok" in result.stdout
    assert new not in (result.stdout or "")
    assert row.login_password_ref == "00000000-0000-0000-0000-00000000bbbb"


@pytest.mark.asyncio
async def test_password_rotation_failure_restores_previous_in_vault(client, station):
    vault = FakeVault()
    calls, result, row = await _rotate(client, station, "login_password", [FAIL], vault)
    (_, values), = vault.versions.items()
    assert values[-1] == "SenhaAntiga#2026"  # previous password is the vault's current again
    assert result.status == "failed" and "a senha anterior voltou" in result.stdout
    assert row.login_password_ref == "00000000-0000-0000-0000-00000000aaaa"


@pytest.mark.asyncio
async def test_key_rotation_removes_old_only_after_new_works(client, station):
    vault = FakeVault()
    calls, result, row = await _rotate(client, station, "ssh_key", [OK, OK, OK], vault)
    assert NEW_PUB in calls[0]["script"]                      # installed with the current key
    assert calls[1]["key_path"].endswith("new_key")            # login checked with the new key
    assert "AAAAOLDKEYOLDKEY" in calls[2]["script"] and calls[2]["key_path"].endswith("new_key")
    assert result.status == "succeeded"
    assert row.ssh_key_path.endswith("new_key") and row.public_key == NEW_PUB
    assert row.ssh_key_ref == "00000000-0000-0000-0000-00000000bbbb"
    assert list(vault.versions)[0].endswith("_SSH_KEY")


@pytest.mark.asyncio
async def test_key_rotation_keeps_old_key_when_new_login_fails(client, station):
    vault = FakeVault()
    calls, result, row = await _rotate(client, station, "ssh_key", [OK, FAIL], vault)
    assert len(calls) == 2  # never tried to remove the old key
    assert result.status == "failed" and "a chave atual continua valendo" in result.stdout
    assert row.ssh_key_path.endswith("old_key") and row.public_key == OLD_PUB


@pytest.mark.asyncio
async def test_keys_to_vault_is_idempotent(client, station):
    vault = FakeVault()

    async def bridge(path, payload, timeout=20.0):
        return _resp({"private_key": "PRIV", "public_key": OLD_PUB, "key_path": payload["key_path"]})

    with (
        patch.object(server_routes, "_bridge_post", AsyncMock(side_effect=bridge)),
        patch.object(server_routes, "vault_store", vault.store),
    ):
        # Scoped to this test's row: the test database is the real one.
        first = (await client.post(f"/api/v1/servers/keys:to-vault?server_ids={station.id}")).json()
        assert first["stored"] == [station.name]
        second = (await client.post(f"/api/v1/servers/keys:to-vault?server_ids={station.id}")).json()
        assert station.name in second["already"]

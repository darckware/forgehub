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
NEW_REF = "00000000-0000-0000-0000-00000000dddd"


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
    generated: list[dict] = []

    async def fake_exec(**kw):
        calls.append(kw)
        return outcomes.pop(0)

    async def bridge(path, payload, timeout=20.0):
        assert path == "/v1/servers/generate-key", path
        generated.append(payload)
        return _resp({"ssh_key_ref": NEW_REF, "public_key": NEW_PUB})

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
    vault.generated = generated
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
async def test_password_rotation_failure_keeps_the_previous_secret_untouched(client, station):
    """The new password goes to a fresh secret, so a failure needs no write
    back: the row keeps its previous ref and the previous secret was never
    rotated (its name might even be another machine's)."""
    vault = FakeVault()
    calls, result, row = await _rotate(client, station, "login_password", [FAIL], vault)
    (_, values), = vault.versions.items()
    assert len(values) == 1 and values[0] != "SenhaAntiga#2026"  # only the new one; nothing written back
    assert result.status == "failed" and "continua com a senha anterior" in result.stdout
    assert row.login_password_ref == "00000000-0000-0000-0000-00000000aaaa"
    event = await _failure_event(station)
    assert event.payload["outcome"] == "not_applied" and event.payload["step"] == "apply"
    assert event.payload["secret_ref"] == NEW_LOGIN_REF and event.payload["row_secret"] == "previous"


NEW_LOGIN_REF = "00000000-0000-0000-0000-00000000bbbb"
OLD_LOGIN_REF = "00000000-0000-0000-0000-00000000aaaa"
TIMEOUT = {"exit_code": None, "stdout": "", "stderr": "timed out", "duration_ms": 120000, "failure": "timeout"}
BRIDGE_LOST = {"failure": "connection", "stderr": "Host bridge unreachable: ReadTimeout"}


async def _failure_event(station):
    async with AsyncSessionLocal() as db:
        (event,) = list((await db.execute(select(AuditEvent).where(
            AuditEvent.entity_id == station.id, AuditEvent.event_type == "login_password_rotation_failed"))).scalars())
    values = repr(event.payload)
    assert "SenhaAntiga" not in values  # ids only, never a password
    return event


@pytest.mark.asyncio
@pytest.mark.parametrize("uncertain", [TIMEOUT, BRIDGE_LOST])
async def test_uncertain_apply_points_the_row_at_the_new_secret(client, station, uncertain):
    """A timeout (or losing the bridge mid-request) may come after the change
    happened: the machine may hold the new password, so the row follows it and
    the log says so; both ids are in the audit."""
    vault = FakeVault()
    calls, result, row = await _rotate(client, station, "login_password", [dict(uncertain)], vault)
    assert len(calls) == 1 and result.status == "failed"
    assert "resultado incerto" in result.stdout and "pode estar com a NOVA senha" in result.stdout
    assert row.login_password_ref == NEW_LOGIN_REF
    event = await _failure_event(station)
    assert event.payload == {"login": "darckware", "secret_ref": NEW_LOGIN_REF, "previous_secret_ref": OLD_LOGIN_REF,
                             "step": "apply", "outcome": "uncertain", "failure": uncertain["failure"],
                             "row_secret": "new"}


@pytest.mark.asyncio
async def test_windows_verify_and_reapply_both_failing_keeps_the_new_password(client, station):
    vault = FakeVault()
    calls, result, row = await _rotate(client, station, "login_password", [OK, FAIL, FAIL], vault)
    assert [c["script"] == "whoami" for c in calls] == [False, True, False]
    assert "SenhaAntiga#2026" in calls[2]["script"]               # the reapply was tried
    assert "reaplicar a senha anterior: FALHOU" in result.stdout
    assert "senha anterior reaplicada: ok" not in result.stdout
    assert row.login_password_ref == NEW_LOGIN_REF
    event = await _failure_event(station)
    assert event.payload["step"] == "verify" and event.payload["outcome"] == "revert_failed"
    assert event.payload["row_secret"] == "new"


@pytest.mark.asyncio
async def test_windows_verify_failing_with_a_good_reapply_keeps_the_previous_secret(client, station):
    vault = FakeVault()
    calls, result, row = await _rotate(client, station, "login_password", [OK, FAIL, OK], vault)
    assert "senha anterior reaplicada: ok" in result.stdout
    assert row.login_password_ref == OLD_LOGIN_REF
    event = await _failure_event(station)
    assert event.payload["outcome"] == "reverted" and event.payload["secret_ref"] == NEW_LOGIN_REF


@pytest.mark.asyncio
async def test_key_rotation_removes_old_only_after_new_works(client, station):
    vault = FakeVault()
    calls, result, row = await _rotate(client, station, "ssh_key", [OK, OK, OK], vault)
    (generated,) = vault.generated                             # one new Vault secret, unique name
    assert generated["secret_name"].endswith("_SSH_KEY")          # suffix before the purpose (ECO-060)
    assert NEW_PUB in calls[0]["script"]                      # installed with the current key
    assert calls[1]["key_ref"] == NEW_REF  # login checked with the new key (key_ref wins over key_path in call_bridge_exec_as)
    assert "AAAAOLDKEYOLDKEY" in calls[2]["script"] and calls[2]["key_ref"] == NEW_REF
    assert result.status == "succeeded"
    assert row.ssh_key_path is None and row.public_key == NEW_PUB and row.ssh_key_ref == NEW_REF
    assert row.private_key_encrypted is None
    assert vault.versions == {}                                # nothing stored outside generate-key


@pytest.mark.asyncio
async def test_key_rotation_keeps_old_key_when_new_login_fails(client, station):
    vault = FakeVault()
    calls, result, row = await _rotate(client, station, "ssh_key", [OK, FAIL], vault)
    assert len(calls) == 2  # never tried to remove the old key
    assert result.status == "failed" and "a chave atual continua valendo" in result.stdout
    assert row.ssh_key_path.endswith("old_key") and row.public_key == OLD_PUB and row.ssh_key_ref is None


def _install_bridge(check_status: str = "active", strict_flag: bool = True):
    """Fake bridge for install-key: ForgeVault key generation, then the strict
    check-status probe with that key. (The keys:to-vault migration route was
    retired with ForgeVault-only keys, 2026-10-24 design.)"""
    seen: list[tuple[str, dict]] = []

    async def bridge(path, payload, timeout=20.0):
        seen.append((path, payload))
        if path == "/v1/servers/generate-key":
            return _resp({"ssh_key_ref": NEW_REF, "public_key": NEW_PUB})
        assert path == "/v1/servers/check-status", path
        entry = payload["servers"][0]
        return _resp({"statuses": {entry["id"]: check_status}, "vault_strict": strict_flag})

    return bridge, seen


@pytest.mark.asyncio
async def test_terminal_command_uses_the_vault_agent(client, station):
    async with AsyncSessionLocal() as db:
        row = await db.get(Server, station.id)
        row.ssh_key_ref = "00000000-0000-0000-0000-00000000cccc"
        await db.commit()

    async def bridge(path, payload, timeout=20.0):
        assert path == "/v1/servers/agent:open" and payload["key_ref"].endswith("cccc")
        return _resp({"socket": "/dev/shm/fh-agent-1/agent.sock"})

    with patch.object(server_routes, "_bridge_post", AsyncMock(side_effect=bridge)):
        out = (await client.post(f"/api/v1/servers/{station.id}/terminal-command")).json()
    assert out == {"command": "ssh -o IdentityAgent=/dev/shm/fh-agent-1/agent.sock darckware@100.127.4.1", "vault_key": True}


class _FakeInstallClient:
    def __init__(self, *a, **k): ...
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def post(self, url, **kw):
        assert url.endswith("/v1/servers/install-key")
        assert kw["json"]["public_key"] == NEW_PUB   # only the public half goes to the machine
        return httpx.Response(200, json={"ok": True, "steps": ["install", "verify"]},
                              request=httpx.Request("POST", "http://bridge"))


async def _install(client, station, bridge):
    with (
        patch.object(server_routes.httpx, "AsyncClient", _FakeInstallClient),
        patch.object(server_routes, "_bridge_post", AsyncMock(side_effect=bridge)),
    ):
        return await client.post(f"/api/v1/servers/{station.id}/install-key", json={"password": "x"})


@pytest.mark.asyncio
async def test_install_key_puts_the_new_key_on_forgevault(client, station):
    bridge, seen = _install_bridge()
    resp = await _install(client, station, bridge)
    assert resp.status_code == 200, resp.text
    assert resp.json()["vault"] == "switched" and resp.json()["key_path"] is None
    probe = next(p for path, p in seen if path == "/v1/servers/check-status")["servers"][0]
    assert probe["strict"] is True and probe["ssh_key_ref"] == NEW_REF
    async with AsyncSessionLocal() as db:
        row = await db.get(Server, station.id)
        released = (await db.execute(select(AuditEvent).where(
            AuditEvent.entity_id == station.id, AuditEvent.event_type == "ssh_key_path_released"))).scalar_one()
    assert row.ssh_key_ref == NEW_REF and row.ssh_key_path is None and row.public_key == NEW_PUB
    assert released.payload["old_key_path"].endswith("old_key")


@pytest.mark.asyncio
async def test_install_key_keeps_the_previous_record_when_the_vault_key_is_refused(client, station):
    bridge, _ = _install_bridge(check_status="not_installed")
    resp = await _install(client, station, bridge)
    assert resp.status_code == 200 and resp.json()["ok"] is False and resp.json()["failed_step"] == "verify"
    async with AsyncSessionLocal() as db:
        row = await db.get(Server, station.id)
    assert row.ssh_key_path.endswith("old_key") and row.ssh_key_ref is None and row.public_key == OLD_PUB


@pytest.mark.asyncio
async def test_install_key_never_trusts_an_old_bridge(client, station):
    """A bridge without the strict mode ignores the vault key and could pass
    on any key the host has: no switch then."""
    bridge, _ = _install_bridge(strict_flag=False)
    resp = await _install(client, station, bridge)
    assert resp.status_code == 503 and "too old" in resp.json()["detail"]
    async with AsyncSessionLocal() as db:
        row = await db.get(Server, station.id)
    assert row.ssh_key_path.endswith("old_key") and row.ssh_key_ref is None

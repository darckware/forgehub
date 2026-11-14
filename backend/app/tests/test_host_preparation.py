"""Preparation scripts per OS and the "Prepare" route (bridge mocked)."""
import asyncio
import re
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


GENERATED: list[dict] = []
GEN_REF = "00000000-0000-0000-0000-00000000eeee"


async def _bridge(path, payload, timeout=20.0):
    # ForgeVault-only keys (2026-10-24 design): the bridge generates the key in
    # tmpfs, stores the private half in ForgeVault and returns only its id and
    # the public half. Nothing private ever reaches ForgeHub.
    assert path == "/v1/servers/generate-key", path
    GENERATED.append(payload)
    return _resp({"ssh_key_ref": GEN_REF, "public_key": KEY})


@pytest.mark.asyncio
async def test_copy_mode_creates_key_stores_password_in_vault_and_returns_script(client, station):
    VAULT.clear()
    GENERATED.clear()
    with (
        patch.object(server_routes, "_bridge_post", AsyncMock(side_effect=_bridge)),
        patch.object(server_routes, "vault_store", AsyncMock(side_effect=_fake_store)),
    ):
        resp = await client.post(f"/api/v1/servers/{station.id}/preparation", json={"mode": "copy", "admin_user": "administrador"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["language"] == "powershell" and body["key_created"] is True and body["execution_id"] is None
    base = f"WS_SEM_CLIENTE_{station.name.upper().replace('-', '_')}"
    # Fresh names, suffix before the purpose (WS_<CLIENT>_<MACHINE>_<SUFFIX>_<PURPOSE>):
    # the vault upserts by name, so a computed name is never reused.
    (login_name,) = VAULT                                      # the password, through vault_store
    assert re.fullmatch(rf"{base}_[0-9A-F]{{12}}_LOGIN", login_name)
    (key_name,) = [g["secret_name"] for g in GENERATED]         # the key, generated in ForgeVault
    assert re.fullmatch(rf"{base}_[0-9A-F]{{12}}_SSH_KEY", key_name)
    password = VAULT[login_name]
    assert password in body["script"] and KEY in body["script"] and "New-LocalUser" in body["script"]
    assert PRIV not in resp.text
    async with AsyncSessionLocal() as db:
        row = await db.get(Server, station.id)
        assert row.remote_user == "administrador" and row.admin_user is None
        assert row.login_password_ref is None and row.ssh_key_ref is None
        assert row.pending_login_password_ref and row.pending_ssh_key_ref == GEN_REF
        assert row.private_key_encrypted is None and row.ssh_key_path is None


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
    assert result.status == "succeeded"
    assert "Segredo#2026" not in (detail.command or "") and "Segredo#2026" not in (result.stdout or "")
    assert detail.script_name == "Preparar máquina"
    async with AsyncSessionLocal() as db:
        assert (await db.get(Server, station.id)).remote_user == "darckware"


@pytest.mark.asyncio
async def test_ssh_mode_never_locks_admin_when_the_new_login_fails(client, station):
    calls, detail = await _run_ssh(client, station, [
        OK, {"exit_code": 255, "stdout": "", "stderr": "Permission denied", "duration_ms": 1, "failure": "auth"}])
    assert [c[0] for c in calls] == ["administrador", "darckware"]  # no lock step
    result = detail.results[0]
    assert result.status == "failed" and "Candidate key did not authenticate" in result.stdout


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


@pytest.mark.asyncio
async def test_a_machine_on_its_vault_key_gets_fresh_candidate(client, station):
    """Reconfiguration preserves active access while minting a new candidate."""
    async with AsyncSessionLocal() as db:
        row = await db.get(Server, station.id)
        row.ssh_key_ref, row.public_key, row.ssh_key_path = "00000000-0000-0000-0000-00000000dddd", None, None
        await db.commit()
    bridge = AsyncMock(side_effect=_bridge)
    with (
        patch.object(server_routes, "_bridge_post", bridge),
        patch.object(server_routes, "vault_store", AsyncMock(side_effect=_fake_store)),
    ):
        resp = await client.post(f"/api/v1/servers/{station.id}/preparation", json={"mode": "copy", "admin_user": "administrador"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["key_created"] is True
    assert len(bridge.call_args_list) == 1
    async with AsyncSessionLocal() as db:
        row = await db.get(Server, station.id)
    assert row.ssh_key_ref.endswith("dddd") and row.ssh_key_path is None
    assert row.pending_ssh_key_ref == GEN_REF


@pytest.mark.parametrize("identity,os_family,ok", [
    ("darckware", "linux", True), ("darckware-evil", "linux", False),
    ("aegis", "linux", False), ("darckware\nroot", "linux", False),
    ("HOST\\Darckware", "windows", True), ("HOST\\notdarckware", "windows", False),
    ("darckware", "windows", False), ("HOST\\darckware-evil", "windows", False),
])
def test_exact_machine_identity(identity, os_family, ok):
    assert server_routes._is_machine_login(identity, os_family) is ok


@pytest.mark.asyncio
async def test_pending_is_durable_recoverable_and_promoted_only_after_exact_validation(client, station):
    with (patch.object(server_routes, "_bridge_post", AsyncMock(side_effect=_bridge)) as generate,
          patch.object(server_routes, "vault_store", AsyncMock(side_effect=_fake_store)) as store):
        first = await client.post(f"/api/v1/servers/{station.id}/preparation", json={"ssh_port": 2222})
        assert first.status_code == 200, first.text
        again = await client.post(f"/api/v1/servers/{station.id}/preparation")
        assert again.status_code == 409
        assert generate.await_count == store.await_count == 1
    async with AsyncSessionLocal() as db:
        row = await db.get(Server, station.id)
        assert row.ssh_port == 22 and row.pending_ssh_port == 2222
        ref = row.pending_login_password_ref
    password = list(VAULT.values())[-1]
    with patch.object(server_routes, "vault_reveal", AsyncMock(return_value=password)) as reveal:
        recovered = await client.post(f"/api/v1/servers/{station.id}/preparation/pending")
        assert recovered.status_code == 200, recovered.text
        assert recovered.json()["script"] == first.json()["script"]
        reveal.assert_awaited_once_with(ref)
    with patch.object(server_routes, "call_bridge_exec_as", AsyncMock(return_value={**OK, "stdout": "host\\notdarckware"})):
        bad = await client.post(f"/api/v1/servers/{station.id}/preparation/validate")
    assert bad.status_code == 200 and bad.json()["ok"] is False
    async with AsyncSessionLocal() as db:
        row = await db.get(Server, station.id)
        assert row.remote_user == "administrador" and row.ssh_port == 22 and row.preparation_pending
    with patch.object(server_routes, "call_bridge_exec_as", AsyncMock(return_value={**OK, "stdout": "host\\darckware"})) as bridge:
        good = await client.post(f"/api/v1/servers/{station.id}/preparation/validate")
    assert good.status_code == 200 and good.json()["ok"] is True
    assert bridge.call_args.kwargs["key_ref"] == GEN_REF
    assert bridge.call_args.kwargs["port"] == 2222
    async with AsyncSessionLocal() as db:
        row = await db.get(Server, station.id)
        assert row.remote_user == "darckware" and row.ssh_port == 2222
        assert row.ssh_key_ref == GEN_REF and row.login_password_ref == ref and not row.preparation_pending
        assert row.access_verified_at is not None


@pytest.mark.asyncio
async def test_stored_password_cannot_bootstrap_legacy_login(client, station):
    with patch.object(server_routes, "vault_reveal", AsyncMock()) as reveal:
        response = await client.post(f"/api/v1/servers/{station.id}/preparation", json={
            "mode": "ssh", "use_stored_password": True, "disable_admin": False})
    assert response.status_code == 422
    reveal.assert_not_awaited()


@pytest.mark.asyncio
async def test_agents_require_verified_parseable_unique_machine_key():
    from datetime import datetime, timezone
    from fastapi import HTTPException
    from app.core.remote_authority import require_managed_machines
    from types import SimpleNamespace
    valid = dict(id=uuid.uuid4(), name="test", remote_user="darckware", ssh_key_ref="key",
                 login_password_ref="password", access_verified_at=datetime.now(timezone.utc), public_key=KEY,
                 preparation_pending=False)
    for changed in [dict(remote_user="aegis"), dict(ssh_key_ref=None), dict(login_password_ref=None),
                    dict(access_verified_at=None), dict(public_key="invalid"), dict(public_key=None)]:
        with pytest.raises(HTTPException) as caught:
            await require_managed_machines(AsyncMock(), [SimpleNamespace(**(valid | changed))])
        assert caught.value.status_code == 403
        assert caught.value.detail["code"] == "MACHINE_RECONFIGURATION_REQUIRED"
    with patch("app.core.ssh_key_uniqueness.find_key_owner", AsyncMock(return_value="other-machine")):
        with pytest.raises(HTTPException):
            await require_managed_machines(AsyncMock(), [SimpleNamespace(**valid)])
    with patch("app.core.ssh_key_uniqueness.find_key_owner", AsyncMock(return_value=None)):
        await require_managed_machines(AsyncMock(), [SimpleNamespace(**valid)])


@pytest.mark.asyncio
async def test_inventory_cannot_forge_or_keep_machine_verification(client, station):
    from datetime import datetime, timezone
    response = await client.put(f"/api/v1/servers/{station.id}", json={"remote_user": "darckware"})
    assert response.status_code == 422
    async with AsyncSessionLocal() as db:
        row = await db.get(Server, station.id)
        row.remote_user = "darckware"
        row.access_verified_at = datetime.now(timezone.utc)
        await db.commit()
    response = await client.put(f"/api/v1/servers/{station.id}", json={"ssh_port": 2223})
    assert response.status_code == 200
    assert response.json()["access_verified_at"] is None


@pytest.mark.asyncio
async def test_validation_reservation_refuses_parallel_checks_and_access_pause_preserves_candidate(client, station):
    with (patch.object(server_routes, "_bridge_post", AsyncMock(side_effect=_bridge)),
          patch.object(server_routes, "vault_store", AsyncMock(side_effect=_fake_store))):
        response = await client.post(f"/api/v1/servers/{station.id}/preparation")
    assert response.status_code == 200
    started, release = asyncio.Event(), asyncio.Event()

    async def bridge(**kwargs):
        started.set()
        await release.wait()
        return {**OK, "stdout": "host\\darckware"}

    with patch.object(server_routes, "call_bridge_exec_as", bridge):
        first = asyncio.create_task(client.post(f"/api/v1/servers/{station.id}/preparation/validate"))
        await asyncio.wait_for(started.wait(), timeout=5)
        second = await client.post(f"/api/v1/servers/{station.id}/preparation/validate")
        assert second.status_code == 409
        paused = await client.put(f"/api/v1/servers/{station.id}", json={"access_enabled": False})
        assert paused.status_code == 200
        release.set()
        checked = await first
    assert checked.status_code == 409
    async with AsyncSessionLocal() as db:
        row = await db.get(Server, station.id)
        assert row.preparation_pending and row.access_verified_at is None
        assert row.remote_user == "administrador" and row.preparation_validation_until is None


@pytest.mark.asyncio
async def test_staging_blocks_inventory_and_key_mutation(client, station):
    with (patch.object(server_routes, "_bridge_post", AsyncMock(side_effect=_bridge)),
          patch.object(server_routes, "vault_store", AsyncMock(side_effect=_fake_store))):
        response = await client.post(f"/api/v1/servers/{station.id}/preparation")
    assert response.status_code == 200
    changed = await client.put(f"/api/v1/servers/{station.id}", json={"ssh_port": 2222})
    deleted = await client.delete(f"/api/v1/servers/{station.id}/key")
    assert changed.status_code == deleted.status_code == 409

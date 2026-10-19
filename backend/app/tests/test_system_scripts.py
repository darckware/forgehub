"""System scripts (Tailscale/RustDesk install, RustDesk password change):
safe text, idempotent seed, and the RustDesk ID/password recorded only after
success. Bridge mocked; rows created here are deleted."""
import asyncio
import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import delete, select

from app.api.routes import host_execution as exec_routes
from app.core import host_exec_runner
from app.core.host_scripts import ScriptError, render_script, resolve_values, validate_parameters
from app.core.system_scripts import RUSTDESK_SERVER_SECRET, SYSTEM_SCRIPTS, seed_system_scripts
from app.db.base import AsyncSessionLocal
from app.db.models.governance import AuditEvent
from app.db.models.host_execution import HostExecution
from app.db.models.host_script import HostScript
from app.db.models.server import Server


@pytest.mark.parametrize("spec", SYSTEM_SCRIPTS, ids=lambda s: s["system_key"])
def test_system_scripts_render_safely(spec):
    params = validate_parameters(spec["parameters"])
    values = {p["name"]: "x'; evil" for p in params if p["required"] and not p["default"]}
    resolved, _ = resolve_values(params, values)
    text = render_script(spec["platform"], spec["content"], resolved)
    assert not [c for c in text if ord(c) < 32 and c not in "\n\r\t"]
    if spec["platform"] == "windows" and values:
        assert "x''; evil" in text  # quoted for PowerShell
    if spec["system_key"].startswith(("rustdesk_install", "remote_access_install")):
        assert "RUSTDESK_ID=" in text
        fixed = {p["name"]: p for p in params if p.get("vault_secret") == RUSTDESK_SERVER_SECRET}
        assert {n: p["vault_field"] for n, p in fixed.items()} == {
            "RUSTDESK_ID_SERVER": "id_server", "RUSTDESK_RELAY_SERVER": "relay_server", "RUSTDESK_KEY": "key"}
        assert not any(p["default"] for p in fixed.values())  # nothing fixed is kept in the script
        assert fixed["RUSTDESK_KEY"]["secret"] and not fixed["RUSTDESK_ID_SERVER"]["secret"]


def _render(system_key, values):
    spec = next(s for s in SYSTEM_SCRIPTS if s["system_key"] == system_key)
    params = validate_parameters(spec["parameters"])
    resolved, secrets = resolve_values(params, values)
    return render_script(spec["platform"], spec["content"], resolved), secrets


@pytest.mark.parametrize("platform", ["windows", "linux", "macos"])
def test_user_password_scripts(platform):
    text, secrets = _render(f"user_password:{platform}", {"USER_LOGIN": "maria", "USER_PASSWORD": "N0va'Senha"})
    assert secrets == ["N0va'Senha"]  # masked in the stored command and output
    assert "darckware" in text  # the maintenance account is refused by the script
    if platform == "linux":
        assert '| $SUDO chpasswd' in text  # password on stdin, not in argv
    with pytest.raises(ScriptError):
        _render(f"user_password:{platform}", {"USER_LOGIN": "maria", "USER_PASSWORD": "x", "ACCOUNT_STATE": "apagada"})


# What prepare_script_run would read from ForgeVault (these tests render directly).
_RD_SERVER = {"RUSTDESK_ID_SERVER": "10.0.0.9", "RUSTDESK_RELAY_SERVER": "10.0.0.9:21117", "RUSTDESK_KEY": "k="}


@pytest.mark.parametrize("platform", ["windows", "linux"])
def test_remote_access_installer_options(platform):
    spec = next(s for s in SYSTEM_SCRIPTS if s["system_key"] == f"remote_access_install:{platform}")
    params = {p["name"]: p for p in validate_parameters(spec["parameters"])}
    assert params["COMPONENTES"]["options"] == ["tailscale_e_rustdesk", "somente_tailscale", "somente_rustdesk"]
    # Only Tailscale needs no RustDesk password, only RustDesk no auth key.
    assert not params["TAILSCALE_AUTHKEY"]["required"] and not params["RUSTDESK_PASSWORD"]["required"]
    assert ("ROUTER_IP" in params) == (platform == "windows")  # router mode is Windows-only
    text, _ = _render(f"remote_access_install:{platform}", {"COMPONENTES": "somente_tailscale", "TAILSCALE_AUTHKEY": "tskey-x", **_RD_SERVER})
    assert "Validacao" in text
    with pytest.raises(ScriptError):
        _render(f"remote_access_install:{platform}", {"COMPONENTES": "tudo", **_RD_SERVER})


@pytest.mark.asyncio
async def test_rustdesk_server_read_from_forgevault_when_blank():
    spec = next(s for s in SYSTEM_SCRIPTS if s["system_key"] == "rustdesk_install:windows")
    script = HostScript(system_key=spec["system_key"], platform="windows", content=spec["content"],
                        parameters=validate_parameters(spec["parameters"]), archived=False)
    asked = []

    async def reveal(name):
        asked.append(name)
        return '{"id_server": "10.0.0.9", "relay_server": "10.0.0.9:21117", "key": "vault-key="}'

    with patch.object(exec_routes, "vault_reveal_name", reveal):
        text, _, secrets = await exec_routes.prepare_script_run(script, {"RUSTDESK_PASSWORD": "Senha#2026x"})
        assert asked == [RUSTDESK_SERVER_SECRET]  # one read for the three fields
        assert "$RUSTDESK_ID_SERVER = '10.0.0.9'" in text and "$RUSTDESK_KEY = 'vault-key='" in text
        assert "vault-key=" in secrets and "10.0.0.9" not in secrets  # only the key is masked
        text, _, _ = await exec_routes.prepare_script_run(script, {
            "RUSTDESK_PASSWORD": "Senha#2026x", "RUSTDESK_ID_SERVER": "1.2.3.4",
            "RUSTDESK_RELAY_SERVER": "1.2.3.4:21117", "RUSTDESK_KEY": "typed="})
        assert asked == [RUSTDESK_SERVER_SECRET] and "'typed='" in text  # typed values never touch the vault

    async def broken(name):
        return '{"id_server": "10.0.0.9"}'

    with patch.object(exec_routes, "vault_reveal_name", broken), pytest.raises(HTTPException):
        await exec_routes.prepare_script_run(script, {"RUSTDESK_PASSWORD": "Senha#2026x"})


def test_installer_records_rustdesk_password_only_when_rustdesk_installed():
    script = HostScript(system_key="remote_access_install:windows")
    assert exec_routes.system_script_hook(script, {"COMPONENTES": "somente_tailscale", "RUSTDESK_PASSWORD": "x"}) is None
    assert exec_routes.system_script_hook(script, {"COMPONENTES": "somente_rustdesk", "RUSTDESK_PASSWORD": "x"}) is not None


@pytest.mark.parametrize("platform", ["windows", "linux"])
def test_tailscale_adjust(platform):
    text, _ = _render(f"tailscale_adjust:{platform}", {"AJUSTE": "anunciar_subrede", "ROTAS": "192.168.0.0/24"})
    assert "--advertise-routes=" in text and "--accept-routes=" in text and "Configuracao atual" in text
    if platform == "linux":
        assert "net.ipv4.ip_forward = 1" in text  # a Linux router must forward
    else:
        assert "Tailscale\\tailscale.exe" in text
    assert "ver_configuracao" in text or "AJUSTE" in text
    with pytest.raises(ScriptError):
        _render(f"tailscale_adjust:{platform}", {"AJUSTE": "rotear_tudo"})


def test_every_system_script_is_classified():
    from app.core.system_scripts import SYSTEM_CATEGORIES

    slugs = {slug for slug, _, _ in SYSTEM_CATEGORIES}
    assert all(spec["category"] in slugs for spec in SYSTEM_SCRIPTS)


@pytest.mark.asyncio
async def test_seed_is_idempotent():
    await seed_system_scripts()
    assert await seed_system_scripts() == 0
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(HostScript).where(HostScript.is_system.is_(True)))).scalars().all()
    keys = {r.system_key for r in rows}
    assert {s["system_key"] for s in SYSTEM_SCRIPTS} <= keys


@pytest_asyncio.fixture
async def machine():
    row = Server(name=f"rd-{uuid.uuid4().hex[:8]}", ip_address="100.127.5.1", remote_user="darckware",
                 os_family="windows", kind="workstation")
    async with AsyncSessionLocal() as db:
        db.add(row)
        await db.commit()
    yield row
    for task in list(host_exec_runner._running.values()):
        await asyncio.wait_for(task, timeout=10)
    async with AsyncSessionLocal() as db:
        ids = list((await db.execute(select(HostExecution.id).where(HostExecution.target_summary == "rd-test"))).scalars())
        await db.execute(delete(AuditEvent).where(AuditEvent.entity_id.in_([row.id, *ids])))
        if ids:
            await db.execute(delete(HostExecution).where(HostExecution.id.in_(ids)))
        await db.execute(delete(Server).where(Server.id == row.id))
        await db.commit()


VAULT: dict[str, str] = {}


async def _fake_store(name, value, description, secret_type="Password"):
    VAULT[name] = value
    return "11111111-2222-3333-4444-555555555555"


async def _run(machine, outcome):
    await seed_system_scripts()
    async with AsyncSessionLocal() as db:
        script = (await db.execute(select(HostScript).where(HostScript.system_key == "rustdesk_password:windows"))).scalar_one()
        values = {"RUSTDESK_PASSWORD": "Nova#Senha2026"}
        command, shell, secrets = await exec_routes.prepare_script_run(script, values)

        async def bridge(server, shell_, body, timeout):
            assert "$RUSTDESK_PASSWORD = 'Nova#Senha2026'" in body
            return outcome

        with (
            patch.object(host_exec_runner, "call_bridge_exec", bridge),
            patch.object(exec_routes, "vault_store", _fake_store),
        ):
            execution = await exec_routes.launch_execution(
                db, servers=[await db.get(Server, machine.id)], command=command, shell=shell, timeout_seconds=60,
                actor="t", target_summary="rd-test", secrets=secrets, script=script, values_for_hook=values)
            await asyncio.wait_for(host_exec_runner._running[execution.id], timeout=10)
    return execution


@pytest.mark.asyncio
async def test_rustdesk_password_recorded_only_after_success(machine):
    await _run(machine, {"exit_code": 1, "stdout": "", "stderr": "recusou", "duration_ms": 1, "failure": "command"})
    async with AsyncSessionLocal() as db:
        row = await db.get(Server, machine.id)
        assert row.rustdesk_password_ref is None and row.rustdesk_password_encrypted is None
    assert VAULT == {}

    execution = await _run(machine, {"exit_code": 0, "stdout": "RUSTDESK_ID=123456789\n", "stderr": "", "duration_ms": 1, "failure": None})
    async with AsyncSessionLocal() as db:
        row = await db.get(Server, machine.id)
        assert row.rustdesk_id == "123456789"
        assert row.rustdesk_password_ref == "11111111-2222-3333-4444-555555555555"
        assert row.rustdesk_password_encrypted is None
    assert list(VAULT.values()) == ["Nova#Senha2026"]
    assert list(VAULT)[0].endswith("_RUSTDESK")
    async with AsyncSessionLocal() as db:
        detail = await exec_routes._detail(db, await db.get(HostExecution, execution.id))
    assert "Nova#Senha2026" not in detail.command  # secret parameter masked in the stored command

"""System scripts (Tailscale/RustDesk install, RustDesk password change):
safe text, idempotent seed, and the RustDesk ID/password recorded only after
success. Bridge mocked; rows created here are deleted."""
import asyncio
import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.api.routes import host_execution as exec_routes
from app.core import host_exec_runner
from app.core.host_scripts import render_script, resolve_values, validate_parameters
from app.core.secrets import decrypt_secret
from app.core.system_scripts import RUSTDESK_KEY, SYSTEM_SCRIPTS, seed_system_scripts
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
    if spec["platform"] == "windows":
        assert "x''; evil" in text  # quoted for PowerShell
    if spec["system_key"].startswith("rustdesk_install"):
        assert RUSTDESK_KEY in text and "RUSTDESK_ID=" in text


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


async def _run(machine, outcome):
    await seed_system_scripts()
    async with AsyncSessionLocal() as db:
        script = (await db.execute(select(HostScript).where(HostScript.system_key == "rustdesk_password:windows"))).scalar_one()
        values = {"RUSTDESK_PASSWORD": "Nova#Senha2026"}
        command, shell, secrets = exec_routes.prepare_script_run(script, values)

        async def bridge(server, shell_, body, timeout):
            assert "$RUSTDESK_PASSWORD = 'Nova#Senha2026'" in body
            return outcome

        with patch.object(host_exec_runner, "call_bridge_exec", bridge):
            execution = await exec_routes.launch_execution(
                db, servers=[await db.get(Server, machine.id)], command=command, shell=shell, timeout_seconds=60,
                actor="t", target_summary="rd-test", secrets=secrets, script=script, values_for_hook=values)
            await asyncio.wait_for(host_exec_runner._running[execution.id], timeout=10)
    return execution


@pytest.mark.asyncio
async def test_rustdesk_password_recorded_only_after_success(machine):
    await _run(machine, {"exit_code": 1, "stdout": "", "stderr": "recusou", "duration_ms": 1, "failure": "command"})
    async with AsyncSessionLocal() as db:
        assert (await db.get(Server, machine.id)).rustdesk_password_encrypted is None

    execution = await _run(machine, {"exit_code": 0, "stdout": "RUSTDESK_ID=123456789\n", "stderr": "", "duration_ms": 1, "failure": None})
    async with AsyncSessionLocal() as db:
        row = await db.get(Server, machine.id)
        assert row.rustdesk_id == "123456789"
        assert decrypt_secret(row.rustdesk_password_encrypted) == "Nova#Senha2026"
        detail = await exec_routes._detail(db, await db.get(HostExecution, execution.id))
    assert "Nova#Senha2026" not in detail.command  # secret parameter masked in the stored command

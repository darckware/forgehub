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
    # A patterned parameter gets a valid sample (its pattern refuses the quote test).
    samples = {"ALVO_HOST": "srv.example.test", "ALVO_PORTA": "22"}
    values = {p["name"]: samples.get(p["name"], "x'; evil") for p in params if p["required"] and not p["default"]}
    resolved, _ = resolve_values(params, values)
    text = render_script(spec["platform"], spec["content"], resolved)
    # No control character but newline/tab: a stray "\r" in a Python
    # template once turned 'RustDesk\rustdesk.exe' into a broken path.
    assert not [c for c in text if ord(c) < 32 and c not in "\n\t"]
    if spec["platform"] == "windows" and "x'; evil" in values.values():
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


@pytest.mark.asyncio
async def test_get_rustdesk_id_records_only_the_id(machine):
    await seed_system_scripts()
    async with AsyncSessionLocal() as db:
        script = (await db.execute(select(HostScript).where(HostScript.system_key == "rustdesk_get_id:windows"))).scalar_one()
        assert script.risk == "read" and script.parameters == []
        command, shell, secrets = await exec_routes.prepare_script_run(script, {})

        async def bridge(server, shell_, body, timeout):
            assert "--get-id" in body
            return {"exit_code": 0, "stdout": "Servico RustDesk: Running\nRUSTDESK_ID=987654321\n", "stderr": "", "duration_ms": 1, "failure": None}

        with patch.object(host_exec_runner, "call_bridge_exec", bridge), patch.object(exec_routes, "vault_store", _fake_store):
            execution = await exec_routes.launch_execution(
                db, servers=[await db.get(Server, machine.id)], command=command, shell=shell, timeout_seconds=60,
                actor="t", target_summary="rd-test", secrets=secrets, script=script, values_for_hook={})
            await asyncio.wait_for(host_exec_runner._running[execution.id], timeout=10)
    async with AsyncSessionLocal() as db:
        row = await db.get(Server, machine.id)
        assert row.rustdesk_id == "987654321" and row.rustdesk_password_ref is None


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


def test_windows_paths_survive_python_escapes():
    """A path like 'RustDesk\\rustdesk.exe' written in a non-raw template
    turns "\\r" into a line break; every quoted Windows path stays on one line."""
    import re

    for spec in SYSTEM_SCRIPTS:
        if spec["platform"] != "windows":
            continue
        for match in re.finditer(r"'(?:[A-Za-z]:|HKLM:|RustDesk|Tailscale)[^']*'", spec["content"]):
            assert "\n" not in match.group(0), (spec["system_key"], match.group(0))
    fw = next(s for s in SYSTEM_SCRIPTS if s["system_key"] == "rustdesk_firewall:windows")
    assert "'RustDesk\\rustdesk.exe'" in fw["content"]


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


# ---- Read-only monitoring scripts (2026-11-11) ----

from app.core.system_scripts import MONITORING_SCRIPTS  # noqa: E402

_MONITORING_KINDS = ("monitor_state", "monitor_services", "monitor_containers", "monitor_logs", "monitor_network",
                     "monitor_reachability")
# Opens a connection to another host: not read-only (Marcelo, 2026-11-11).
_NOT_READ = {"monitor_reachability"}


def test_monitoring_scripts_are_read_only_on_both_platforms():
    import re

    keys = {s["system_key"] for s in MONITORING_SCRIPTS}
    assert keys == {f"{k}:{p}" for k in _MONITORING_KINDS for p in ("linux", "windows")}
    for spec in MONITORING_SCRIPTS:
        kind = spec["system_key"].split(":")[0]
        assert spec["risk"] == ("change" if kind in _NOT_READ else "read"), spec["system_key"]
        assert spec["category"] == "monitoramento", spec["system_key"]
        params = validate_parameters(spec["parameters"])
        assert not any(p["secret"] or p.get("vault_secret") for p in params)
        text = spec["content"].lower()
        # No elevation, nothing started, stopped or restarted.
        # ("sudo" only appears as a journal unit the logs script refuses.)
        assert not re.search(r"\bsudo\s", text) and "$sudo" not in text and "runas" not in text
        for verb in ("systemctl start", "systemctl stop", "systemctl restart", "start-service", "stop-service",
                     "restart-service", "docker start", "docker stop", "docker restart", "docker rm", "rm -"):
            assert verb not in text, (spec["system_key"], verb)
    assert all(s in SYSTEM_SCRIPTS for s in MONITORING_SCRIPTS)


def _monitoring(key):
    spec = next(s for s in MONITORING_SCRIPTS if s["system_key"] == key)
    return spec, validate_parameters(spec["parameters"])


@pytest.mark.parametrize("values", [
    {"ORIGEM": "arquivo", "ARQUIVO": "/etc/shadow"},
    {"ORIGEM": "arquivo", "ARQUIVO": "/var/log/syslog"},  # names from the list only, never a path
    {"ORIGEM": "arquivo", "ARQUIVO": "../../etc/shadow"},
    {"ORIGEM": "arquivo", "ARQUIVO": "auth.log"},
    {"ORIGEM": "arquivo", "ARQUIVO": "secure"},
    {"ORIGEM": "arquivo", "ARQUIVO": "wtmp"},
    {"ORIGEM": "arquivo", "ARQUIVO": "syslog; cat /etc/shadow"},
    {"ORIGEM": "servico", "SERVICO": "nginx", "LINHAS": "0"},
    {"ORIGEM": "servico", "SERVICO": "nginx", "LINHAS": "501"},
    {"ORIGEM": "servico", "SERVICO": "nginx", "LINHAS": "abc"},
    {"ORIGEM": "servico", "SERVICO": "nginx", "LINHAS": "5\n"},
    {"ORIGEM": "servico", "SERVICO": "-n1 --system"},
    {"ORIGEM": "servico", "SERVICO": "sshd"},
    {"ORIGEM": "servico", "SERVICO": "ssh.service"},
    {"ORIGEM": "servico", "SERVICO": "sshd@1-10.0.0.1:22.service"},
    {"ORIGEM": "servico", "SERVICO": "sudo"},
    {"ORIGEM": "servico", "SERVICO": "systemd-logind.service"},
    {"ORIGEM": "servico", "SERVICO": "pam-auth-helper"},
    {"ORIGEM": "servico", "SERVICO": "cron"},
    {"ORIGEM": "servico", "SERVICO": "crond.service"},
    {"ORIGEM": "servico", "SERVICO": "anacron"},
    {"ORIGEM": "tudo"},
])
def test_log_parameters_are_refused_before_running(values):
    _, params = _monitoring("monitor_logs:linux")
    with pytest.raises(ScriptError):
        resolve_values(params, values)


def test_log_file_list_never_holds_login_or_elevation_logs():
    from app.core.system_scripts import LINUX_LOG_FILES, WINDOWS_EVENT_LOGS

    for name in LINUX_LOG_FILES:
        assert not name.startswith("/") and ".." not in name
        assert not any(bad in name for bad in ("auth", "secure", "sudo", "wtmp", "btmp", "lastlog"))
    assert WINDOWS_EVENT_LOGS == ["System", "Application", "Setup"]


@pytest.mark.parametrize("values,message", [
    ({"ORIGEM": "arquivo", "ARQUIVO": "/etc/shadow", "LINHAS": "10"}, "fora da lista"),
    ({"ORIGEM": "arquivo", "ARQUIVO": "../etc/shadow", "LINHAS": "10"}, "fora da lista"),
    ({"ORIGEM": "arquivo", "ARQUIVO": "auth.log", "LINHAS": "10"}, "fora da lista"),
    ({"ORIGEM": "servico", "SERVICO": "nginx", "LINHAS": "501"}, "1 a 500"),
    ({"ORIGEM": "servico", "SERVICO": "nginx", "LINHAS": "0"}, "1 a 500"),
    ({"ORIGEM": "servico", "SERVICO": "-x", "LINHAS": "5"}, "invalido"),
    ({"ORIGEM": "servico", "SERVICO": "sshd.service", "LINHAS": "5"}, "nao e lido"),
    ({"ORIGEM": "servico", "SERVICO": "ssh@x.service", "LINHAS": "5"}, "nao e lido"),
    ({"ORIGEM": "servico", "SERVICO": "systemd-logind", "LINHAS": "5"}, "nao e lido"),
    ({"ORIGEM": "servico", "SERVICO": "my-Auth-proxy", "LINHAS": "5"}, "nao e lido"),
    ({"ORIGEM": "servico", "SERVICO": "cron.service", "LINHAS": "5"}, "nao e lido"),
    ({"ORIGEM": "servico", "SERVICO": "crond", "LINHAS": "5"}, "nao e lido"),
])
def test_log_script_validates_again_when_pasted(values, message):
    """The script also stands alone (a console paste skips ForgeHub's check):
    rendered with the raw values, it refuses before reading anything."""
    import subprocess

    spec, _ = _monitoring("monitor_logs:linux")
    text = render_script("linux", spec["content"], values)
    done = subprocess.run(["sh", "-s"], input=text, capture_output=True, text=True, timeout=10)
    assert done.returncode == 2 and message in done.stderr
    assert done.stdout == ""  # nothing was read


def test_log_file_read_is_bounded_and_goes_through_the_resolved_path():
    spec, _ = _monitoring("monitor_logs:linux")
    assert 'tail -c 1048576 < "$REAL" | grep -viE \'(ana)?cron(d|ie)?\\[\' | tail -n "$LINHAS"' in spec["content"]


def test_service_and_container_scripts_print_no_command_lines():
    services = _monitoring("monitor_services:linux")[0]["content"]
    assert "systemctl status" not in services and "systemctl show -p LoadState,ActiveState,SubState" in services
    windows = _monitoring("monitor_services:windows")[0]["content"]
    assert "Win32_Service" not in windows and "PathName" not in windows and "BinaryPathName" not in windows
    for platform in ("linux", "windows"):
        assert "docker inspect --type container" in _monitoring(f"monitor_containers:{platform}")[0]["content"]


def test_windows_checks_are_anchored_at_the_very_end():
    """PowerShell's `$` also matches before a trailing newline: in-script checks use \\z."""
    import re

    for spec in MONITORING_SCRIPTS:
        if spec["platform"] == "windows":
            assert not re.search(r"-c?notmatch '[^']*\$'", spec["content"]), spec["system_key"]
            assert " -notmatch " not in spec["content"]


@pytest.mark.parametrize("key,values", [
    ("monitor_reachability:linux", {"ALVO_HOST": "a b", "ALVO_PORTA": "22"}),
    ("monitor_reachability:linux", {"ALVO_HOST": "srv", "ALVO_PORTA": "70000"}),
    ("monitor_reachability:linux", {"ALVO_HOST": "srv", "ALVO_PORTA": "0"}),
    ("monitor_reachability:linux", {"ALVO_HOST": "srv", "ALVO_PORTA": "22", "TEMPO_LIMITE": "11"}),
    ("monitor_reachability:linux", {"ALVO_HOST": "fe80::1", "ALVO_PORTA": "22"}),
    ("monitor_reachability:linux", {"ALVO_HOST": "10.0.0.0/24", "ALVO_PORTA": "22"}),
    ("monitor_reachability:linux", {"ALVO_HOST": "10.0.0.1-20", "ALVO_PORTA": "22"}),
    ("monitor_reachability:linux", {"ALVO_HOST": "a.test,b.test", "ALVO_PORTA": "22"}),
    ("monitor_reachability:windows", {"ALVO_HOST": "300.1.1.1", "ALVO_PORTA": "22"}),
    ("monitor_services:linux", {"SERVICO": "nginx; reboot"}),
    ("monitor_services:windows", {"SERVICO": "Spool'er"}),
    ("monitor_containers:linux", {"CONTAINER": "$(id)"}),
    ("monitor_logs:windows", {"LOG_EVENTOS": "System", "LINHAS": "1000"}),
    ("monitor_logs:windows", {"LOG_EVENTOS": "Security"}),
    ("monitor_logs:windows", {"LOG_EVENTOS": "Microsoft-Windows-PowerShell/Operational"}),
    ("monitor_logs:windows", {"LOG_EVENTOS": "Windows PowerShell"}),
])
def test_monitoring_parameters_are_validated(key, values):
    _, params = _monitoring(key)
    with pytest.raises(ScriptError):
        resolve_values(params, values)


@pytest.mark.parametrize("key,values", [
    ("monitor_logs:linux", {"ORIGEM": "arquivo", "ARQUIVO": "nginx/error.log", "LINHAS": "500"}),
    ("monitor_logs:linux", {"SERVICO": "nginx.service"}),
    ("monitor_logs:linux", {"SERVICO": "sssd"}),
    ("monitor_logs:windows", {"LOG_EVENTOS": "Application", "LINHAS": "1"}),
    ("monitor_reachability:linux", {"ALVO_HOST": "10.0.0.9", "ALVO_PORTA": "65535", "TEMPO_LIMITE": "10"}),
    ("monitor_reachability:windows", {"ALVO_HOST": "srv-app02.example.test", "ALVO_PORTA": "1"}),
    ("monitor_services:windows", {"SERVICO": "MSSQL$SQLEXPRESS"}),
    ("monitor_containers:linux", {"CONTAINER": "forgehub_test_postgres"}),
])
def test_monitoring_accepts_valid_values(key, values):
    spec, params = _monitoring(key)
    resolved, secrets = resolve_values(params, values)
    assert secrets == []
    text = render_script(spec["platform"], spec["content"], resolved)
    assert not [c for c in text if ord(c) < 32 and c not in "\n\t"]


def test_parameter_pattern_is_validated_when_declared():
    with pytest.raises(ScriptError):
        validate_parameters([{"name": "N", "pattern": "("}])
    with pytest.raises(ScriptError):
        validate_parameters([{"name": "N", "pattern": "[0-9]+", "default": "abc"}])
    params = validate_parameters([{"name": "N", "pattern": "[0-9]+", "default": "5"}, {"name": "P"}])
    assert params[0]["pattern"] == "[0-9]+" and "pattern" not in params[1]
    assert resolve_values(params, {"N": "12"})[0]["N"] == "12" and resolve_values(params, {})[0]["N"] == "5"
    with pytest.raises(ScriptError):
        resolve_values(params, {"N": "12a"})  # the whole value must match
    with pytest.raises(ScriptError):
        resolve_values(params, {"N": "1" * 1025})  # too long: refused before the regex runs
    assert resolve_values(params, {"N": "1" * 1024})[0]["N"] == "1" * 1024
    with pytest.raises(ScriptError):
        validate_parameters([{"name": "N", "pattern": "[0-9]+", "default": "1" * 1025}])
    # Unpatterned values keep their old behaviour (no cap).
    assert len(resolve_values(params, {"P": "x" * 5000})[0]["P"]) == 5000


@pytest.mark.asyncio
async def test_seed_adds_the_monitoring_category_and_scripts_once():
    from app.db.models.host_script import HostScriptCategory

    await seed_system_scripts()
    assert await seed_system_scripts() == 0
    async with AsyncSessionLocal() as db:
        category = await db.scalar(select(HostScriptCategory).where(HostScriptCategory.slug == "monitoramento"))
        assert category is not None and category.label == "Monitoramento"
        rows = (await db.execute(select(HostScript).where(
            HostScript.system_key.in_([s["system_key"] for s in MONITORING_SCRIPTS])))).scalars().all()
    assert len(rows) == len(MONITORING_SCRIPTS)  # one row each, never duplicated
    assert all(r.category_id == category.id and r.is_system for r in rows)
    assert {r.system_key for r in rows if r.risk != "read"} == {"monitor_reachability:linux", "monitor_reachability:windows"}
    ports = next(r for r in rows if r.system_key == "monitor_network:linux")
    assert ports.parameters == [] and "nc " not in ports.content and "/dev/tcp" not in ports.content
    logs = next(r for r in rows if r.system_key == "monitor_logs:linux")
    assert {p["name"]: p.get("options") for p in logs.parameters}["ARQUIVO"][0] == "syslog"


def test_log_file_mode_drops_cron_lines(tmp_path):
    """Cron lines in syslog carry job command lines (secrets): the file mode
    removes them before taking the last N lines (Marcelo, 2026-11-11)."""
    import subprocess

    spec, _ = _monitoring("monitor_logs:linux")
    text = render_script("linux", spec["content"], {"ORIGEM": "arquivo", "ARQUIVO": "syslog", "LINHAS": "10"})
    sample = tmp_path / "syslog"
    sample.write_text(
        "Nov 11 10:00:01 h CRON[123]: (root) CMD (backup --password=s3cret)\n"
        "Nov 11 10:00:02 h crond[9]: (root) CMD (x)\n"
        "Nov 11 10:00:03 h anacron[7]: Job started\n"
        "Nov 11 10:00:04 h systemd[1]: Started nginx.service\n"
    )
    text = text.replace('"/var/log/$ARQUIVO"', f'"{sample}"').replace("/var/log/*)", f"{tmp_path}/*)")
    done = subprocess.run(["sh", "-s"], input=text, capture_output=True, text=True, timeout=10)
    assert done.returncode == 0, done.stderr
    assert done.stdout == "Nov 11 10:00:04 h systemd[1]: Started nginx.service\n"

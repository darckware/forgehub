"""Offline catalog checks and execution with absent/unavailable Linux tools."""
import os
from pathlib import Path
import subprocess

import pytest

from app.core.host_scripts import render_script, validate_parameters
from app.core.system_scripts import SYSTEM_SCRIPTS


@pytest.mark.parametrize("platform,extension", [("windows", "ps1"), ("linux", "sh")])
def test_diagnostics_are_read_only_standalone_catalog_assets(platform, extension):
    matches = [s for s in SYSTEM_SCRIPTS if s["system_key"] == f"ssh_diagnostic:{platform}"]
    assert len(matches) == 1
    spec = matches[0]
    assert spec["risk"] == "read"
    assert spec["category"] == "acesso_remoto"
    assert validate_parameters(spec["parameters"]) == []
    asset = Path(__file__).parents[1] / "app/core/script_assets" / f"diagnose_ssh.{extension}"
    assert spec["content"] == asset.read_text()
    rendered = render_script(platform, spec["content"], {})
    assert "FORGEHUB_SSH_DIAGNOSTIC_V1" in rendered
    assert "FIM_DO_DIAGNOSTICO" in rendered
    assert not [c for c in rendered if ord(c) < 32 and c not in "\n\t"]


@pytest.mark.parametrize("failure", [False, True])
def test_linux_diagnostic_finishes_when_tools_absent_or_queries_fail(tmp_path, failure):
    spec = next((s for s in SYSTEM_SCRIPTS if s["system_key"] == "ssh_diagnostic:linux"), None)
    assert spec is not None, "Linux diagnostic not registered"
    if failure:
        for tool in ("id", "systemctl", "ss", "getent", "stat", "awk", "ufw", "firewall-cmd", "ip", "date", "hostname"):
            wrapper = tmp_path / tool
            wrapper.write_text("#!/bin/sh\necho SENSITIVE_ERROR >&2\nexit 1\n")
            wrapper.chmod(0o700)
    result = subprocess.run(["/bin/sh"], input=spec["content"], text=True, capture_output=True,
                            env={**os.environ, "PATH": str(tmp_path)}, timeout=10)
    assert result.returncode == 0
    assert "FIM_DO_DIAGNOSTICO" in result.stdout
    assert "NAO_VERIFICADO" in result.stdout
    assert "SENSITIVE_ERROR" not in result.stdout + result.stderr
    assert "BEGIN OPENSSH PRIVATE KEY" not in result.stdout


def test_linux_diagnostic_reports_account_metadata_without_reading_authorized_keys(tmp_path):
    spec = next(s for s in SYSTEM_SCRIPTS if s["system_key"] == "ssh_diagnostic:linux")
    home = tmp_path / "home"
    (home / ".ssh").mkdir(parents=True)
    key_file = home / ".ssh/authorized_keys"
    key_file.write_text("DO_NOT_DISCLOSE_KEY_CONTENT\n")
    tools_dir = tmp_path / "bin"
    tools_dir.mkdir()
    import shutil

    for tool in ("cut", "stat"):
        (tools_dir / tool).symlink_to(shutil.which(tool))
    stubs = {
        "id": 'if [ "$1" = -u ]; then echo 0; else echo "uid=1234(darckware)"; fi',
        "getent": f"echo 'darckware:x:1234:1234::{home}:/bin/bash'",
        "sshd": 'test "$1" = -t',
        "systemctl": 'echo "ActiveState=active"',
        "ss": 'echo "LISTEN 0 128 100.64.1.2:22 0.0.0.0:*"',
    }
    for tool, content in stubs.items():
        executable = tools_dir / tool
        executable.write_text(f"#!/bin/sh\n{content}\n")
        executable.chmod(0o700)
    result = subprocess.run(["/bin/sh"], input=spec["content"], text=True, capture_output=True,
                            env={**os.environ, "PATH": str(tools_dir)}, timeout=10)
    assert result.returncode == 0
    assert "Configuracao padrao sshd: valida" in result.stdout
    assert "ActiveState=active" in result.stdout
    assert "100.64.1.2:22" in result.stdout
    assert "authorized_keys | modo=" in result.stdout
    assert "DO_NOT_DISCLOSE_KEY_CONTENT" not in result.stdout + result.stderr
    assert key_file.read_text() == "DO_NOT_DISCLOSE_KEY_CONTENT\n"
    assert "FIM_DO_DIAGNOSTICO" in result.stdout

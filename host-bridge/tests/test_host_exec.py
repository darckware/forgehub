"""host_exec.py: the real subprocess/capping/timeout path, with `ssh` swapped
for a local shell so the script runs for real and only the transport is fake."""

from __future__ import annotations

import asyncio
import base64
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import host_exec  # noqa: E402

TOKEN = "test-token"
TARGET = host_exec.ExecTarget(host="ws01.example", user="darckware")


def _local(target, shell, script):
    return ["sh", "-s"], script.encode()


def run(script: str, timeout: float = 10.0) -> dict:
    return asyncio.run(host_exec.run_script(TARGET, "sh", script, timeout, build=_local))


def test_success_captures_stdout_and_exit_code():
    result = run("echo hello; echo oops >&2")
    assert result["exit_code"] == 0
    assert result["stdout"] == "hello\n"
    assert result["stderr"] == "oops\n"
    assert result["failure"] is None


def test_nonzero_exit_is_a_command_failure():
    result = run("exit 3")
    assert result["exit_code"] == 3
    assert result["failure"] == "command"


def test_timeout_kills_and_reports():
    result = run("sleep 5", timeout=0.5)
    assert result["timed_out"] is True
    assert result["exit_code"] is None
    assert result["failure"] == "timeout"


def test_output_is_capped(monkeypatch):
    monkeypatch.setattr(host_exec, "MAX_OUTPUT_BYTES", 100)
    result = run("head -c 5000 /dev/zero | tr '\\0' 'x'")
    assert len(result["stdout"]) == 100
    assert result["truncated"] is True
    assert result["exit_code"] == 0


def test_ssh_255_is_classified():
    assert host_exec.classify_failure(255, "Permission denied (publickey).", False) == "auth"
    assert host_exec.classify_failure(255, "ssh: connect to host x port 22: No route to host", False) == "connection"


def test_build_command_sh_sends_script_on_stdin():
    argv, stdin = host_exec.build_command(TARGET, "sh", "echo $HOME")
    assert argv[-1] == "sh -s" and argv[-2] == "darckware@ws01.example"
    assert "BatchMode=yes" in argv
    assert stdin == b"echo $HOME"


def test_build_command_powershell_is_encoded_and_bounded():
    argv, stdin = host_exec.build_command(TARGET, "powershell", "Get-Date; 'a \"b\" c'")
    assert stdin is None
    encoded = argv[-1].rsplit(" ", 1)[-1]
    decoded = base64.b64decode(encoded).decode("utf-16-le")
    assert decoded == host_exec.POWERSHELL_PRELUDE + "Get-Date; 'a \"b\" c'"
    with pytest.raises(ValueError):
        host_exec.build_command(TARGET, "powershell", "x" * (host_exec.MAX_POWERSHELL_CHARS + 1))


def _check_token(token):
    if token != TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


def test_route_validates_token_and_target(monkeypatch):
    monkeypatch.setattr(host_exec, "build_command", _local)
    app = FastAPI()
    app.include_router(host_exec.make_host_exec_router(_check_token, lambda raw: raw))
    client = TestClient(app)
    body = {"host": "ws01", "user": "darckware", "shell": "sh", "script": "echo ok"}
    assert client.post("/v1/servers/exec", json=body).status_code == 401
    assert client.post("/v1/servers/exec", json={**body, "host": "-oProxyCommand=x"},
                       headers={"X-Bridge-Token": TOKEN}).status_code == 400
    ok = client.post("/v1/servers/exec", json=body, headers={"X-Bridge-Token": TOKEN})
    assert ok.status_code == 200 and ok.json()["stdout"] == "ok\n"


def test_decode_clixml_keeps_only_errors():
    raw = (
        '#< CLIXML\n<Objs Version="1.1.0.1" xmlns="http://schemas.microsoft.com/powershell/2004/04">'
        '<Obj S="progress" RefId="0"><TN RefId="0"><T>System.Object</T></TN><MS><PR N="Record">'
        '<AV>Preparando m\u00f3dulos para primeiro uso.</AV></PR></MS></Obj>'
        '<S S="Error">Get-Item : acesso negado_x000D__x000A_</S>'
        '<S S="Error">No linha:1 caractere:1 &amp; mais_x000D__x000A_</S></Objs>'
    )
    assert host_exec.decode_clixml(raw) == "Get-Item : acesso negado\nNo linha:1 caractere:1 & mais\n"
    assert host_exec.decode_clixml("plain error\n") == "plain error\n"
    progress_only = '#< CLIXML\n<Objs><Obj S="progress"><AV>x</AV></Obj></Objs>'
    assert host_exec.decode_clixml(progress_only) == ""


def test_long_powershell_is_uploaded_in_chunks_that_fit_cmd():
    script = "Write-Output 'manutenção ação'\n" * 400  # ~13 KB, accents included
    commands, path = host_exec.powershell_upload_commands(script, token="abc")
    assert path.endswith("forgehub-abc.ps1") and len(commands) > 2
    rebuilt = b""
    for remote in commands[:-1]:
        assert len(remote) < 8191  # cmd.exe command-line limit
        inner = base64.b64decode(remote.rsplit(" ", 1)[-1]).decode("utf-16-le")
        chunk = inner.split("FromBase64String('", 1)[1].split("')", 1)[0]
        rebuilt += base64.b64decode(chunk)
    assert rebuilt.decode("utf-8") == host_exec.POWERSHELL_PRELUDE + script
    final = base64.b64decode(commands[-1].rsplit(" ", 1)[-1]).decode("utf-16-le")
    assert "-File" in final and "Remove-Item" in final and "exit $c" in final


def test_password_target_uses_sshpass_and_never_puts_password_in_argv():
    target = host_exec.ExecTarget(host="ws01", user="administrador", password="S3cr3t!")
    argv = host_exec.ssh_base(target)
    assert argv[:3] == ["sshpass", "-e", "ssh"] and "S3cr3t!" not in " ".join(argv)
    assert "PubkeyAuthentication=no" in argv and "BatchMode=no" in argv
    assert host_exec._env_for(target)["SSHPASS"] == "S3cr3t!"
    assert "S3cr3t!" not in repr(target)
    assert host_exec._env_for(TARGET) is None


def test_run_script_uploads_long_powershell_then_runs(monkeypatch):
    calls = []

    async def fake_exec(argv, stdin, timeout, env):
        calls.append(argv[-1])
        return 0, b"done", b"", False, False

    monkeypatch.setattr(host_exec, "_exec_once", fake_exec)
    result = asyncio.run(host_exec.run_script(TARGET, "powershell", "x" * 5000, 60))
    assert result["exit_code"] == 0 and result["stdout"] == "done"
    assert len(calls) == len(host_exec.powershell_upload_commands("x" * 5000)[0])


def test_detect_os(monkeypatch):
    answers = {"uname -s": (0, b"Linux\n")}

    async def fake_exec(argv, stdin, timeout, env):
        code, out = answers.get(argv[-1], (0, b"Microsoft Windows NT 10.0.26300.0\n"))
        return code, out, b"", False, False

    monkeypatch.setattr(host_exec, "_exec_once", fake_exec)
    assert asyncio.run(host_exec.detect_os(TARGET))["os_family"] == "linux"
    answers["uname -s"] = (1, b"")
    assert asyncio.run(host_exec.detect_os(TARGET)) == {"os_family": "windows", "detail": "Microsoft Windows NT 10.0.26300.0"}

    async def refused(argv, stdin, timeout, env):
        return 255, b"", b"Permission denied (password).", False, False

    monkeypatch.setattr(host_exec, "_exec_once", refused)
    with pytest.raises(ValueError, match="auth"):
        asyncio.run(host_exec.detect_os(TARGET))


def test_ephemeral_agent_holds_the_key_only_inside_the_block(tmp_path):
    import os
    import subprocess

    keyfile = tmp_path / "k"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(keyfile)], check=True)
    private_key = keyfile.read_text()

    async def scenario():
        async with host_exec.ephemeral_agent(private_key) as sock:
            listed = subprocess.run(["ssh-add", "-l"], env={**os.environ, "SSH_AUTH_SOCK": sock},
                                    capture_output=True, text=True)
            return sock, listed.returncode, listed.stdout

    sock, code, out = asyncio.run(scenario())
    assert code == 0 and "ED25519" in out
    assert not os.path.exists(sock) and not os.path.exists(os.path.dirname(sock))


def test_route_uses_the_vault_key_through_an_agent(monkeypatch):
    seen = {}

    async def fake_run(target, shell, script, timeout, **kw):
        seen["target"] = target
        return {"exit_code": 0, "stdout": "ok", "stderr": "", "truncated": False, "timed_out": False, "duration_ms": 1, "failure": None}

    import contextlib as _c

    @_c.asynccontextmanager
    async def fake_agent(private_key):
        seen["key"] = private_key
        yield "/dev/shm/fake.sock"

    async def reveal(ref):
        return "PRIVATE-KEY-FROM-VAULT"

    monkeypatch.setattr(host_exec, "run_script", fake_run)
    monkeypatch.setattr(host_exec, "ephemeral_agent", fake_agent)
    app = FastAPI()
    app.include_router(host_exec.make_host_exec_router(_check_token, lambda raw: raw, reveal))
    client = TestClient(app)
    ref = "12345678-1234-1234-1234-123456789012"
    resp = client.post("/v1/servers/exec", json={"host": "ws01", "user": "darckware", "shell": "sh", "script": "uptime", "key_ref": ref},
                       headers={"X-Bridge-Token": TOKEN})
    assert resp.status_code == 200
    assert seen["key"] == "PRIVATE-KEY-FROM-VAULT"
    assert seen["target"].agent_sock == "/dev/shm/fake.sock" and seen["target"].key is None
    assert "IdentityAgent=/dev/shm/fake.sock" in " ".join(host_exec.ssh_base(seen["target"]))


def test_agent_cache_reuses_per_key_and_reaps_idle(tmp_path):
    import os
    import subprocess

    keyfile = tmp_path / "k"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(keyfile)], check=True)
    reveals = []

    async def reveal(ref):
        reveals.append(ref)
        return keyfile.read_text()

    async def scenario():
        cache = host_exec.AgentCache(reveal, ttl=0.0)
        first = await cache.socket_for("ref-1")
        second = await cache.socket_for("ref-1")
        listed = subprocess.run(["ssh-add", "-l"], env={**os.environ, "SSH_AUTH_SOCK": first}, capture_output=True, text=True)
        reaped = await cache.reap_idle()
        return first, second, listed.returncode, reaped

    first, second, code, reaped = asyncio.run(scenario())
    assert first == second and reveals == ["ref-1"]  # one agent, one vault read
    assert code == 0 and reaped == 1
    assert not os.path.exists(first)

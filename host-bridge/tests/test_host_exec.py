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

import os
import sys
import asyncio
import importlib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_runtime import resolve_runtime_executable


@pytest.mark.parametrize("kind", ["relative", "missing", "file", "denied"])
def test_working_directory_rejects_invalid_targets(tmp_path, monkeypatch, kind):
    import agent_runtime
    target = tmp_path / "project"
    if kind == "relative":
        target = Path("relative/project")
    elif kind == "file":
        target.write_text("not a directory")
    elif kind == "denied":
        target.mkdir()
        monkeypatch.setattr(agent_runtime.os, "access", lambda *_: False)
    with pytest.raises(ValueError):
        agent_runtime.validate_working_directory(str(target))


def test_working_directory_preserves_explicit_target(tmp_path):
    import agent_runtime
    assert agent_runtime.validate_working_directory(str(tmp_path)) == tmp_path


def test_runtime_executable_prefers_explicit_configuration(tmp_path: Path) -> None:
    configured = tmp_path / "codex-custom"
    configured.write_text("#!/bin/sh\n", encoding="utf-8")
    configured.chmod(0o700)

    resolved = resolve_runtime_executable(
        "codex",
        env={"FORGEHUB_CODEX_BIN": str(configured), "PATH": ""},
    )

    assert resolved == str(configured)


def test_runtime_executable_falls_back_to_path(tmp_path: Path) -> None:
    executable = tmp_path / "codex"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o700)

    resolved = resolve_runtime_executable(
        "codex",
        env={"PATH": str(tmp_path)},
    )

    assert resolved == str(executable)


def test_runtime_executable_rejects_missing_explicit_path() -> None:
    with pytest.raises(RuntimeError, match="FORGEHUB_CODEX_BIN"):
        resolve_runtime_executable(
            "codex",
            env={"FORGEHUB_CODEX_BIN": "/missing/codex", "PATH": os.devnull},
        )


def test_health_uses_codex_resolver_and_sanitizes_resolution_failure(monkeypatch) -> None:
    monkeypatch.setenv("FORGEHUB_BRIDGE_TOKEN", "test-token")
    bridge_app = importlib.import_module("app")

    def unavailable(runtime: str, *, env=None) -> str:
        assert runtime == "codex"
        raise RuntimeError("/private/host/codex is missing")

    monkeypatch.setattr(bridge_app, "resolve_runtime_executable", unavailable)
    result = asyncio.run(bridge_app.agent_runner_health("test-token"))

    codex = result["capabilities"]["adapters"]["codex"]
    assert codex == {"available": False, "reason": "runtime executable unavailable"}


@pytest.mark.parametrize("runtime", ["claude", "codex", "agy"])
def test_external_runtimes_ignore_forgerouter_credential(monkeypatch, tmp_path, runtime) -> None:
    """A ForgeRouter key on the request must never route claude/codex/agy
    away from their own login and default model."""
    monkeypatch.setenv("FORGEHUB_BRIDGE_TOKEN", "test-token")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://localhost:2100")
    bridge_app = importlib.import_module("app")
    monkeypatch.setattr(bridge_app, "resolve_runtime_executable", lambda name, *, env=None: f"/bin/{name}")
    req = bridge_app.AgentRunRequest(
        run_id="00000000-0000-0000-0000-000000000001",
        runtime_type=runtime,
        project_path=str(tmp_path),
        prompt="do it",
        api_key="fr-secret",
    )

    command, env = bridge_app._agent_run_command(req, tmp_path)

    assert "--model" not in command
    assert not any("forgerouter" in part for part in command)
    for key in ("FORGEROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"):
        assert key not in env
    assert "fr-secret" not in env.values()


_AUTONOMY_FLAGS = {
    "claude": "--dangerously-skip-permissions",
    "codex": "--dangerously-bypass-approvals-and-sandbox",
    "agy": "--dangerously-skip-permissions",
}


def _command_for(monkeypatch, tmp_path, runtime, **fields):
    monkeypatch.setenv("FORGEHUB_BRIDGE_TOKEN", "test-token")
    bridge_app = importlib.import_module("app")
    monkeypatch.setattr(bridge_app, "resolve_runtime_executable", lambda name, *, env=None: f"/bin/{name}")
    req = bridge_app.AgentRunRequest(
        run_id="00000000-0000-0000-0000-000000000001",
        runtime_type=runtime,
        project_path=str(tmp_path),
        prompt="do it",
        **fields,
    )
    return bridge_app._agent_run_command(req, tmp_path)


@pytest.mark.parametrize("runtime", ["claude", "codex", "agy"])
def test_autonomous_execute_skips_permission_prompts(monkeypatch, tmp_path, runtime) -> None:
    """A headless run has nobody to approve a tool: autonomy must turn the
    prompt off, or the CLI auto-denies it (Dartan's review #41628)."""
    command, env = _command_for(monkeypatch, tmp_path, runtime, autonomous=True)

    assert _AUTONOMY_FLAGS[runtime] in command
    assert "--sandbox" not in command
    if runtime == "claude":
        assert "--permission-mode" not in command
        assert env["IS_SANDBOX"] == "1"


@pytest.mark.parametrize("runtime", ["claude", "codex", "agy"])
def test_without_autonomy_runs_keep_their_guards(monkeypatch, tmp_path, runtime) -> None:
    command, env = _command_for(monkeypatch, tmp_path, runtime)

    assert _AUTONOMY_FLAGS[runtime] not in command
    # Only what the bridge itself inherited, never set by the bridge.
    assert env.get("IS_SANDBOX") == os.environ.get("IS_SANDBOX")


def test_a_restricted_hermes_run_gets_only_those_tools_and_no_memory(monkeypatch, tmp_path) -> None:
    home = tmp_path / "maia"
    home.mkdir()
    bridge_app = importlib.import_module("app")
    monkeypatch.setattr(bridge_app, "Path", lambda p: tmp_path / Path(p).name if str(p).startswith("/root/.hermes") else Path(p))
    req = bridge_app.AgentRunRequest(run_id="00000000-0000-0000-0000-000000000001", runtime_type="hermes", project_path=str(tmp_path),
                                     prompt="do it", hermes_profile="profiles", restricted_toolsets="moodle")
    (tmp_path / "profiles" / "profiles").mkdir(parents=True)
    command, _ = bridge_app._agent_run_command(req, tmp_path)
    assert command[-3:] == ["-t", "moodle", "--ignore-rules"]
    plain = req.model_copy(update={"restricted_toolsets": None})
    assert "--ignore-rules" not in bridge_app._agent_run_command(plain, tmp_path)[0]


def test_strict_media_reaches_hermes_send(monkeypatch) -> None:
    monkeypatch.setenv("FORGEHUB_BRIDGE_TOKEN", "test-token")
    bridge_app = importlib.import_module("app")
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["env"] = kwargs.get("env")
        return bridge_app.subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")
    monkeypatch.setattr(bridge_app.subprocess, "run", fake_run)
    monkeypatch.setattr(bridge_app, "_check_token", lambda *_: None)
    req = bridge_app.MessageSendRequest(target="whatsapp:x@g.us", message="oi", strict_media=True)
    asyncio.run(bridge_app.send_message(req, "t"))
    assert seen["env"]["HERMES_MEDIA_DELIVERY_STRICT"] == "1"
    assert seen["env"]["HERMES_MEDIA_TRUST_RECENT_FILES"] == "0"
    asyncio.run(bridge_app.send_message(req.model_copy(update={"strict_media": False}), "t"))
    assert seen["env"] is None


def test_restricted_tools_are_refused_for_other_runtimes(monkeypatch, tmp_path) -> None:
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        _command_for(monkeypatch, tmp_path, "claude", restricted_toolsets="moodle")


def test_claude_prompt_is_not_read_as_an_mcp_config(monkeypatch, tmp_path) -> None:
    """--mcp-config takes many values: every Porthus run died on ENAMETOOLONG without the separator."""
    command, _ = _command_for(monkeypatch, tmp_path, "claude", autonomous=True)
    assert command[-2:] == ["--", "do it"]


@pytest.mark.parametrize("runtime", ["claude", "codex", "agy"])
def test_plan_mode_stays_read_only_even_when_autonomous(monkeypatch, tmp_path, runtime) -> None:
    command, _env = _command_for(monkeypatch, tmp_path, runtime, autonomous=True, mode="plan")

    assert _AUTONOMY_FLAGS[runtime] not in command
    assert "plan" in command or "read-only" in command


@pytest.mark.parametrize('mode,expected_sandbox',[('plan','read-only'),('execute','workspace-write')])
def test_codex_exec_accepts_explicit_workspace_without_git_without_broadening_permissions(tmp_path,monkeypatch,mode,expected_sandbox):
    monkeypatch.setenv('FORGEHUB_BRIDGE_TOKEN','test-token')
    monkeypatch.setenv('FORGEHUB_RUN_STATE_DIR',str(tmp_path/'run-state'))
    bridge_app=importlib.import_module('app')
    monkeypatch.setattr(bridge_app,'resolve_runtime_executable',lambda name,**kw:f'/bin/{name}')
    request=bridge_app.AgentRunRequest(run_id='00000000-0000-4000-8000-000000000001',runtime_type='codex',project_path=str(tmp_path),prompt='Inspect the explicitly supplied workspace',mode=mode)
    command,_=bridge_app._agent_run_command(request,tmp_path)
    assert '--skip-git-repo-check' in command
    assert command[command.index('--sandbox')+1]==expected_sandbox
    assert command[command.index('-C')+1]==str(tmp_path)
    assert '--dangerously-bypass-approvals-and-sandbox' not in command


def test_codex_repository_keeps_git_check(tmp_path,monkeypatch):
    monkeypatch.setenv('FORGEHUB_BRIDGE_TOKEN','test-token')
    bridge_app=importlib.import_module('app')
    monkeypatch.setattr(bridge_app,'resolve_runtime_executable',lambda name,**kw:f'/bin/{name}')
    (tmp_path/'.git').mkdir()
    (tmp_path/'.git'/'HEAD').write_text('ref: refs/heads/main\n')
    nested=tmp_path/'nested'
    nested.mkdir()
    request=bridge_app.AgentRunRequest(run_id='00000000-0000-4000-8000-000000000001',runtime_type='codex',project_path=str(nested),prompt='Inspect')
    command,_=bridge_app._agent_run_command(request,nested)
    assert '--skip-git-repo-check' not in command

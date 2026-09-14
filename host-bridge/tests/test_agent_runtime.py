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

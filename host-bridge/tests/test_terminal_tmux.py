"""Terminal sessions must invoke tmux's new-session subcommand."""

import importlib
import sys
from pathlib import Path
from subprocess import CompletedProcess


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_tmux_session_creation_uses_new_session_for_scope_and_fallback(monkeypatch):
    monkeypatch.setenv("FORGEHUB_BRIDGE_TOKEN", "test-token")
    bridge = importlib.import_module("app")
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return CompletedProcess(cmd, 1 if len(calls) == 1 else 0, "", "scope unavailable")

    monkeypatch.setattr(bridge.subprocess, "run", fake_run)
    monkeypatch.setattr(bridge, "_tmux_session_exists", lambda name: False)

    result = bridge._tmux_new_session("-d", "-s", "forgehub-test", "-x", "80", "-y", "24", "-c", "/tmp")

    assert result.returncode == 0
    expected = ["tmux", "new-session", "-d", "-s", "forgehub-test", "-x", "80", "-y", "24", "-c", "/tmp"]
    assert calls[0][-len(expected):] == expected
    assert calls[1] == expected

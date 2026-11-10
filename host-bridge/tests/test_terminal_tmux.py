"""Terminal sessions must invoke tmux's new-session subcommand."""

import importlib
import asyncio
import sys
from pathlib import Path
from subprocess import CompletedProcess

import pytest


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


def test_terminal_scope_keeps_other_sessions_alive_after_child_oom(monkeypatch):
    monkeypatch.setenv("FORGEHUB_BRIDGE_TOKEN", "test-token")
    bridge = importlib.import_module("app")
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(bridge.subprocess, "run", fake_run)
    bridge._tmux_new_session("-d", "-s", "forgehub-test")

    # systemd defaults to OOMPolicy=stop for scopes: one OOM victim then
    # terminates every pane and CLI sharing the tmux server's scope.
    assert "--property=OOMPolicy=continue" in calls[0]


@pytest.mark.asyncio
@pytest.mark.parametrize('attached,command,children', [
    (True, 'bash', ''), (False, 'codex', ''), (False, 'bash', '456'),
])
async def test_inactivity_never_kills_attached_sessions_or_running_programs(monkeypatch, attached, command, children):
    monkeypatch.setenv('FORGEHUB_BRIDGE_TOKEN', 'test-token')
    bridge = importlib.import_module('app')
    monkeypatch.setattr(bridge, 'TERMINAL_INACTIVITY_TIMEOUT_SECONDS', 1)
    monkeypatch.setattr(bridge, '_list_forgehub_tmux_sessions', lambda: [
        {'session_id': 'protected', 'last_activity_at': 0, 'attached': attached},
    ])
    killed = []
    def tmux(*args, **kwargs):
        if args[0] == 'kill-session':
            killed.append(args[-1])
        return CompletedProcess(args, 0, f'123\t{command}\t0\n', '')
    monkeypatch.setattr(bridge, '_tmux', tmux)
    monkeypatch.setattr(bridge.Path, 'read_text', lambda *args, **kwargs: children)
    async def stop_after_pass(*args):
        raise asyncio.CancelledError
    monkeypatch.setattr(bridge.asyncio, 'sleep', stop_after_pass)
    with pytest.raises(asyncio.CancelledError):
        await bridge._terminal_inactivity_sweep_loop()
    assert killed == []


@pytest.mark.asyncio
async def test_inactivity_cleanup_is_disabled_without_explicit_timeout(monkeypatch):
    monkeypatch.setenv('FORGEHUB_BRIDGE_TOKEN', 'test-token')
    bridge = importlib.import_module('app')
    monkeypatch.setattr(bridge, 'TERMINAL_INACTIVITY_TIMEOUT_SECONDS', 0)
    await bridge._start_terminal_inactivity_sweep()
    assert bridge._terminal_inactivity_sweep_task is None


@pytest.mark.parametrize("clients,expected", [("0", False), ("1", True), ("2", True)])
def test_terminal_connection_accepts_multiple_browser_clients(monkeypatch, clients, expected):
    monkeypatch.setenv("FORGEHUB_BRIDGE_TOKEN", "test-token")
    bridge = importlib.import_module("app")
    monkeypatch.setattr(bridge, "_tmux", lambda *args: CompletedProcess(args, 0, f"forgehub-test\t100\t200\t{clients}\n", ""))
    assert bridge._list_forgehub_tmux_sessions()[0]["attached"] is expected

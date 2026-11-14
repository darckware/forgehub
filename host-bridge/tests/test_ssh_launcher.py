"""The terminal launcher accepts only safe, explicitly supported SSH forms."""

import importlib
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _bridge(monkeypatch):
    monkeypatch.setenv("FORGEHUB_BRIDGE_TOKEN", "test-token")
    return importlib.import_module("app")


def test_identity_agent_socket_is_a_valid_launcher(monkeypatch):
    bridge = _bridge(monkeypatch)

    assert bridge._is_allowed_launcher_command(
        "ssh -o IdentityAgent=/dev/shm/fh-agent-abc/agent.sock darckware@172.15.2.3"
    )


def test_identity_agent_must_be_absolute_and_path_safe(monkeypatch):
    bridge = _bridge(monkeypatch)

    assert not bridge._is_allowed_launcher_command(
        "ssh -o IdentityAgent=agent.sock darckware@172.15.2.3"
    )
    assert not bridge._is_allowed_launcher_command(
        "ssh -o IdentityAgent=/tmp/$(touch-pwned) darckware@172.15.2.3"
    )


def test_dangerous_ssh_options_remain_rejected(monkeypatch):
    bridge = _bridge(monkeypatch)

    assert not bridge._is_allowed_launcher_command(
        "ssh -o ProxyCommand=sh -c id darckware@172.15.2.3"
    )

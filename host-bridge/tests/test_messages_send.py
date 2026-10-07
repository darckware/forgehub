"""/v1/messages/send usa o `hermes send` oficial, com o texto pelo stdin."""

import asyncio
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _bridge(monkeypatch, result, returncode=0):
    monkeypatch.setenv("FORGEHUB_BRIDGE_TOKEN", "test-token")
    bridge = importlib.import_module("app")
    monkeypatch.setattr(bridge, "_check_token", lambda token: None)
    monkeypatch.setattr(bridge, "_is_valid_profile", lambda profile: profile == "athos")
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return SimpleNamespace(returncode=returncode, stdout=json.dumps(result, indent=2), stderr="")

    monkeypatch.setattr(bridge.subprocess, "run", fake_run)
    return bridge, calls


def test_envia_pelo_hermes_send_do_perfil(monkeypatch):
    bridge, calls = _bridge(monkeypatch, {"success": True, "message_id": "7"})
    req = bridge.MessageSendRequest(target="telegram", message="linha 1\nlinha 2", profile="athos")

    result = asyncio.run(bridge.send_message(req, x_bridge_token="t"))

    assert result == {"success": True, "message_id": "7"}
    cmd, kwargs = calls[0]
    assert cmd == [bridge.HERMES_BIN, "-p", "athos", "send", "--to", "telegram", "--json", "--file", "-"]
    assert kwargs["input"] == "linha 1\nlinha 2"  # o texto nunca vai no argv


def test_erro_do_hermes_vira_502(monkeypatch):
    bridge, _ = _bridge(monkeypatch, {"error": "Telegram send failed: Chat not found"}, returncode=1)
    req = bridge.MessageSendRequest(target="telegram:0", message="x")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(bridge.send_message(req, x_bridge_token="t"))
    assert exc.value.status_code == 502 and "Chat not found" in exc.value.detail


def test_perfil_desconhecido_vira_404(monkeypatch):
    bridge, calls = _bridge(monkeypatch, {})
    req = bridge.MessageSendRequest(target="telegram", message="x", profile="../etc")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(bridge.send_message(req, x_bridge_token="t"))
    assert exc.value.status_code == 404 and not calls

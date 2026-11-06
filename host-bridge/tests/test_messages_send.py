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


class _Bridge:
    calls = []
    status = 200

    def __init__(self, **_): ...
    async def __aenter__(self): return self
    async def __aexit__(self, *_): ...

    async def post(self, url, json):
        _Bridge.calls.append((url, json))
        return SimpleNamespace(status_code=_Bridge.status, text="falhou", json=lambda: {"success": True, "messageId": "9"})


def _reply_setup(monkeypatch, tmp_path):
    bridge, calls = _bridge(monkeypatch, {})
    (tmp_path / "athos").mkdir()
    (tmp_path / "athos" / "config.yaml").write_text("whatsapp:\n  bridge_port: 30303\n")
    monkeypatch.setattr(bridge, "PROFILES_DIR", tmp_path)
    monkeypatch.setattr(bridge.httpx, "AsyncClient", _Bridge)
    _Bridge.calls, _Bridge.status = [], 200
    return bridge, calls


def test_resposta_citada_vai_direto_a_ponte_do_perfil(monkeypatch, tmp_path):
    bridge, calls = _reply_setup(monkeypatch, tmp_path)
    req = bridge.MessageSendRequest(target="whatsapp:1@g.us", message="oi", profile="athos", reply_to="3EB0ABC")

    assert asyncio.run(bridge.send_message(req, x_bridge_token="t"))["messageId"] == "9"
    assert _Bridge.calls == [("http://127.0.0.1:30303/send", {"chatId": "1@g.us", "message": "oi", "replyTo": "3EB0ABC"})]
    assert not calls  # nunca passa pelo `hermes send`


def test_resposta_citada_recusa_outro_canal_e_erro_vira_502(monkeypatch, tmp_path):
    bridge, _ = _reply_setup(monkeypatch, tmp_path)
    req = bridge.MessageSendRequest(target="telegram:1", message="oi", profile="athos", reply_to="3EB0ABC")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(bridge.send_message(req, x_bridge_token="t"))
    assert exc.value.status_code == 400 and not _Bridge.calls

    _Bridge.status = 503
    req = req.model_copy(update={"target": "whatsapp:1@g.us"})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(bridge.send_message(req, x_bridge_token="t"))
    assert exc.value.status_code == 502


def test_id_da_mensagem_invalido_e_recusado(monkeypatch):
    bridge, _ = _bridge(monkeypatch, {})
    with pytest.raises(ValueError):
        bridge.MessageSendRequest(target="whatsapp:1@g.us", message="oi", reply_to="../x")

"""A resposta do bridge precisa carregar o ID real criado pelo Hermes."""

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_chat_extrai_id_da_saida_do_hermes(monkeypatch, tmp_path):
    monkeypatch.setenv("FORGEHUB_BRIDGE_TOKEN", "test-token")
    bridge = importlib.import_module("app")
    monkeypatch.setattr(bridge, "_is_valid_profile", lambda profile: profile == "lara")
    monkeypatch.setattr(bridge, "_chat_cwd", lambda profile, channel: str(tmp_path))
    monkeypatch.setattr(
        bridge.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="Olá, como posso ajudar?\n",
            stderr="session_id: hermes-real-123\n",
        ),
    )

    result = bridge._run_hermes_chat(bridge.ChatRequest(profile="lara", channel="site", message="Oi"))

    assert result.reply == "Olá, como posso ajudar?"
    assert result.session_id == "hermes-real-123"


def test_chat_aplica_restricao_de_toolsets_do_canal(monkeypatch, tmp_path):
    monkeypatch.setenv("FORGEHUB_BRIDGE_TOKEN", "test-token")
    bridge = importlib.import_module("app")
    monkeypatch.setattr(bridge, "_is_valid_profile", lambda profile: profile == "lara")
    monkeypatch.setattr(bridge, "_chat_cwd", lambda profile, channel: str(tmp_path))
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        return SimpleNamespace(returncode=0, stdout="OK\n", stderr="session_id: hermes-real-456\n")

    monkeypatch.setattr(bridge.subprocess, "run", fake_run)

    result = bridge._run_hermes_chat(
        bridge.ChatRequest(profile="lara", channel="site", message="Oi", toolsets=["no_mcp"])
    )

    assert result.session_id == "hermes-real-456"
    assert "-t" in captured["args"]
    assert captured["args"][captured["args"].index("-t") + 1] == "no_mcp"

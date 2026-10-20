"""Hindsight status must reflect the daemon's effective LLM configuration."""

import asyncio
import importlib
import json
import sys
from pathlib import Path
from subprocess import CompletedProcess


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_hindsight_status_reads_container_llm_without_exposing_key(monkeypatch, tmp_path):
    monkeypatch.setenv("FORGEHUB_BRIDGE_TOKEN", "test-token")
    bridge = importlib.import_module("app")
    profile_dir = tmp_path / "profiles" / "athos"
    (profile_dir / "hindsight").mkdir(parents=True)
    (profile_dir / "config.yaml").write_text("memory:\n  provider: hindsight\n", encoding="utf-8")
    (profile_dir / "hindsight" / "config.json").write_text(
        json.dumps({"api_url": "http://localhost:8888", "mode": "local_external"}), encoding="utf-8"
    )
    monkeypatch.setattr(bridge, "HERMES_PROFILES_DIR", tmp_path / "profiles")
    monkeypatch.setattr(bridge, "HERMES_HOME_DIR", tmp_path)
    monkeypatch.setattr(bridge, "HINDSIGHT_PROFILE_DIR", tmp_path / "hindsight")
    monkeypatch.setattr(bridge, "_hindsight_processes", lambda: [])

    async def healthy(_url):
        return {"ok": True, "error": None}

    monkeypatch.setattr(bridge, "_probe_hindsight", healthy)
    monkeypatch.setattr(bridge, "read_hindsight_retention_status", lambda: {
        "mode": "preview", "review_days": 90, "compact_days": 180,
        "recovery_days": 60, "review_count": 4, "eligible_count": 0,
    })

    def inspect_container(command, **_kwargs):
        assert command == ["docker", "inspect", "--format", "{{json .Config.Env}}", "hindsight"]
        return CompletedProcess(command, 0, json.dumps([
            "HINDSIGHT_API_LLM_PROVIDER=openai",
            "HINDSIGHT_API_LLM_MODEL=forgerouter/auto",
            "HINDSIGHT_API_LLM_BASE_URL=http://forgerouter:2100/v1",
            "HINDSIGHT_API_LLM_API_KEY=super-secret",
        ]), "")

    monkeypatch.setattr(bridge.subprocess, "run", inspect_container)

    status = asyncio.run(bridge.hindsight_status(bridge.BRIDGE_TOKEN))

    assert status["llm"] == {
        "provider": "openai",
        "model": "forgerouter/auto",
        "base_url": "http://forgerouter:2100/v1",
        "api_key_present": True,
    }
    assert "super-secret" not in json.dumps(status)
    assert status["retention"]["review_count"] == 4

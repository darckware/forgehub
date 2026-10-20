import asyncio
import importlib
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_install_key_reports_missing_local_ssh_dependency(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FORGEHUB_BRIDGE_TOKEN", "test-token")
    bridge_app = importlib.import_module("app")
    monkeypatch.setattr(bridge_app, "BRIDGE_TOKEN", "test-token")
    monkeypatch.setattr(bridge_app, "SSH_KEYS_DIR", str(tmp_path))

    key_path = tmp_path / "192_0_2_10_key"
    key_path.write_text("private key fixture", encoding="utf-8")
    key_path.with_suffix(key_path.suffix + ".pub").write_text(
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest fixture",
        encoding="utf-8",
    )
    monkeypatch.setenv("PATH", "")

    request = bridge_app.InstallKeyRequest(
        ip_address="192.0.2.10",
        remote_user="alice",
        password="secret",
    )
    result = asyncio.run(bridge_app.install_server_key(request, "test-token"))

    assert result["ok"] is False
    assert result["step"] == "install"
    assert "command not found: sshpass" in result["error"]
    assert "required command" in result["error"]

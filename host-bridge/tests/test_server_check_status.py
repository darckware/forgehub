"""The SSH probe behind /v1/servers/check-status: which key it offers.

Phase 5 of docs/architecture/REMOTE_ACCESS_SERVERS_UNIFICATION_PLAN.md: a
machine whose key is in ForgeVault is probed with that key (its agent), and
the strict mode proves the vault key alone logs in before ForgeHub stops
pointing at the key file."""
import asyncio
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REF = "0b0f3c1e-1111-4222-8333-444455556666"


class _Proc:
    def __init__(self, code: int) -> None:
        self.returncode = code

    async def wait(self) -> int:
        return self.returncode


class _Writer:
    def close(self) -> None:
        pass

    async def wait_closed(self) -> None:
        pass


def _probe(monkeypatch, entry_kwargs: dict, returncode: int = 0):
    bridge_app = importlib.import_module("app")
    calls: list[tuple] = []

    async def fake_open(host, port):
        return object(), _Writer()

    async def fake_exec(*args, **kwargs):
        calls.append(args)
        return _Proc(returncode)

    async def fake_socket(ref):
        assert ref == REF
        return "/dev/shm/fh-agent-x/agent.sock"

    async def fake_identity(ref):
        assert ref == REF
        return ["-F", "/dev/null", "-o", "IdentityAgent=/s", "-i", "/s.pub", "-o", "IdentitiesOnly=yes"]

    monkeypatch.setattr(bridge_app.asyncio, "open_connection", fake_open)
    monkeypatch.setattr(bridge_app.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(bridge_app, "_agent_socket_for", fake_socket)
    monkeypatch.setattr(bridge_app, "_vault_identity_args", fake_identity)
    entry = bridge_app.ServerCheckEntry(id="m", ip_address="192.0.2.10", remote_user="aegis", **entry_kwargs)
    status = asyncio.run(bridge_app._check_one_server(entry))
    return status, calls[-1] if calls else ()


def test_key_file_is_offered_with_i(monkeypatch) -> None:
    status, args = _probe(monkeypatch, {"ssh_key_path": "/keys/k"})
    assert status == "active"
    assert "-i" in args and "/keys/k" in args
    assert "-F" not in args


def test_vault_key_wins_over_the_file(monkeypatch) -> None:
    status, args = _probe(monkeypatch, {"ssh_key_path": "/keys/k", "ssh_key_ref": REF})
    assert status == "active"
    assert "IdentityAgent=/dev/shm/fh-agent-x/agent.sock" in args
    assert "/keys/k" not in args


def test_strict_vault_probe_ignores_host_config_and_other_keys(monkeypatch) -> None:
    status, args = _probe(monkeypatch, {"ssh_key_ref": REF, "strict": True})
    assert status == "active"
    assert args[args.index("-F") + 1] == "/dev/null"
    assert "IdentitiesOnly=yes" in args


def test_refused_vault_key_reads_not_installed(monkeypatch) -> None:
    status, _ = _probe(monkeypatch, {"ssh_key_ref": REF, "strict": True}, returncode=255)
    assert status == "not_installed"


def test_unreadable_vault_key_never_reads_active(monkeypatch) -> None:
    bridge_app = importlib.import_module("app")

    async def broken(ref):
        raise ValueError("vault down")

    status, _ = _probe(monkeypatch, {"ssh_key_ref": REF, "strict": True})
    monkeypatch.setattr(bridge_app, "_vault_identity_args", broken)
    entry = bridge_app.ServerCheckEntry(id="m", ip_address="192.0.2.10", remote_user="aegis", ssh_key_ref=REF, strict=True)
    assert asyncio.run(bridge_app._check_one_server(entry)) == "not_installed"

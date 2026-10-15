from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vpn_control import VpnControl, VpnPolicyError, parse_ping, parse_prefs, parse_status  # noqa: E402


def _peer(peer_id: str, name: str, *, online: bool = True, cur_addr: str = "", relay: str = "fra", active: bool = True, **extra) -> dict:
    return {
        "ID": peer_id,
        "HostName": name.upper(),
        "DNSName": f"{name}.tail0000.ts.net.",
        "OS": "windows",
        "Tags": ["tag:gatling-users"],
        "TailscaleIPs": ["fd7a:115c:a1e0::1", f"100.82.{len(name)}.10"],
        "Online": online,
        "Active": active,
        "CurAddr": cur_addr,
        "Relay": relay,
        "RxBytes": 300,
        "TxBytes": 400,
        "LastSeen": "0001-01-01T00:00:00Z" if online else "2026-10-14T19:42:15Z",
        **extra,
    }


def _status(peers: list[dict] | None = None, *, backend_state: str = "Running") -> str:
    if peers is None:
        peers = [
            _peer("nAAA11CNTRL", "gat-adm-pc01", cur_addr="45.170.178.64:19267"),
            _peer("nBBB11CNTRL", "desk-semed-admin", online=False),
        ]
    return json.dumps(
        {
            "BackendState": backend_state,
            "Self": {
                "ID": "nSELF1CNTRL",
                "HostName": "vmi3547248",
                "DNSName": "darckware-srv.tail0000.ts.net.",
                "OS": "linux",
                "TailscaleIPs": ["100.105.235.114"],
                "Online": True,
            },
            "Peer": {f"nodekey:{index}": peer for index, peer in enumerate(peers)},
        }
    )


class RecordingRunner:
    def __init__(self, status: str | None = None, ping: str = "pong from gat-adm-pc01 (100.82.12.10) via 45.170.178.64:19267 in 34ms") -> None:
        self.calls: list[tuple[list[str], float]] = []
        self.status_json = status if status is not None else _status()
        self.ping = ping

    def __call__(self, argv: list[str], timeout: float):
        self.calls.append((argv, timeout))
        if argv[:2] == ["tailscale", "status"]:
            return _result(self.status_json)
        if argv[:2] == ["tailscale", "ping"]:
            return _result(self.ping)
        if argv[:3] == ["tailscale", "debug", "prefs"]:
            return _result(json.dumps({"CorpDNS": False, "RouteAll": False, "AdvertiseRoutes": [], "RunSSH": False, "ExitNodeID": ""}))
        if argv == ["systemctl", "is-active", "tailscaled"]:
            return _result("active\n")
        return _result("")


def _result(stdout: str, returncode: int = 0, stderr: str = ""):
    return type("Result", (), {"returncode": returncode, "stdout": stdout, "stderr": stderr})()


def test_parse_status_reads_self_and_every_peer():
    parsed = parse_status(_status())

    assert parsed["self"]["id"] == "self"
    assert parsed["self"]["name"] == "darckware-srv"
    assert parsed["self"]["state"] == "online"
    assert [peer["name"] for peer in parsed["peers"]] == ["gat-adm-pc01", "desk-semed-admin"]
    online = parsed["peers"][0]
    assert online["id"] == "nAAA11CNTRL"
    assert online["hostname"] == "GAT-ADM-PC01"
    assert online["tags"] == ["tag:gatling-users"]
    assert online["tailscale_ipv4"] == "100.82.12.10"
    assert online["connection"] == {"kind": "direct", "relay": None}
    # "0001-01-01" is Tailscale's "now"/"never", not a date.
    assert online["last_seen"] is None
    assert parsed["peers"][1]["last_seen"] == "2026-10-14T19:42:15Z"
    assert parsed["peers"][1]["connection"]["kind"] == "unavailable"


def test_parse_status_handles_payloads_far_larger_than_8kb():
    # Regression: the bridge used to cut stdout at 8 KB, which broke the JSON
    # (and the whole page) as soon as the tailnet had ~10 devices.
    peers = [_peer(f"n{index:04d}CNTRL", f"ws-{index:03d}") for index in range(150)]
    raw = _status(peers)
    assert len(raw) > 8192

    result = VpnControl(runner=RecordingRunner(status=raw)).status()

    assert "error" not in result
    assert len(result["peers"]) == 150


def test_parse_status_derp_only_when_traffic_is_flowing():
    relayed, idle = parse_status(
        _status([_peer("nAAA11CNTRL", "a", relay="fra"), _peer("nBBB11CNTRL", "b", relay="fra", active=False)])
    )["peers"]

    assert relayed["connection"] == {"kind": "derp", "relay": "fra"}
    assert idle["connection"] == {"kind": "idle", "relay": None}


def test_parse_status_drops_peers_without_a_valid_stable_id():
    parsed = parse_status(_status([_peer("../etc", "evil"), _peer("nAAA11CNTRL", "ok")]))

    assert [peer["name"] for peer in parsed["peers"]] == ["ok"]


def test_parse_status_reports_needs_login():
    assert parse_status(_status(backend_state="NeedsLogin"))["self"]["state"] == "needs_login"


def test_parse_status_rejects_malformed_json():
    with pytest.raises(ValueError, match="invalid_response"):
        parse_status("{not-json")


def test_parse_ping_normalizes_derp_and_direct_without_raw_output():
    assert parse_ping("pong from vmi3547248 (100.105.235.114) via DERP(fra) in 210ms") == {
        "success": True,
        "kind": "derp",
        "relay": "fra",
        "latency_ms": 210.0,
    }
    assert parse_ping("pong from vmi3547248 via 203.0.113.10:41641 in 34ms") == {
        "success": True,
        "kind": "direct",
        "relay": None,
        "latency_ms": 34.0,
    }


def test_parse_prefs_reports_only_restricted_posture_fields():
    assert parse_prefs(
        json.dumps({"CorpDNS": False, "RouteAll": False, "AdvertiseRoutes": [], "RunSSH": False, "ExitNodeID": ""})
    ) == {
        "accept_dns": False,
        "accept_routes": False,
        "advertise_exit_node": False,
        "tailscale_ssh": False,
        "exit_node": False,
        "restricted": True,
    }


def test_status_includes_daemon_and_posture_of_this_server():
    runner = RecordingRunner()

    result = VpnControl(runner=runner).status()

    assert result["self"]["daemon_state"] == "active"
    assert result["self"]["posture"]["restricted"] is True
    assert [call[0] for call in runner.calls[:3]] == [
        ["tailscale", "status", "--json"],
        ["systemctl", "is-active", "tailscaled"],
        ["tailscale", "debug", "prefs"],
    ]


def test_status_maps_missing_binary_to_stable_error():
    def missing_binary(_argv: list[str], _timeout: float):
        raise FileNotFoundError

    result = VpnControl(runner=missing_binary).status()

    assert result["error"]["code"] == "binary_missing"
    assert result["peers"] == []
    assert "traceback" not in json.dumps(result).lower()


def test_peer_test_resolves_address_from_fresh_status_only():
    runner = RecordingRunner()

    result = VpnControl(runner=runner).action("nAAA11CNTRL", "test")

    assert result["success"] is True
    assert result["latency_ms"] == 34.0
    assert result["kind"] == "direct"
    assert runner.calls[-1][0] == ["tailscale", "ping", "--until-direct=false", "--c", "1", "--timeout", "5s", "100.82.12.10"]


def test_peer_test_reports_offline_and_unknown_without_pinging():
    runner = RecordingRunner()
    control = VpnControl(runner=runner)

    assert control.action("nBBB11CNTRL", "test")["code"] == "peer_offline"
    assert control.action("nZZZ11CNTRL", "test")["code"] == "peer_not_found"
    assert not any(call[0][:2] == ["tailscale", "ping"] for call in runner.calls)


def test_peer_test_without_reply_is_a_failure():
    result = VpnControl(runner=RecordingRunner(ping="no reply")).action("nAAA11CNTRL", "test")

    assert result == {"success": False, "code": "no_reply", "summary": "gat-adm-pc01 did not answer.", "target_name": "gat-adm-pc01"}


@pytest.mark.parametrize(
    ("node", "action"),
    [
        ("self", "test"),
        ("self", "connect"),
        ("self", "disconnect"),
        ("nAAA11CNTRL", "restart"),
        ("local", "connect"),
        ("../../etc", "test"),
        ("100.82.12.10", "test"),
    ],
)
def test_policy_rejects_unsafe_or_unknown_actions_before_execution(node: str, action: str):
    runner = RecordingRunner()

    with pytest.raises(VpnPolicyError, match="action_not_allowed"):
        VpnControl(runner=runner).action(node, action)

    assert runner.calls == []


def test_self_restart_uses_fixed_command_and_confirms_online():
    runner = RecordingRunner()

    result = VpnControl(runner=runner).action("self", "restart")

    assert result["success"] is True
    assert runner.calls[0][0] == ["systemctl", "restart", "tailscaled"]


def test_login_url_is_replaced_by_stable_needs_login_error():
    def login_runner(argv: list[str], _timeout: float):
        return _result("To authenticate, visit https://login.tailscale.com/a/secret-value", returncode=1)

    result = VpnControl(runner=login_runner).action("self", "restart")

    assert result == {"success": False, "code": "needs_login", "summary": "Tailscale authorization is required on the host."}
    assert "login.tailscale.com" not in json.dumps(result)

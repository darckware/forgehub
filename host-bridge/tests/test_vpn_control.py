from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vpn_control import VpnControl, VpnPolicyError, parse_ping, parse_prefs, parse_status  # noqa: E402


def _status(*, relay: str = "fra", cur_addr: str = "", online: bool = True) -> str:
    return json.dumps(
        {
            "BackendState": "Running",
            "Self": {
                "HostName": "NotebookSTI-wsl",
                "TailscaleIPs": ["100.119.242.42", "fd7a:115c:a1e0::2330:f22b"],
                "Online": True,
                "Active": True,
                "CurAddr": "",
                "Relay": "",
                "RxBytes": 100,
                "TxBytes": 200,
                "LastSeen": "2026-09-03T18:00:00Z",
            },
            "Peer": {
                "node-key:unrelated": {
                    "HostName": "other-device",
                    "TailscaleIPs": ["100.64.1.9"],
                    "Online": True,
                },
                "node-key:vps": {
                    "HostName": "vmi3547248",
                    "TailscaleIPs": ["fd7a:115c:a1e0::2501:ebce", "100.105.235.114"],
                    "Online": online,
                    "Active": online,
                    "CurAddr": cur_addr,
                    "Relay": relay,
                    "RxBytes": 300,
                    "TxBytes": 400,
                    "LastSeen": "2026-09-03T18:01:00Z",
                },
            },
        }
    )


def test_parse_status_selects_authorized_nodes_and_derp_path():
    parsed = parse_status(_status())

    assert parsed["local"]["hostname"] == "NotebookSTI-wsl"
    assert parsed["local"]["tailscale_ipv4"] == "100.119.242.42"
    assert parsed["remote"]["hostname"] == "vmi3547248"
    assert parsed["remote"]["tailscale_ipv4"] == "100.105.235.114"
    assert parsed["connection"] == {"kind": "derp", "relay": "fra"}


def test_parse_status_prefers_direct_path_when_current_address_exists():
    parsed = parse_status(_status(relay="", cur_addr="198.51.100.7:41641"))

    assert parsed["connection"] == {"kind": "direct", "relay": None}


@pytest.mark.parametrize(
    ("raw", "expected_state"),
    [
        (json.dumps({"BackendState": "NeedsLogin", "Self": {}, "Peer": {}}), "needs_login"),
        (json.dumps({"BackendState": "Running", "Self": {}, "Peer": {}}), "unavailable"),
    ],
)
def test_parse_status_reports_missing_operational_state(raw: str, expected_state: str):
    assert parse_status(raw)["local"]["state"] == expected_state


def test_parse_status_rejects_malformed_json():
    with pytest.raises(ValueError, match="invalid_response"):
        parse_status("not-json")


def test_parse_ping_normalizes_derp_and_direct_without_raw_output():
    assert parse_ping("pong from vmi3547248 (100.105.235.114) via DERP(fra) in 210ms") == {
        "success": True,
        "kind": "derp",
        "relay": "fra",
        "latency_ms": 210.0,
    }


def test_parse_prefs_reports_only_restricted_posture_fields():
    assert parse_prefs(
        json.dumps(
            {
                "CorpDNS": False,
                "RouteAll": False,
                "AdvertiseRoutes": [],
                "RunSSH": False,
                "ExitNodeID": "",
                "ControlURL": "https://controlplane.tailscale.com",
            }
        )
    ) == {
        "accept_dns": False,
        "accept_routes": False,
        "advertise_exit_node": False,
        "tailscale_ssh": False,
        "exit_node": False,
        "restricted": True,
    }
    assert parse_ping("pong from vmi3547248 via 203.0.113.10:41641 in 34ms") == {
        "success": True,
        "kind": "direct",
        "relay": None,
        "latency_ms": 34.0,
    }


class RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], float]] = []

    def __call__(self, argv: list[str], timeout: float):
        self.calls.append((argv, timeout))
        if argv[:2] == ["tailscale", "status"]:
            return type("Result", (), {"returncode": 0, "stdout": _status(), "stderr": ""})()
        if argv[:2] == ["tailscale", "ping"]:
            return type(
                "Result",
                (),
                {
                    "returncode": 0,
                    "stdout": "pong from vmi3547248 via DERP(fra) in 210ms",
                    "stderr": "",
                },
            )()
        if argv[:3] == ["tailscale", "debug", "prefs"]:
            return type(
                "Result",
                (),
                {
                    "returncode": 0,
                    "stdout": json.dumps(
                        {
                            "CorpDNS": False,
                            "RouteAll": False,
                            "AdvertiseRoutes": [],
                            "RunSSH": False,
                            "ExitNodeID": "",
                        }
                    ),
                    "stderr": "",
                },
            )()
        if argv == ["systemctl", "is-active", "tailscaled"]:
            return type("Result", (), {"returncode": 0, "stdout": "active\n", "stderr": ""})()
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()


def test_status_includes_daemon_and_restricted_local_posture():
    runner = RecordingRunner()

    result = VpnControl(runner=runner).status()

    assert result["local"]["daemon_state"] == "active"
    assert result["local"]["posture"]["restricted"] is True
    assert result["remote"]["daemon_state"] == "observed"
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
    assert "traceback" not in json.dumps(result).lower()
    assert "/usr/" not in json.dumps(result)


def test_remote_test_resolves_live_private_ip_and_uses_fixed_ping_command():
    runner = RecordingRunner()

    result = VpnControl(runner=runner).action("remote", "test")

    assert result["success"] is True
    assert runner.calls[-1][0] == [
        "tailscale",
        "ping",
        "--until-direct=false",
        "--c",
        "1",
        "100.105.235.114",
    ]


@pytest.mark.parametrize(
    ("node", "action"),
    [("remote", "disconnect"), ("remote", "connect"), ("unknown", "test"), ("local", "erase")],
)
def test_policy_rejects_unsafe_or_unknown_actions_before_execution(node: str, action: str):
    runner = RecordingRunner()

    with pytest.raises(VpnPolicyError):
        VpnControl(runner=runner).action(node, action)

    assert runner.calls == []


def test_local_connect_uses_restricted_posture_flags():
    runner = RecordingRunner()

    VpnControl(runner=runner).action("local", "connect")

    assert runner.calls == [
        (
            [
                "tailscale",
                "up",
                "--hostname=NotebookSTI-wsl",
                "--accept-dns=false",
                "--accept-routes=false",
                "--advertise-exit-node=false",
                "--ssh=false",
            ],
            30.0,
        )
    ]


def test_remote_restart_uses_only_live_tailscale_ip_and_fixed_ssh_command():
    runner = RecordingRunner()
    control = VpnControl(
        runner=runner,
        remote_user="aegis",
        remote_key_path="/root/.ssh/vps-key",
        remote_host_key_alias="vmi3547248-public",
    )

    result = control.action("remote", "restart")

    assert result["success"] is True
    assert (
        [
            "ssh",
            "-i",
            "/root/.ssh/vps-key",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=8",
            "-o",
            "HostKeyAlias=vmi3547248-public",
            "aegis@100.105.235.114",
            "sudo",
            "-n",
            "systemctl",
            "restart",
            "tailscaled",
        ],
        20.0,
    ) in runner.calls
    assert runner.calls[-3][0] == ["tailscale", "status", "--json"]


def test_remote_restart_fails_closed_when_private_peer_is_absent():
    class OfflineRunner(RecordingRunner):
        def __call__(self, argv: list[str], timeout: float):
            self.calls.append((argv, timeout))
            return type(
                "Result",
                (),
                {
                    "returncode": 0,
                    "stdout": json.dumps(
                        {
                            "BackendState": "Running",
                            "Self": {"HostName": "NotebookSTI-wsl", "Online": True},
                            "Peer": {},
                        }
                    ),
                    "stderr": "",
                },
            )()

    runner = OfflineRunner()

    result = VpnControl(runner=runner).action("remote", "restart")

    assert result == {
        "success": False,
        "code": "peer_offline",
        "summary": "Remote peer is unavailable.",
    }
    assert all(call[0][0] != "ssh" for call in runner.calls)


def test_remote_key_path_must_stay_inside_approved_roots():
    with pytest.raises(VpnPolicyError, match="invalid_key_path"):
        VpnControl(runner=RecordingRunner(), remote_key_path="/tmp/untrusted-key")


def test_login_url_is_replaced_by_stable_needs_login_error():
    class LoginRunner(RecordingRunner):
        def __call__(self, argv: list[str], timeout: float):
            self.calls.append((argv, timeout))
            return type(
                "Result",
                (),
                {
                    "returncode": 1,
                    "stdout": "To authenticate, visit https://login.tailscale.com/a/secret-value",
                    "stderr": "",
                },
            )()

    result = VpnControl(runner=LoginRunner()).action("local", "connect")

    assert result == {
        "success": False,
        "code": "needs_login",
        "summary": "Tailscale authorization is required on the host.",
    }
    assert "login.tailscale.com" not in json.dumps(result)

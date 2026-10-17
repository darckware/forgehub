from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.api.routes.vpn import normalize_status, sanitize_summary, validate_action


def _bridge_status() -> dict:
    return {
        "backend_state": "Running",
        "self": {
            "hostname": "vmi3547248",
            "tailscale_ipv4": "100.105.235.114",
            "state": "online",
            "online": True,
            "active": True,
            "last_seen": "2026-09-03T18:01:00Z",
        },
        "peers": [
            {
                "id": "nKqVMEy38E11CNTRL",
                "hostname": "NotebookSTI-wsl",
                "tailscale_ipv4": "100.119.242.42",
                "state": "online",
                "online": True,
                "active": True,
                "last_seen": "2026-09-03T18:00:00Z",
                "rx_bytes": 100,
                "tx_bytes": 200,
                "connection": {"kind": "derp", "relay": "fra"},
            },
        ],
    }


def test_normalize_status_exposes_only_typed_vpn_state():
    checked_at = datetime(2026, 9, 3, 18, 2, tzinfo=timezone.utc)

    status = normalize_status(_bridge_status(), checked_at=checked_at)

    assert status.server.id == "self"
    assert status.server.hostname == "vmi3547248"
    assert [peer.hostname for peer in status.peers] == ["NotebookSTI-wsl"]
    assert status.peers[0].connection.kind == "derp"
    assert status.peers[0].connection.relay == "fra"
    assert status.checked_at == checked_at


def test_normalize_status_without_self_reads_as_unavailable():
    status = normalize_status({"peers": "garbage"})

    assert status.backend_state == "Unavailable"
    assert status.server.state == "unavailable"
    assert status.peers == []


@pytest.mark.parametrize(
    ("node", "action"),
    [
        ("self", "test"),
        ("self", "disconnect"),
        ("nKqVMEy38E11CNTRL", "restart"),
        ("nKqVMEy38E11CNTRL", "connect"),
        ("../etc/passwd", "test"),
        ("", "test"),
    ],
)
def test_validate_action_rejects_unsafe_combinations(node: str, action: str):
    with pytest.raises(ValueError, match="action_not_allowed"):
        validate_action(node, action)


@pytest.mark.parametrize(
    ("node", "action", "kind"),
    [
        ("self", "restart", "self"),
        ("nKqVMEy38E11CNTRL", "test", "peer"),
    ],
)
def test_validate_action_accepts_only_documented_combinations(node: str, action: str, kind: str):
    assert validate_action(node, action) == kind


def test_sanitize_summary_removes_login_urls_and_private_paths():
    raw = (
        "Open https://login.tailscale.com/a/secret-value using "
        "/root/agents/aegis/server-management/ssh_keys/private-key"
    )

    cleaned = sanitize_summary(raw)

    assert cleaned == "VPN operation requires attention."
    assert "secret-value" not in cleaned
    assert "/root/" not in cleaned


def test_normalize_status_keeps_partial_failure_as_usable_state():
    payload = _bridge_status()
    payload["peers"].append(
        {"id": "nOffline1CNTRL", "hostname": "gat-srv-01", "state": "unavailable"}
    )
    payload["peers"].append({"hostname": "no-id-and-no-state"})
    payload["error"] = {"code": "peer_offline", "summary": "Remote peer is unavailable."}

    status = normalize_status(payload)

    assert status.server.state == "online"
    assert [peer.state for peer in status.peers] == ["online", "unavailable"]
    assert status.source_error == "Remote peer is unavailable."

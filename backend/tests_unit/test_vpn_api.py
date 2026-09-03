from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.api.routes.vpn import normalize_status, sanitize_summary, validate_action


def _bridge_status() -> dict:
    return {
        "backend_state": "Running",
        "local": {
            "role": "local",
            "hostname": "NotebookSTI-wsl",
            "tailscale_ipv4": "100.119.242.42",
            "state": "online",
            "online": True,
            "active": True,
            "last_seen": "2026-09-03T18:00:00Z",
            "rx_bytes": 100,
            "tx_bytes": 200,
        },
        "remote": {
            "role": "remote",
            "hostname": "vmi3547248",
            "tailscale_ipv4": "100.105.235.114",
            "state": "online",
            "online": True,
            "active": True,
            "last_seen": "2026-09-03T18:01:00Z",
            "rx_bytes": 300,
            "tx_bytes": 400,
        },
        "connection": {"kind": "derp", "relay": "fra"},
    }


def test_normalize_status_exposes_only_typed_vpn_state():
    checked_at = datetime(2026, 9, 3, 18, 2, tzinfo=timezone.utc)

    status = normalize_status(_bridge_status(), checked_at=checked_at)

    assert status.independent_from_cloudflare is True
    assert [node.role for node in status.nodes] == ["local", "remote"]
    assert status.nodes[1].hostname == "vmi3547248"
    assert status.connection.kind == "derp"
    assert status.connection.relay == "fra"
    assert status.checked_at == checked_at


@pytest.mark.parametrize(
    ("node", "action"),
    [
        ("remote", "disconnect"),
        ("remote", "connect"),
        ("unknown", "test"),
        ("local", "delete"),
    ],
)
def test_validate_action_rejects_unsafe_combinations(node: str, action: str):
    with pytest.raises(ValueError, match="action_not_allowed"):
        validate_action(node, action)


@pytest.mark.parametrize(
    ("node", "action"),
    [
        ("local", "connect"),
        ("local", "disconnect"),
        ("local", "restart"),
        ("local", "test"),
        ("remote", "restart"),
        ("remote", "test"),
    ],
)
def test_validate_action_accepts_only_documented_combinations(node: str, action: str):
    assert validate_action(node, action) == (node, action)


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
    payload["remote"] = {
        "role": "remote",
        "hostname": "vmi3547248",
        "tailscale_ipv4": None,
        "state": "unavailable",
        "online": False,
        "active": False,
        "last_seen": None,
        "rx_bytes": 0,
        "tx_bytes": 0,
    }
    payload["error"] = {"code": "peer_offline", "summary": "Remote peer is unavailable."}

    status = normalize_status(payload)

    assert status.nodes[0].state == "online"
    assert status.nodes[1].state == "unavailable"
    assert status.source_error == "Remote peer is unavailable."

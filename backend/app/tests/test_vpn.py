import pytest

from app.api.routes.vpn import normalize_status, sanitize_summary, validate_action


@pytest.mark.parametrize(
    ("node", "action", "target"),
    [("self", "restart", "self"), ("nKqVMEy38E11CNTRL", "test", "peer")],
)
def test_validate_action_accepts_only_the_fixed_pairs(node, action, target):
    assert validate_action(node, action) == target


@pytest.mark.parametrize(
    ("node", "action"),
    [
        ("self", "test"),
        ("self", "connect"),
        ("local", "connect"),
        ("remote", "restart"),
        ("nKqVMEy38E11CNTRL", "restart"),
        ("100.82.42.10", "test"),
        ("../etc", "test"),
    ],
)
def test_validate_action_rejects_everything_else(node, action):
    with pytest.raises(ValueError, match="action_not_allowed"):
        validate_action(node, action)


def test_normalize_status_maps_server_and_peers():
    status = normalize_status(
        {
            "backend_state": "Running",
            "self": {"id": "self", "name": "darckware-srv", "state": "online", "online": True, "daemon_state": "active"},
            "peers": [
                {
                    "id": "nKqVMEy38E11CNTRL",
                    "name": "gat-adm-pc01",
                    "os": "windows",
                    "tags": ["tag:gatling-users"],
                    "state": "online",
                    "online": True,
                    "connection": {"kind": "direct", "relay": None},
                },
                {"id": "broken"},  # missing state: skipped, never fails the whole read
            ],
        }
    )

    assert status.server.name == "darckware-srv"
    assert [peer.name for peer in status.peers] == ["gat-adm-pc01"]
    assert status.peers[0].connection.kind == "direct"


def test_normalize_status_degrades_when_bridge_has_no_server():
    status = normalize_status({"backend_state": "Unavailable", "error": {"summary": "VPN bridge is unavailable."}})

    assert status.server.state == "unavailable"
    assert status.peers == []
    assert status.source_error == "VPN bridge is unavailable."


def test_sanitize_summary_hides_login_urls_and_key_paths():
    assert sanitize_summary("visit https://login.tailscale.com/a/x") == "VPN operation requires attention."
    assert sanitize_summary("key /root/.ssh/id_ed25519 missing") == "VPN operation requires attention."
    assert sanitize_summary("gat-adm-pc01 answered in 34 ms (direct).") == "gat-adm-pc01 answered in 34 ms (direct)."

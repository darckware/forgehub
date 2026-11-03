"""A.1: per-agent channel/gateway badge on the Agent Activity board (no network, no DB)."""
import json

from app.core import agent_telegram
from app.core.agent_telegram import GatewayHealth, build_channel_health, parse_gateway_state


def _home(tmp_path, configured=True):
    if configured:
        (tmp_path / ".env").write_text(
            "TELEGRAM_BOT_TOKEN=fictitious\nTELEGRAM_HOME_CHANNEL=-1000000000001\n", encoding="utf-8"
        )
    return str(tmp_path)


def _health(**kw):
    return build_channel_health(profile_slug=kw.pop("slug", "alpha"), required=kw.pop("required", False),
                                home_path=kw.pop("home"), runtime_type=kw.pop("runtime", "hermes"),
                                gateway=kw.pop("gateway"))


def test_unreachable_bridge_is_unknown_never_down(tmp_path):
    home = _home(tmp_path)
    for gateway in (None, GatewayHealth(None, None, "Host-bridge unreachable")):
        health = _health(home=home, gateway=gateway)
        assert (health.telegram, health.gateway) == ("unknown", "unknown")


def test_gateway_up_and_adapter_states(tmp_path):
    home = _home(tmp_path)
    up = GatewayHealth(True, {"alpha": "connected"}, None)
    assert vars(_health(home=home, gateway=up)) == {"telegram": "ok", "gateway": "ok"}
    fatal = GatewayHealth(True, {"alpha": "fatal"}, None)
    assert vars(_health(home=home, gateway=fatal)) == {"telegram": "not_running", "gateway": "ok"}
    down = GatewayHealth(False, {}, None)
    assert vars(_health(home=home, gateway=down)) == {"telegram": "not_running", "gateway": "down"}


def test_external_runtime_has_no_gateway_and_no_channel(tmp_path):
    up = GatewayHealth(True, {}, None)
    health = _health(home=_home(tmp_path, configured=False), runtime="claude", gateway=up)
    assert vars(health) == {"telegram": "not_applicable", "gateway": "not_applicable"}


def test_hermes_without_telegram_is_not_applicable_but_gateway_reported(tmp_path):
    health = _health(home=_home(tmp_path, configured=False), gateway=GatewayHealth(True, {}, None))
    assert vars(health) == {"telegram": "not_applicable", "gateway": "ok"}


def test_parse_gateway_state_reports_liveness_apart_from_adapters():
    body = json.dumps({"gateway_state": "running", "platforms": {}})
    assert parse_gateway_state(f"{body}\n__GATEWAY_PID_ALIVE__\nyes\n") == (True, {})
    assert parse_gateway_state(f"{body}\n__GATEWAY_PID_ALIVE__\nno\n") == (False, {})
    assert parse_gateway_state("[]\n__GATEWAY_PID_ALIVE__\nyes\n") == (False, {})
    assert agent_telegram.parse_telegram_states("garbage\n__GATEWAY_PID_ALIVE__\nyes\n") == {}

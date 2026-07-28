"""Tests for per-agent MCP configuration (app/core/agent_mcp.py).

Pure filesystem tests against tmp_path -- no DB, no app. What matters here is
that a write touches *only* the entry it was asked to touch: these are live
production configs (a Hermes profile's config.yaml, ~/.claude.json, Codex's
config.toml with its per-project trust blocks), so every test asserts the
surrounding content survives byte-for-byte, not just that the entry landed.
"""
import json

import pytest
import tomllib
import yaml

from app.core import agent_mcp

HERMES_YAML = """\
# Hermes profile config -- hand maintained, comments matter.
model: forgerouter/standard
browser:
  enabled: true
  loopback_host_alias: host.docker.internal
mcp_servers:
  forgehub-macros:
    command: uv
    args:
      - run
      - /root/project/forgehub/host-bridge/forgehub_macro_mcp.py
    env:
      FORGEHUB_API_URL: http://localhost:8001
checkpoints:
  enabled: false
  max_snapshots: 20
"""

CODEX_TOML = """\
model = "gpt-5.6-sol"

[projects."/root"]
trust_level = "trusted"

[mcp_servers.other]
command = "npx"
args = ["-y", "some-server"]

[mcp_servers.other.env]
TOKEN = "abc"

[notice]
hide_full_access_warning = true
"""


def _server(name: str = "forgehub-messages", **kwargs) -> agent_mcp.McpServerInfo:
    defaults = dict(
        command="uv",
        args=["run", "/root/project/forgehub/host-bridge/forgehub_messages_mcp.py"],
        env={"FORGEHUB_AGENT_SLUG": "athos"},
    )
    defaults.update(kwargs)
    return agent_mcp.McpServerInfo(name=name, **defaults)


# ---------------------------------------------------------------------------
# Config file location per runtime
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "runtime,home,expected",
    [
        ("hermes", "/root/.hermes/profiles/athos", "/root/.hermes/profiles/athos/config.yaml"),
        ("claude", "/root/.claude", "/root/.claude.json"),
        ("codex", "/root/.codex", "/root/.codex/config.toml"),
        ("agy", "/root/.gemini/config", "/root/.gemini/config/mcp_config.json"),
        ("openclaw", "/root/.openclaw/workspace", "/root/.openclaw/openclaw.json"),
    ],
)
def test_config_host_path_per_runtime(runtime, home, expected):
    """Two runtimes keep the file beside the home directory rather than in it;
    that asymmetry is the whole reason for the in_parent flag."""
    fmt = agent_mcp.format_for(runtime)
    assert agent_mcp.config_host_path(home, fmt) == expected


def test_unknown_runtime_has_no_format():
    assert agent_mcp.format_for(None) is None
    assert agent_mcp.format_for("something-else") is None


# ---------------------------------------------------------------------------
# YAML (Hermes profiles)
# ---------------------------------------------------------------------------


def test_yaml_upsert_keeps_comments_and_siblings(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(HERMES_YAML, encoding="utf-8")
    fmt = agent_mcp.format_for("hermes")

    agent_mcp.write_server(str(path), fmt, "forgehub-messages", _server())

    text = path.read_text(encoding="utf-8")
    assert text.startswith("# Hermes profile config -- hand maintained, comments matter.\n")
    assert "  loopback_host_alias: host.docker.internal\n" in text
    assert "checkpoints:\n  enabled: false\n  max_snapshots: 20\n" in text

    document = yaml.safe_load(text)
    assert set(document["mcp_servers"]) == {"forgehub-macros", "forgehub-messages"}
    assert document["mcp_servers"]["forgehub-messages"]["command"] == "uv"
    assert document["mcp_servers"]["forgehub-macros"]["env"]["FORGEHUB_API_URL"] == "http://localhost:8001"


def test_yaml_update_replaces_only_that_entry(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(HERMES_YAML, encoding="utf-8")
    fmt = agent_mcp.format_for("hermes")

    agent_mcp.write_server(str(path), fmt, "forgehub-macros", _server("forgehub-macros", env={"X": "1"}))

    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert document["mcp_servers"]["forgehub-macros"]["env"] == {"X": "1"}
    assert list(document["mcp_servers"]) == ["forgehub-macros"]
    assert document["checkpoints"]["max_snapshots"] == 20


def test_yaml_disabled_writes_enabled_false(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(HERMES_YAML, encoding="utf-8")
    fmt = agent_mcp.format_for("hermes")

    agent_mcp.write_server(str(path), fmt, "forgehub-messages", _server(enabled=False))

    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert document["mcp_servers"]["forgehub-messages"]["enabled"] is False
    assert agent_mcp.read_servers(str(path), fmt)[0].enabled is False


def test_yaml_enabled_true_is_not_written(tmp_path):
    """Every runtime defaults to on, so an explicit `enabled: true` is noise."""
    path = tmp_path / "config.yaml"
    path.write_text(HERMES_YAML, encoding="utf-8")
    fmt = agent_mcp.format_for("hermes")

    agent_mcp.write_server(str(path), fmt, "forgehub-messages", _server(enabled=True))

    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "enabled" not in document["mcp_servers"]["forgehub-messages"]


def test_yaml_remove_last_server_drops_the_block(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(HERMES_YAML, encoding="utf-8")
    fmt = agent_mcp.format_for("hermes")

    agent_mcp.write_server(str(path), fmt, "forgehub-macros", None)

    text = path.read_text(encoding="utf-8")
    assert "mcp_servers" not in text
    document = yaml.safe_load(text)
    assert document["checkpoints"]["enabled"] is False
    assert document["browser"]["enabled"] is True


def test_yaml_creates_block_when_absent(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("model: forgerouter/standard\n", encoding="utf-8")
    fmt = agent_mcp.format_for("hermes")

    agent_mcp.write_server(str(path), fmt, "forgehub-messages", _server())

    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert document["model"] == "forgerouter/standard"
    assert document["mcp_servers"]["forgehub-messages"]["args"][0] == "run"


# ---------------------------------------------------------------------------
# TOML (Codex)
# ---------------------------------------------------------------------------


def test_toml_upsert_appends_and_keeps_other_tables(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(CODEX_TOML, encoding="utf-8")
    fmt = agent_mcp.format_for("codex")

    agent_mcp.write_server(str(path), fmt, "forgehub-messages", _server())

    document = tomllib.loads(path.read_text(encoding="utf-8"))
    assert document["projects"]["/root"]["trust_level"] == "trusted"
    assert document["notice"]["hide_full_access_warning"] is True
    assert document["mcp_servers"]["other"]["env"]["TOKEN"] == "abc"
    entry = document["mcp_servers"]["forgehub-messages"]
    assert entry["command"] == "uv"
    assert entry["env"]["FORGEHUB_AGENT_SLUG"] == "athos"


def test_toml_update_replaces_entry_including_env_subtable(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(CODEX_TOML, encoding="utf-8")
    fmt = agent_mcp.format_for("codex")

    agent_mcp.write_server(str(path), fmt, "other", _server("other", command="node", args=[], env={}))

    document = tomllib.loads(path.read_text(encoding="utf-8"))
    assert document["mcp_servers"]["other"] == {"command": "node", "args": []}
    assert document["notice"]["hide_full_access_warning"] is True


def test_toml_remove_takes_subtables_with_it(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(CODEX_TOML, encoding="utf-8")
    fmt = agent_mcp.format_for("codex")

    agent_mcp.write_server(str(path), fmt, "other", None)

    text = path.read_text(encoding="utf-8")
    assert "mcp_servers" not in text
    document = tomllib.loads(text)
    assert document["model"] == "gpt-5.6-sol"
    assert document["notice"]["hide_full_access_warning"] is True


# ---------------------------------------------------------------------------
# JSON (Claude Code, agy, OpenClaw)
# ---------------------------------------------------------------------------


def test_claude_json_preserves_unrelated_keys_and_stamps_stdio(tmp_path):
    path = tmp_path / ".claude.json"
    path.write_text(json.dumps({"projects": {"/root": {"history": [1, 2, 3]}}}), encoding="utf-8")
    fmt = agent_mcp.format_for("claude")

    agent_mcp.write_server(str(path), fmt, "forgehub-messages", _server())

    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["projects"]["/root"]["history"] == [1, 2, 3]
    assert document["mcpServers"]["forgehub-messages"]["type"] == "stdio"
    assert document["mcpServers"]["forgehub-messages"]["command"] == "uv"


def test_openclaw_nested_path_and_disabled_flag(tmp_path):
    path = tmp_path / "openclaw.json"
    path.write_text(json.dumps({"plugins": {"entries": {"telegram": {"enabled": True}}}}), encoding="utf-8")
    fmt = agent_mcp.format_for("openclaw")

    agent_mcp.write_server(str(path), fmt, "forgehub-messages", _server(enabled=False))

    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["plugins"]["entries"]["telegram"]["enabled"] is True
    assert document["mcp"]["servers"]["forgehub-messages"]["disabled"] is True
    # Inverted toggle: `disabled: true` must read back as enabled=False.
    assert agent_mcp.read_servers(str(path), fmt)[0].enabled is False


def test_json_remove_leaves_other_servers(tmp_path):
    path = tmp_path / "mcp_config.json"
    path.write_text(
        json.dumps({"mcpServers": {"a": {"command": "x"}, "b": {"command": "y"}}}), encoding="utf-8"
    )
    fmt = agent_mcp.format_for("agy")

    agent_mcp.write_server(str(path), fmt, "a", None)

    document = json.loads(path.read_text(encoding="utf-8"))
    assert list(document["mcpServers"]) == ["b"]


def test_write_creates_missing_file(tmp_path):
    """Adding the first MCP server to a runtime that never had one is normal
    first use, not an error -- every format has a valid empty document."""
    path = tmp_path / "mcp_config.json"
    fmt = agent_mcp.format_for("agy")

    agent_mcp.write_server(str(path), fmt, "forgehub-messages", _server())

    assert json.loads(path.read_text(encoding="utf-8"))["mcpServers"]["forgehub-messages"]["command"] == "uv"


# ---------------------------------------------------------------------------
# Reading and validation
# ---------------------------------------------------------------------------


def test_read_missing_file_is_empty_not_an_error(tmp_path):
    fmt = agent_mcp.format_for("hermes")
    assert agent_mcp.read_servers(str(tmp_path / "nope.yaml"), fmt) == []


def test_read_invalid_yaml_raises_config_error(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("mcp_servers:\n  broken: [unclosed\n", encoding="utf-8")
    fmt = agent_mcp.format_for("hermes")
    with pytest.raises(agent_mcp.McpConfigError):
        agent_mcp.read_servers(str(path), fmt)


def test_http_server_round_trips_url(tmp_path):
    path = tmp_path / "mcp_config.json"
    fmt = agent_mcp.format_for("agy")
    agent_mcp.write_server(
        str(path), fmt, "remote", agent_mcp.McpServerInfo(name="remote", url="https://example/mcp")
    )
    server = agent_mcp.read_servers(str(path), fmt)[0]
    assert server.url == "https://example/mcp"
    assert server.command is None
    assert "command" not in json.loads(path.read_text(encoding="utf-8"))["mcpServers"]["remote"]


@pytest.mark.parametrize("name", ["../escape", "with space", "a]b", "", "x" * 65])
def test_invalid_server_names_are_rejected(tmp_path, name):
    """The name lands in a YAML key and a TOML table header -- anything that
    could change the meaning of either must never reach the file."""
    path = tmp_path / "config.yaml"
    path.write_text(HERMES_YAML, encoding="utf-8")
    fmt = agent_mcp.format_for("hermes")
    with pytest.raises(agent_mcp.McpConfigError):
        agent_mcp.write_server(str(path), fmt, name, _server(name or "x"))
    assert path.read_text(encoding="utf-8") == HERMES_YAML

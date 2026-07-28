"""Per-agent MCP server configuration, across the five agent runtimes.

Every runtime in the ecosystem can load MCP servers, but each keeps that
configuration in its own file, in its own format, under its own key:

    runtime_type   file                                key           toggle
    ------------   ---------------------------------   -----------   ------
    hermes         <home>/config.yaml                  mcp_servers   enabled: false
    claude         <home>/../.claude.json              mcpServers    (none)
    codex          <home>/config.toml                  mcp_servers   enabled = false
    agy            <home>/mcp_config.json              mcpServers    (none)
    openclaw        <home>/../openclaw.json             mcp.servers   disabled: true

`<home>` is the same `Agent.home_path`/runtime convention `agent_profile_files`
already resolves, so an agent that moved its config stays a field edit rather
than a code change. Two of the files sit *next to* the home directory rather
than inside it (Claude Code's `~/.claude.json` and OpenClaw's
`~/.openclaw/openclaw.json`) -- that is a property of those runtimes, not a
mistake, so the mapping is expressed as a filename plus a "parent" flag.

The actual file read/write engine (format parsing, surgical YAML/TOML edits,
JSON round-trip) lives in `core/mcp_config_io.py` -- extracted 2026-07-28 so
`core/project_mcp.py` (per-project `.mcp.json`, Claude Code only) can reuse it
without duplicating the surgical-write logic or reaching into this module's
internals. This module only adds the agent-specific pieces: which runtime
uses which format (`FORMATS`), and how an agent's home path becomes a config
file path (`config_host_path`).

Nothing here is a second source of truth: these are the same files the
runtimes' own `mcp add`/`mcp list` commands read and write. ForgeHub edits
them in place so an operator can see and manage all thirteen agents' servers
from one screen instead of shelling into five different CLIs.
"""
from __future__ import annotations

from pathlib import Path

from app.core.mcp_config_io import (
    SERVER_NAME_RE,
    McpConfigError,
    McpConfigFormat,
    McpServerInfo,
    read_servers,
    resolve_host_file,
    write_server,
)

__all__ = [
    "SERVER_NAME_RE",
    "McpConfigError",
    "McpConfigFormat",
    "McpServerInfo",
    "read_servers",
    "resolve_host_file",
    "write_server",
    "FORMATS",
    "format_for",
    "config_host_path",
]

FORMATS: dict[str, McpConfigFormat] = {
    "hermes": McpConfigFormat(
        key="hermes", filename="config.yaml", path=("mcp_servers",), toggle_field="enabled"
    ),
    "claude": McpConfigFormat(
        key="claude", filename=".claude.json", in_parent=True, path=("mcpServers",)
    ),
    "codex": McpConfigFormat(
        key="codex", filename="config.toml", path=("mcp_servers",), toggle_field="enabled"
    ),
    "agy": McpConfigFormat(key="agy", filename="mcp_config.json", path=("mcpServers",)),
    "openclaw": McpConfigFormat(
        key="openclaw",
        filename="openclaw.json",
        in_parent=True,
        path=("mcp", "servers"),
        toggle_field="disabled",
        toggle_inverted=True,
    ),
}


def format_for(runtime_type: str | None) -> McpConfigFormat | None:
    return FORMATS.get(runtime_type or "")


def config_host_path(agent_home: str | None, fmt: McpConfigFormat) -> str | None:
    """The host-canonical path of the file holding this runtime's MCP config."""
    if not agent_home:
        return None
    home = agent_home.rstrip("/") or "/"
    base = str(Path(home).parent) if fmt.in_parent else home
    return f"{base.rstrip('/')}/{fmt.filename}"

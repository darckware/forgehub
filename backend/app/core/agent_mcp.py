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

Writes are deliberately **surgical**, not a parse/re-serialize round-trip, for
the two commented formats. A Hermes `config.yaml` is a live production config
with comments and a hand-tuned key order that `yaml.safe_dump` would flatten,
and a Codex `config.toml` has per-project trust blocks in it; rewriting either
wholesale to change one server is a much bigger blast radius than the edit
asks for. So YAML and TOML are edited line-wise (the entry's own lines are
replaced/removed/appended, everything else is byte-identical), while the three
JSON files -- machine-written by their own CLIs, no comments possible -- are
round-tripped normally.

Nothing here is a second source of truth: these are the same files the
runtimes' own `mcp add`/`mcp list` commands read and write. ForgeHub edits
them in place so an operator can see and manage all thirteen agents' servers
from one screen instead of shelling into five different CLIs.
"""
from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.core import agent_profile_files

# A server name lands inside a YAML key and a TOML table header, so it is kept
# to characters that cannot change the meaning of either. The runtimes' own
# CLIs accept the same shape.
SERVER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


@dataclass(frozen=True)
class McpConfigFormat:
    """How one runtime stores its MCP servers."""

    key: str
    filename: str
    # True when the file sits beside the home directory rather than inside it
    # (Claude Code's ~/.claude.json, OpenClaw's ~/.openclaw/openclaw.json).
    in_parent: bool = False
    # Dotted path to the servers mapping inside the parsed document.
    path: tuple[str, ...] = ()
    # Which field expresses on/off, if any. "enabled" is true-means-on,
    # "disabled" is true-means-off, None means the runtime has no toggle.
    toggle_field: str | None = None
    toggle_inverted: bool = False


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


@dataclass(frozen=True)
class McpServerInfo:
    name: str
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str | None = None
    enabled: bool = True


class McpConfigError(RuntimeError):
    """Raised when a config file exists but cannot be read or written."""


def format_for(runtime_type: str | None) -> McpConfigFormat | None:
    return FORMATS.get(runtime_type or "")


def config_host_path(agent_home: str | None, fmt: McpConfigFormat) -> str | None:
    """The host-canonical path of the file holding this runtime's MCP config."""
    if not agent_home:
        return None
    home = agent_home.rstrip("/") or "/"
    base = str(Path(home).parent) if fmt.in_parent else home
    return f"{base.rstrip('/')}/{fmt.filename}"


def resolve_host_file(host_path: str | None) -> Path | None:
    """Resolve a host file path to one readable from this process -- the file
    equivalent of agent_profile_files.resolve_home_dir, with the same
    host-first / named-mount / /host-root fallback order. None when the file
    does not exist anywhere (an unconfigured runtime, not an error)."""
    if not host_path:
        return None
    candidates = [Path(host_path)]
    mapped = agent_profile_files.container_path(host_path)
    if mapped:
        candidates.append(Path(mapped))
    candidates.append(Path(agent_profile_files.HOST_ROOT_MOUNT + "/" + host_path.lstrip("/")))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _is_enabled(entry: dict, fmt: McpConfigFormat) -> bool:
    if not fmt.toggle_field:
        return True
    raw = entry.get(fmt.toggle_field)
    if raw is None:
        return True
    return (not bool(raw)) if fmt.toggle_inverted else bool(raw)


def _entry_to_info(name: str, entry: dict, fmt: McpConfigFormat) -> McpServerInfo:
    args = entry.get("args") or []
    env = entry.get("env") or {}
    return McpServerInfo(
        name=name,
        command=entry.get("command"),
        args=[str(a) for a in args] if isinstance(args, list) else [],
        env={str(k): str(v) for k, v in env.items()} if isinstance(env, dict) else {},
        url=entry.get("url"),
        enabled=_is_enabled(entry, fmt),
    )


def _load_document(path: Path, fmt: McpConfigFormat) -> dict:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise McpConfigError(f"Failed to read {path}: {exc}") from exc
    if not raw.strip():
        return {}
    try:
        if fmt.filename.endswith(".yaml"):
            return yaml.safe_load(raw) or {}
        if fmt.filename.endswith(".toml"):
            return tomllib.loads(raw)
        return json.loads(raw)
    except (yaml.YAMLError, tomllib.TOMLDecodeError, json.JSONDecodeError) as exc:
        raise McpConfigError(f"{path} is not valid {fmt.filename.rsplit('.', 1)[-1]}: {exc}") from exc


def _servers_mapping(document: dict, fmt: McpConfigFormat) -> dict:
    node: object = document
    for step in fmt.path:
        if not isinstance(node, dict):
            return {}
        node = node.get(step) or {}
    return node if isinstance(node, dict) else {}


def read_servers(host_path: str | None, fmt: McpConfigFormat) -> list[McpServerInfo]:
    """Every MCP server configured for this runtime, in file order. An absent
    file means "none configured yet", not an error -- most runtimes only grow
    the file on first `mcp add`."""
    resolved = resolve_host_file(host_path)
    if resolved is None:
        return []
    document = _load_document(resolved, fmt)
    return [
        _entry_to_info(name, entry, fmt)
        for name, entry in _servers_mapping(document, fmt).items()
        if isinstance(entry, dict)
    ]


def _entry_dict(server: McpServerInfo, fmt: McpConfigFormat) -> dict:
    entry: dict[str, object] = {}
    if server.url:
        entry["url"] = server.url
    else:
        entry["command"] = server.command
        entry["args"] = list(server.args)
    if server.env:
        entry["env"] = dict(server.env)
    if fmt.toggle_field:
        # Only write the toggle when it says something: the runtimes all
        # default to on, so an "enabled: true" line is noise in a hand-read
        # config, and "disabled: false" doubly so.
        if fmt.toggle_inverted and not server.enabled:
            entry[fmt.toggle_field] = True
        elif not fmt.toggle_inverted and not server.enabled:
            entry[fmt.toggle_field] = False
    return entry


# --------------------------------------------------------------------------
# Writers. One per file format; each returns the new file text.
# --------------------------------------------------------------------------


def _yaml_entry_lines(name: str, entry: dict) -> list[str]:
    dumped = yaml.safe_dump({name: entry}, sort_keys=False, allow_unicode=True, default_flow_style=False)
    return [f"  {line}\n" if line.strip() else "\n" for line in dumped.splitlines()]


def _yaml_block_bounds(lines: list[str], header: str) -> tuple[int, int] | None:
    """(start, end) line indices of a top-level block, end exclusive."""
    try:
        start = next(i for i, line in enumerate(lines) if line.rstrip("\n") == header)
    except StopIteration:
        return None
    end = start + 1
    while end < len(lines):
        line = lines[end]
        if line.strip() and not line[0].isspace():
            break
        end += 1
    return start, end


def _yaml_entry_bounds(lines: list[str], block: tuple[int, int], name: str) -> tuple[int, int] | None:
    """(start, end) of one server's lines inside an mcp_servers block."""
    block_start, block_end = block
    prefix = f"  {name}:"
    for i in range(block_start + 1, block_end):
        stripped = lines[i].rstrip("\n")
        if stripped == prefix or stripped.startswith(prefix + " "):
            end = i + 1
            while end < block_end and (not lines[end].strip() or lines[end].startswith("    ")):
                end += 1
            return i, end
    return None


def _write_yaml(text: str, name: str, entry: dict | None, fmt: McpConfigFormat) -> str:
    lines = text.splitlines(keepends=True)
    header = f"{fmt.path[0]}:"
    block = _yaml_block_bounds(lines, header)
    if block is None:
        if entry is None:
            return text
        # No mcp_servers block yet: append one at the end of the document,
        # which is always valid at top level and never disturbs a key above it.
        tail = "" if not lines or lines[-1].endswith("\n") else "\n"
        return text + tail + f"{header}\n" + "".join(_yaml_entry_lines(name, entry))
    existing = _yaml_entry_bounds(lines, block, name)
    if entry is None:
        if existing is None:
            return text
        start, end = existing
        remaining = lines[block[0] + 1 : start] + lines[end : block[1]]
        if not any(line.strip() for line in remaining):
            # Removing the last server leaves `mcp_servers:` with a null value,
            # which parses as None and is what the runtimes treat as "unset" --
            # but an empty mapping key reads as an accident, so drop the header.
            return "".join(lines[: block[0]] + lines[block[1] :])
        return "".join(lines[:start] + lines[end:])
    new_lines = _yaml_entry_lines(name, entry)
    if existing is None:
        return "".join(lines[: block[0] + 1] + new_lines + lines[block[0] + 1 :])
    start, end = existing
    return "".join(lines[:start] + new_lines + lines[end:])


def _toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    return json.dumps(str(value))


def _toml_entry_text(name: str, entry: dict, key: str) -> str:
    env = entry.get("env") or {}
    scalars = {k: v for k, v in entry.items() if k != "env"}
    lines = [f"[{key}.{name}]"]
    lines.extend(f"{k} = {_toml_value(v)}" for k, v in scalars.items() if v is not None)
    if env:
        lines.append("")
        lines.append(f"[{key}.{name}.env]")
        lines.extend(f"{k} = {_toml_value(v)}" for k, v in env.items())
    return "\n".join(lines) + "\n"


def _toml_entry_bounds(lines: list[str], name: str, key: str) -> tuple[int, int] | None:
    """(start, end) covering `[key.name]` and every `[key.name.*]` subtable."""
    start = None
    end = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("["):
            continue
        mine = stripped == f"[{key}.{name}]" or stripped.startswith(f"[{key}.{name}.")
        if mine and start is None:
            start = i
        elif start is not None and not mine:
            end = i
            break
    if start is None:
        return None
    if end is None:
        end = len(lines)
    # Trailing blank lines belong to the entry we are removing, not the next one.
    while end - 1 > start and not lines[end - 1].strip():
        end -= 1
    return start, end


def _write_toml(text: str, name: str, entry: dict | None, fmt: McpConfigFormat) -> str:
    key = fmt.path[0]
    lines = text.splitlines(keepends=True)
    bounds = _toml_entry_bounds(lines, name, key)
    if entry is None:
        if bounds is None:
            return text
        start, end = bounds
        while end < len(lines) and not lines[end].strip():
            end += 1
        return "".join(lines[:start] + lines[end:])
    block = _toml_entry_text(name, entry, key)
    if bounds is None:
        separator = "" if not text or text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
        return text + separator + block
    start, end = bounds
    return "".join(lines[:start]) + block + "".join(lines[end:])


def _write_json(text: str, name: str, entry: dict | None, fmt: McpConfigFormat) -> str:
    document = json.loads(text) if text.strip() else {}
    node = document
    for step in fmt.path[:-1]:
        nxt = node.get(step)
        if not isinstance(nxt, dict):
            nxt = {}
            node[step] = nxt
        node = nxt
    leaf = fmt.path[-1]
    servers = node.get(leaf)
    if not isinstance(servers, dict):
        servers = {}
        node[leaf] = servers
    if entry is None:
        servers.pop(name, None)
    else:
        # Claude Code stamps a transport type on every stdio server it writes;
        # keep whatever is already there so an edit doesn't drop fields the
        # runtime added for itself.
        existing = servers.get(name) if isinstance(servers.get(name), dict) else {}
        merged = {**{k: v for k, v in existing.items() if k in {"type", "transport"}}, **entry}
        if fmt.key == "claude" and "type" not in merged and not entry.get("url"):
            merged = {"type": "stdio", **merged}
        servers[name] = merged
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def write_server(
    host_path: str,
    fmt: McpConfigFormat,
    name: str,
    server: McpServerInfo | None,
) -> str:
    """Upsert (`server` set) or remove (`server=None`) one MCP server in the
    runtime's own config file, and return the host path actually written.

    The file is created when absent -- adding the first MCP server to a
    runtime that never had one is a normal first use, and every format has a
    valid empty document. The containing directory is not created: that would
    mean the agent's home doesn't exist, which is a registration error the
    operator should see rather than have papered over.
    """
    if not SERVER_NAME_RE.match(name):
        raise McpConfigError(
            f"Invalid MCP server name {name!r}: use letters, digits, '.', '_' or '-' (max 64 chars)."
        )
    resolved = resolve_host_file(host_path)
    if resolved is None:
        if server is None:
            raise McpConfigError(f"{host_path} does not exist -- nothing to remove.")
        directory = agent_profile_files.resolve_home_dir(str(Path(host_path).parent))
        if directory is None:
            raise McpConfigError(
                f"Cannot create {host_path}: its directory does not exist. "
                "Check the agent's home path."
            )
        resolved = directory / Path(host_path).name
        text = ""
    else:
        try:
            text = resolved.read_text(encoding="utf-8")
        except OSError as exc:
            raise McpConfigError(f"Failed to read {resolved}: {exc}") from exc

    entry = _entry_dict(server, fmt) if server is not None else None
    if fmt.filename.endswith(".yaml"):
        updated = _write_yaml(text, name, entry, fmt)
    elif fmt.filename.endswith(".toml"):
        updated = _write_toml(text, name, entry, fmt)
    else:
        try:
            updated = _write_json(text, name, entry, fmt)
        except json.JSONDecodeError as exc:
            raise McpConfigError(f"{resolved} is not valid JSON: {exc}") from exc

    try:
        resolved.write_text(updated, encoding="utf-8")
    except OSError as exc:
        raise McpConfigError(f"Failed to write {resolved}: {exc}") from exc
    return host_path

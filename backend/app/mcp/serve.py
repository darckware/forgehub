#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp[cli]>=1.2.0,<2", "httpx>=0.27"]
# ///
"""Run one ForgeHub MCP server: `uv run serve.py <server>` (MCP split plan, Fase 1).

Servers and their tools are in server_map.py. The tools themselves are defined once, in
host-bridge/forgehub_messages_mcp.py, factory_server.py and the personal modules; this file loads
that combined catalog and exposes only the chosen server's share of it, with the same tool
objects (same schemas, same code, same credentials). `forgehub_all` exposes everything, exactly
what factory_server.py serves today.

Each server is its own process with its own entry in the agent's config, so an agent's config
decides which servers it gets (plan D4) and the Hermes `platform_toolsets` filter works per server.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def build(server: str):
    """The FastMCP instance for one server, from the combined catalog."""
    server_map = _load("forgehub_mcp_server_map", HERE / "server_map.py")
    if server not in server_map.SERVERS:
        raise SystemExit(f"Unknown ForgeHub MCP server {server!r}; one of: {', '.join(server_map.SERVERS)}")
    factory = _load("forgehub_factory_server", HERE / "factory_server.py")
    combined = factory.mcp
    if server == server_map.ALL:
        return combined
    if server == server_map.PERSONAL:
        personal = _load("forgehub_personal_contacts", HERE / "personal_contacts.py")
        if not personal.register(combined):
            raise SystemExit("forgehub_personal tools are not authorized for this agent")
    from mcp.server.fastmcp import FastMCP

    selected = FastMCP(server)
    tools = combined._tool_manager._tools  # FastMCP keeps its catalog here; Tool objects are reused as-is
    for name, tool in tools.items():
        if server_map.server_of(name) == server:
            selected._tool_manager._tools[name] = tool
    if not selected._tool_manager._tools:
        raise SystemExit(f"ForgeHub MCP server {server!r} has no tools in this session")
    return selected


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: serve.py <server>")
    build(sys.argv[1]).run()


if __name__ == "__main__":
    main()

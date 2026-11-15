"""MCP split plan, Fase 1: every tool belongs to exactly one ForgeHub MCP server (gap L12).

Runs without a database: it only loads the MCP modules and inspects their catalogs.
Both optional tool sets are switched on so the map is checked against the full catalog.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

os.environ["FORGEHUB_TASK_BROWSER_ENABLED"] = "1"
os.environ["FORGEHUB_MISSION_LEARNING_ENABLED"] = "1"

MCP_DIR = Path(__file__).resolve().parents[1] / "app" / "mcp"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


serve = _load("test_forgehub_mcp_serve", MCP_DIR / "serve.py")
server_map = _load("test_forgehub_mcp_server_map", MCP_DIR / "server_map.py")


def _names(instance) -> set[str]:
    return set(instance._tool_manager._tools)


@pytest.fixture(scope="module")
def combined() -> set[str]:
    return _names(serve.build(server_map.ALL))


def test_every_tool_has_exactly_one_server(combined):
    orphans = sorted(name for name in combined if server_map.server_of(name) is None)
    assert orphans == []


def test_the_map_names_no_tool_the_catalog_lacks(combined):
    mapped = set().union(*server_map.SERVER_TOOLS.values())
    assert sorted(mapped - combined) == []


def test_no_tool_is_mapped_twice():
    seen: dict[str, str] = {}
    for server, tools in server_map.SERVER_TOOLS.items():
        for tool in tools:
            assert tool not in seen, f"{tool} in {seen.get(tool)} and {server}"
            seen[tool] = server
            assert not tool.startswith(server_map.PERSONAL_PREFIXES), tool


@pytest.mark.parametrize("server", [s for s in server_map.SERVER_TOOLS])
def test_each_server_exposes_exactly_its_share(server, combined):
    built = _names(serve.build(server))
    assert built == server_map.SERVER_TOOLS[server] & combined
    assert built


def test_the_servers_together_are_the_whole_catalog(combined):
    union = set().union(*(_names(serve.build(s)) for s in server_map.SERVER_TOOLS))
    assert union == combined


def test_tools_are_the_same_objects_not_copies(combined):
    all_tools = serve.build(server_map.ALL)._tool_manager._tools
    remote = serve.build(server_map.REMOTE)._tool_manager._tools
    # Fresh loads build fresh objects, so compare what matters to a caller: schema and description.
    for name, tool in remote.items():
        assert tool.parameters == all_tools[name].parameters
        assert tool.description == all_tools[name].description


def test_remote_access_is_defined_once():
    factory_source = (MCP_DIR / "factory_server.py").read_text(encoding="utf-8")
    for tool in server_map.SERVER_TOOLS[server_map.REMOTE]:
        assert f"def {tool}(" not in factory_source, tool


def test_personal_server_only_for_allowed_agents(monkeypatch):
    monkeypatch.setenv("FORGEHUB_AGENT_SLUG", "athos")
    monkeypatch.delenv("FORGEHUB_PERSONAL_CONTACTS_AGENTS", raising=False)
    with pytest.raises(SystemExit, match="not authorized"):
        serve.build(server_map.PERSONAL)


def test_personal_server_for_the_maia(monkeypatch):
    monkeypatch.setenv("FORGEHUB_AGENT_SLUG", "maia")
    built = _names(serve.build(server_map.PERSONAL))
    assert built and all(name.startswith(server_map.PERSONAL_PREFIXES) for name in built)


def test_unknown_server_is_refused():
    with pytest.raises(SystemExit, match="Unknown ForgeHub MCP server"):
        serve.build("forgehub_everything")

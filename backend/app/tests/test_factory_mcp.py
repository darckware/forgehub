import pytest

from app.mcp import factory_server


def test_unified_mcp_registers_messages_and_factory_catalog():
    tools = factory_server.mcp._tool_manager._tools
    assert len(tools) == 44
    assert "send_agent_message" in tools
    assert "list_my_incubation" in tools
    assert "get_project_context" in tools
    assert "report_governance_blocker" in tools
    assert "list_agents" in tools
    assert "get_agent_profile" in tools
    assert "update_agent_profile" in tools
    assert "get_agent_profile_file" in tools
    assert "update_agent_profile_file" in tools
    assert "list_skills" in tools
    assert "grant_agent_skill" in tools
    assert "revoke_agent_skill" in tools
    assert "list_agent_tools" in tools
    assert "register_agent_tool" in tools
    assert "update_agent_tool" in tools
    assert "scan_agent_tools" in tools
    assert "sync_hermes_agents" in tools
    assert "get_system_status" in tools
    assert "list_system_backups" in tools
    assert "run_system_backup" in tools
    assert "list_audit_checks" in tools
    assert "run_audit_checks" in tools
    assert "list_deploy_containers" in tools
    assert "restart_deploy_container" in tools
    assert "get_container_logs" in tools
    assert "list_managed_servers" in tools
    assert "execute_database_query" in tools


async def test_project_screens_resolves_latest_scope_and_real_route(monkeypatch):
    calls = []

    async def fake_call(method, path, **kwargs):
        calls.append((method, path, kwargs))
        if path == "/api/v1/projects/project-1/scopes":
            return [
                {"id": "scope-1", "revision": 1, "created_at": "2026-08-01"},
                {"id": "scope-2", "revision": 2, "created_at": "2026-08-02"},
            ]
        if path == "/api/v1/project-scopes/scope-2/screens":
            return [{"id": "screen-1", "name": "Cockpit"}]
        raise AssertionError(path)

    monkeypatch.setattr(factory_server, "_factory_call", fake_call)
    result = await factory_server.list_project_screens("project-1")

    assert result["project_scope"]["id"] == "scope-2"
    assert result["screens"] == [{"id": "screen-1", "name": "Cockpit"}]
    assert [path for _, path, _ in calls] == [
        "/api/v1/projects/project-1/scopes",
        "/api/v1/project-scopes/scope-2/screens",
    ]


async def test_factory_failure_is_never_rewritten_as_empty_success(monkeypatch):
    async def failed_call(*args, **kwargs):
        raise factory_server.FactoryError("upstream denied the request")

    monkeypatch.setattr(factory_server, "_factory_call", failed_call)
    with pytest.raises(factory_server.FactoryError, match="upstream denied"):
        await factory_server.list_project_screens("project-1")


async def test_governance_blocker_creates_a_canonical_message(monkeypatch):
    captured = {}

    async def fake_message_call(method, path, **kwargs):
        captured.update({"method": method, "path": path, **kwargs})
        return {"id": "message-1", "number": 42}

    monkeypatch.setattr(factory_server.messages, "_resolve_agent", lambda value: "aramis")
    monkeypatch.setattr(factory_server.messages, "_call", fake_message_call)

    result = await factory_server.report_governance_blocker(
        "project-1",
        "planning-1",
        "Waiting for an operator decision",
        "request-1",
    )

    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/demands/submit"
    assert captured["json"]["project_id"] == "project-1"
    assert captured["json"]["development_request_id"] == "request-1"
    assert captured["json"]["channel_ref"] == "planning-item:planning-1"
    assert result["canonical_path"] == "/demands?message=message-1"


async def test_agent_profile_update_and_file_mcp(monkeypatch):
    captured = []

    async def fake_call(method, path, **kwargs):
        captured.append((method, path, kwargs))
        if method == "GET" and path == "/api/v1/agents":
            return [{"id": "agt-uuid-1", "name": "Athos", "profile_slug": "athos"}]
        if method == "PATCH" and path == "/api/v1/agents/agt-uuid-1":
            return {"id": "agt-uuid-1", "name": "Athos", "profile_slug": "athos", **kwargs.get("json", {})}
        if method == "GET" and path == "/api/v1/agents/agt-uuid-1/profile-files/SOUL.md":
            return {"filename": "SOUL.md", "path": "/root/.hermes/profiles/athos/SOUL.md", "exists": True, "content": "# Athos Soul"}
        if method == "PUT" and path == "/api/v1/agents/agt-uuid-1/profile-files/SOUL.md":
            return {"filename": "SOUL.md", "path": "/root/.hermes/profiles/athos/SOUL.md", "size_bytes": 12, "exists": True}
        raise AssertionError((method, path))

    monkeypatch.setattr(factory_server.messages, "_call", fake_call)

    # 1. Test update_agent_profile
    res_update = await factory_server.messages.update_agent_profile(
        agent="athos",
        mission="Primary orchestrator of development ecosystem",
        department="Engineering",
    )
    assert "Successfully updated agent" in res_update

    # 2. Test get_agent_profile_file
    res_get_file = await factory_server.messages.get_agent_profile_file("athos", "SOUL.md")
    assert "# Athos Soul" in res_get_file

    # 3. Test update_agent_profile_file
    res_put_file = await factory_server.messages.update_agent_profile_file("athos", "SOUL.md", "# New Soul")
    assert "Successfully saved SOUL.md" in res_put_file

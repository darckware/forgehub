"""MCP split Fase 2b: which delegation each sensitive MCP route needs (business rule MCP-023)."""
import pytest

from app.core.agent_mcp_actions import required_action

AGENT = "6f1c9a52-0000-4000-8000-000000000001"


@pytest.mark.parametrize("method, path, action", [
    ("GET", "/api/v1/system-stats", "ops.read"),
    ("GET", "/api/v1/system-control/backups", "ops.read"),
    ("POST", "/api/v1/system-control/backups/run", "ops.backup.run"),
    ("GET", "/api/v1/deploy/containers", "ops.read"),
    ("GET", "/api/v1/deploy/containers/forgehub-backend/logs", "ops.read"),
    ("POST", "/api/v1/deploy/containers/forgehub-backend/restart", "ops.deploy.restart"),
    ("GET", "/api/v1/audit/checks", "ops.read"),
    ("POST", "/api/v1/audit/run", "ops.audit.run"),
    ("POST", f"/api/v1/audit/checks/{AGENT}/run", "ops.audit.run"),
    ("GET", "/api/v1/servers", "ops.read"),
    ("POST", "/api/v1/database/query", "ops.database.query"),
    ("POST", f"/api/v1/agents/{AGENT}/credentials", "registry.credential.request"),
    ("GET", f"/api/v1/agents/{AGENT}/credentials", "registry.read"),
    ("DELETE", f"/api/v1/agents/{AGENT}/credentials/{AGENT}", "registry.manage"),
    ("GET", f"/api/v1/agents/{AGENT}/profile-files/SOUL.md", "registry.read"),
    ("PUT", f"/api/v1/agents/{AGENT}/profile-files/SOUL.md", "registry.manage"),
    ("POST", f"/api/v1/agents/{AGENT}/skills", "registry.manage"),
    ("DELETE", f"/api/v1/agents/{AGENT}/skills/{AGENT}", "registry.manage"),
    ("POST", "/api/v1/agents/sync/hermes-foundation", "registry.manage"),
    ("GET", "/api/v1/tools", "registry.read"),
    ("POST", "/api/v1/tools/scan", "registry.manage"),
    ("PATCH", f"/api/v1/tools/{AGENT}", "registry.manage"),
])
def test_sensitive_routes_map_to_their_action(method, path, action):
    assert required_action(method, path) == action


@pytest.mark.parametrize("method, path", [
    ("POST", "/api/v1/demands/submit"),                 # Messages: core server, never gated
    ("GET", "/api/v1/demands/pending"),
    ("GET", "/api/v1/agents"),                          # roster
    ("GET", "/api/v1/agents/skills"),                   # skills catalog, read by list_agent_skills
    ("GET", f"/api/v1/agents/{AGENT}/skills"),
    ("POST", "/api/v1/operations/agent-questions"),
    ("GET", "/api/v1/servers/readiness"),               # not the bridge-exposed list
    ("GET", "/api/v1/audit-something-else"),
])
def test_core_and_unrelated_routes_are_not_gated(method, path):
    assert required_action(method, path) is None

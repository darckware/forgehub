"""MCP split Fase 2b (MCP-023): only a restart and a direct database query can need approval, and only
outside the functions that do that work. Nothing is refused."""
import pytest

from app.core.agent_mcp_actions import required_action, within_function


def test_the_two_actions():
    assert required_action("POST", "/api/v1/deploy/containers/forgehub-backend/restart") == (
        "ops.deploy.restart", {"container": "forgehub-backend"})
    assert required_action("POST", "/api/v1/database/query") == ("ops.database.query", {})


@pytest.mark.parametrize("method, path", [
    ("POST", "/api/v1/demands/submit"), ("GET", "/api/v1/demands/pending"), ("GET", "/api/v1/agents"),
    ("GET", "/api/v1/system-stats"), ("GET", "/api/v1/audit/checks"), ("POST", "/api/v1/audit/run"),
    ("GET", "/api/v1/deploy/containers"), ("GET", "/api/v1/deploy/containers/x/logs"),
    ("POST", "/api/v1/system-control/backups/run"), ("GET", "/api/v1/servers"),
    ("GET", "/api/v1/agents/x/credentials"), ("POST", "/api/v1/agents/x/skills"), ("GET", "/api/v1/tools"),
    ("GET", "/api/v1/database/query"),
])
def test_everything_else_is_free_for_every_agent(method, path):
    assert required_action(method, path) is None


@pytest.mark.parametrize("department, action, expected", [
    ("Executive Orchestration", "ops.deploy.restart", True),
    ("Platform & Operations", "ops.deploy.restart", True),
    ("Security & Assurance", "ops.deploy.restart", False),
    ("Security & Assurance", "ops.database.query", True),
    ("Knowledge & Context", "ops.database.query", True),
    ("Documentation", "ops.database.query", False),
    (None, "ops.database.query", False),
    ("Marketing", "ops.deploy.restart", False),
])
def test_function_decides(department, action, expected):
    assert within_function(department, action) is expected

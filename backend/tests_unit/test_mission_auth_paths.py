"""M0.2 middleware: which paths an agt_ credential reaches (MCP_MISSION_TOOLS_SPEC.md §0.2, §9.5).

Pure predicate test (``main.is_agent_command_path``, what RequireAuthMiddleware
uses), no database: run with ``pytest --noconftest``. Every admitted mission
route still authorizes the agent itself (test_mission_mcp.py).
"""
import os

os.environ.setdefault("ENVIRONMENT", "test")

import pytest  # noqa: E402

from app.main import is_agent_command_path  # noqa: E402

PID = "11111111-1111-4111-8111-111111111111"


@pytest.mark.parametrize(("method", "path"), [
    ("POST", "/api/v1/missions"),
    ("GET", f"/api/v1/missions/{PID}"),
    ("PATCH", f"/api/v1/missions/{PID}"),
    ("POST", f"/api/v1/missions/{PID}:transition"),
    ("POST", f"/api/v1/missions/{PID}/planning:advance"),
    ("POST", f"/api/v1/missions/{PID}/members:apply"),
    # M0.2b: submit_project_plan / withdraw and add_task_dependency.
    ("POST", f"/api/v1/missions/{PID}/plans:submit"),
    ("POST", f"/api/v1/missions/{PID}/plans/{PID}:withdraw"),
    ("POST", f"/api/v1/tasks/{PID}/dependencies"),
    # Pre-existing agt_ surface, unchanged.
    ("GET", "/api/v1/projects"),
    ("GET", f"/api/v1/tasks/{PID}"),
    ("PATCH", f"/api/v1/tasks/{PID}"),
])
def test_agent_reaches_mission_paths(method, path):
    assert is_agent_command_path(method, path)


@pytest.mark.parametrize(("method", "path"), [
    ("POST", f"/api/v1/projects/plans/{PID}/approve"),
    ("POST", f"/api/v1/projects/{PID}/baselines"),
    ("POST", "/api/v1/projects"),
    ("PATCH", f"/api/v1/projects/{PID}"),
    ("DELETE", f"/api/v1/projects/{PID}"),
    ("POST", f"/api/v1/orchestration/projects/{PID}/memberships"),
    ("PATCH", f"/api/v1/orchestration/memberships/{PID}"),
    ("POST", "/api/v1/missionsx"),
    ("POST", "/api/v1/missions-admin/x"),
    ("POST", "/api/v1/tasks"),
    ("GET", "/api/v1/users"),
    # M0.2b: only adding a dependency; removing one and other task sub-paths stay human.
    ("DELETE", f"/api/v1/tasks/{PID}/dependencies/{PID}"),
    ("POST", f"/api/v1/tasks/{PID}/dependencies/{PID}"),
    ("POST", "/api/v1/tasks//dependencies"),
    ("POST", f"/api/v1/tasks/{PID}/required-skills"),
    ("POST", f"/api/v1/tasks/{PID}/assignments"),
])
def test_agent_does_not_reach_other_paths(method, path):
    assert not is_agent_command_path(method, path)

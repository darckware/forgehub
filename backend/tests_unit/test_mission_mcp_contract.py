"""M0.2a mission MCP contract, pure logic (MCP_MISSION_TOOLS_SPEC.md §0.3, §0.4, §5, §9.4).

No database and no network: run with ``pytest --noconftest``. ENVIRONMENT is
forced to ``test`` before any app import so the settings never read the
production ``.env``.
"""
import os

os.environ.setdefault("ENVIRONMENT", "test")

import uuid  # noqa: E402

import pytest  # noqa: E402

from app.api.routes.mission import _never_does_conflict  # noqa: E402
from app.core.command_receipts import _WriteRateLimiter, request_hash  # noqa: E402
from app.mcp import factory_server  # noqa: E402

HERMES_NEVER = "Editar código em qualquer repositório (abre Task para Aramis, Dartan ou Porthus)"


@pytest.mark.parametrize(("status", "detail", "expected"), [
    (409, {"code": "IDEMPOTENCY_KEY_REUSED", "message": "used"}, "failed (409): IDEMPOTENCY_KEY_REUSED: used"),
    (409, {"code": "PROJECT_NAME_EXISTS_IN_VERSION", "message": "exists", "project_id": "p1"},
     "failed (409): PROJECT_NAME_EXISTS_IN_VERSION: exists {'project_id': 'p1'}"),
    (401, "Invalid or expired agent credential", "failed (401): UNAUTHENTICATED: Invalid or expired agent credential"),
    (502, "bridge down", "failed (502): UPSTREAM_UNCERTAIN: bridge down"),
    (504, "timeout", "failed (504): UPSTREAM_UNCERTAIN: timeout"),
    (403, "No active delegation permits: x", "failed (403): No active delegation permits: x"),
    (429, {"code": "RATE_LIMITED", "message": "slow down"}, "failed (429): RATE_LIMITED: slow down"),
    (503, {"code": "MISSION_TOOLS_DISABLED", "message": "off"}, "failed (503): MISSION_TOOLS_DISABLED: off"),
])
def test_error_mapping(status, detail, expected):
    message = factory_server._error_message("POST", "/api/v1/missions", status, detail)
    assert message == f"ForgeHub POST /api/v1/missions {expected}"


def test_request_hash_ignores_key_and_order():
    a = request_hash("mission.x", {"name": "A", "idempotency_key": "k1", "n": [1, 2]})
    b = request_hash("mission.x", {"n": [1, 2], "idempotency_key": "k2", "name": "A"})
    assert a == b and len(a) == 64
    assert request_hash("mission.y", {"name": "A"}) != request_hash("mission.x", {"name": "A"})
    assert request_hash("mission.x", {"name": "B"}) != a
    assert request_hash("mission.x", {"id": uuid.UUID(int=1)}) == request_hash("mission.x", {"id": str(uuid.UUID(int=1))})


def test_rate_limiter_window():
    limiter = _WriteRateLimiter(limit=3, window_seconds=60)
    agent, other = uuid.uuid4(), uuid.uuid4()
    assert [limiter.hit(agent, now=t) for t in (0, 1, 2)] == [None, None, None]
    assert limiter.hit(agent, now=3) == pytest.approx(57)
    assert limiter.hit(other, now=3) is None  # per agent
    assert limiter.hit(agent, now=60.5) is None  # the first hit left the window


def test_never_does_conflicts():
    assert _never_does_conflict([HERMES_NEVER], "developer") == HERMES_NEVER
    assert _never_does_conflict([HERMES_NEVER], "data_engineer") == HERMES_NEVER
    assert _never_does_conflict([HERMES_NEVER], "reviewer") is None
    assert _never_does_conflict(["Atuar como qa"], "qa") == "Atuar como qa"
    assert _never_does_conflict(["Nunca ser release manager"], "release_manager") == "Nunca ser release manager"
    assert _never_does_conflict([], "developer") is None


async def test_mission_write_refuses_locally_without_network(monkeypatch):
    async def no_network(*args, **kwargs):
        raise AssertionError("must not call the API")

    monkeypatch.setattr(factory_server, "_factory_request", no_network)
    monkeypatch.setenv("FORGEHUB_AGENT_TOKEN", "agt_x")
    with pytest.raises(factory_server.FactoryError, match="PAYLOAD_TOO_LARGE"):
        await factory_server.create_internal_project(str(uuid.uuid4()), "n", "k", description="x" * (65 * 1024))
    with pytest.raises(factory_server.FactoryError, match="idempotency_key is required"):
        await factory_server.create_internal_project(str(uuid.uuid4()), "n", "  ")
    with pytest.raises(factory_server.FactoryError, match="At most 20"):
        await factory_server.manage_project_members(str(uuid.uuid4()), [{}] * 21, "k")


async def test_missing_or_non_agt_token_is_a_tool_error(monkeypatch):
    monkeypatch.delenv("FORGEHUB_AGENT_TOKEN", raising=False)
    with pytest.raises(factory_server.FactoryError, match="FORGEHUB_AGENT_TOKEN is required"):
        await factory_server.create_internal_project(str(uuid.uuid4()), "n", "k")
    monkeypatch.setenv("FORGEHUB_AGENT_TOKEN", "bridge-token-not-agt")
    with pytest.raises(factory_server.FactoryError, match="must be an agt_"):
        await factory_server.manage_project_members(str(uuid.uuid4()), [], "k")


async def test_tools_forward_the_contract(monkeypatch):
    sent = []

    class Response:
        def __init__(self, body, replay):
            self._body, self.headers = body, {"idempotent-replay": "true"} if replay else {}

        def json(self):
            return self._body

    async def fake(method, path, *, json=None, write=False):
        sent.append((method, path, json, write))
        if path == "/api/v1/missions":
            return Response({"project_id": "p", "project_type": "mission", "project_status": "planned",
                             "mission_state": "draft"}, replay=len(sent) > 1)
        return Response({"project_id": "p", "memberships": [], "applied": [], "violations": []}, replay=False)

    monkeypatch.setattr(factory_server, "_factory_request", fake)
    first = await factory_server.create_internal_project("v", "Name", "k1", executor_project_ids=["e"])
    again = await factory_server.create_internal_project("v", "Name", "k1", executor_project_ids=["e"])
    members = await factory_server.manage_project_members("p", [{"op": "add", "agent_id": "a", "role": "qa"}], "k2")
    assert first == {"project_id": "p", "project_type": "mission", "project_status": "planned",
                     "created": True, "replayed": False, "mission_state": "draft"}
    assert again["replayed"] is True and again["created"] is False
    assert members["replayed"] is False
    assert sent[0] == ("POST", "/api/v1/missions", {
        "product_version_id": "v", "name": "Name", "project_type": "mission", "idempotency_key": "k1",
        "executor_project_ids": ["e"]}, True)
    assert sent[2][1] == "/api/v1/missions/p/members:apply" and sent[2][3] is True


def test_tools_registered():
    tools = factory_server.mcp._tool_manager._tools
    assert {"create_internal_project", "manage_project_members", "attach_project_document",
            "get_my_mission_role", "list_my_tasks"} <= tools.keys()


async def test_m0_2d_tools_forward_the_contract(monkeypatch):
    sent = []

    class Response:
        status_code = 200
        headers: dict = {}

        def __init__(self, body):
            self._body = body

        def json(self):
            return self._body

    async def fake(method, path, *, json=None, write=False):
        sent.append((method, path, json, write))
        return Response({"doc_link_id": "l"} if method == "POST" else {"tasks": []})

    monkeypatch.setattr(factory_server, "_factory_request", fake)
    monkeypatch.setenv("FORGEHUB_AGENT_TOKEN", "agt_x")
    attached = await factory_server.attach_project_document("p", "project_task", "t", "missions/s/a.md", "k",
                                                            register_artifact=True, artifact_type="spec")
    await factory_server.get_my_mission_role("p")
    await factory_server.list_my_tasks("all")
    assert attached == {"doc_link_id": "l", "replayed": False}
    assert sent == [
        ("POST", "/api/v1/missions/p/documents", {
            "entity_type": "project_task", "entity_id": "t", "doc_path": "missions/s/a.md",
            "register_artifact": True, "idempotency_key": "k", "artifact_type": "spec"}, True),
        ("GET", "/api/v1/missions/p/me", None, False),
        ("GET", "/api/v1/missions/me/tasks?state=all", None, False),
    ]


async def test_attach_refuses_locally_without_key(monkeypatch):
    async def no_network(*args, **kwargs):
        raise AssertionError("must not call the API")

    monkeypatch.setattr(factory_server, "_factory_request", no_network)
    monkeypatch.setenv("FORGEHUB_AGENT_TOKEN", "agt_x")
    with pytest.raises(factory_server.FactoryError, match="idempotency_key is required"):
        await factory_server.attach_project_document("p", "project", "p", "missions/s/a.md", " ")


async def test_m0_2c_tools_forward_the_contract(monkeypatch):
    sent = []

    class Response:
        status_code = 200
        headers: dict = {}

        def __init__(self, body):
            self._body = body

        def json(self):
            return self._body

    async def fake(method, path, *, json=None, write=False):
        sent.append((method, path, json, write))
        if method == "GET":
            return Response([{"id": "e1", "attempt_number": 1, "status": "verified"},
                             {"id": "e2", "attempt_number": 2, "status": "running"}])
        return Response({"ok": True})

    monkeypatch.setattr(factory_server, "_factory_request", fake)
    monkeypatch.setenv("FORGEHUB_AGENT_TOKEN", "agt_x")
    await factory_server.assign_task("p", "t", "a", "fit", "k1")
    await factory_server.dispatch_task("t", "k2", command_text="go", scheduled_at="2030-01-01T00:00:00Z")
    await factory_server.report_task_execution("t", "reported", "done", ["git:abc1234"], "k3")
    await factory_server.request_task_review("p", "t", "e2", "r", "k4")
    await factory_server.return_task_for_correction("p", "t", "e2", "redo", "k5")
    assert sent == [
        ("POST", "/api/v1/missions/p/tasks/t:assign", {"agent_id": "a", "reason": "fit", "idempotency_key": "k1"},
         True),
        ("POST", "/api/v1/tasks/t/dispatch", {"idempotency_key": "k2", "command_text": "go",
                                              "scheduled_at": "2030-01-01T00:00:00Z"}, True),
        ("GET", "/api/v1/tasks/t/executions", None, False),
        ("POST", "/api/v1/tasks/t/executions/e2:report", {"status": "reported", "summary": "done",
                                                          "evidence": ["git:abc1234"], "idempotency_key": "k3"}, True),
        ("POST", "/api/v1/missions/p/tasks/t:request-review", {"execution_id": "e2", "reviewer_agent_id": "r",
                                                               "idempotency_key": "k4"}, True),
        ("POST", "/api/v1/missions/p/tasks/t:return", {"execution_id": "e2", "reason": "redo",
                                                       "idempotency_key": "k5"}, True),
    ]


async def test_m0_2c_tools_refuse_locally(monkeypatch):
    async def no_network(*args, **kwargs):
        raise AssertionError("must not call the API")

    monkeypatch.setattr(factory_server, "_factory_request", no_network)
    monkeypatch.setenv("FORGEHUB_AGENT_TOKEN", "agt_x")
    for status in ("verified", "completed", "DONE"):
        with pytest.raises(factory_server.FactoryError, match="never verified/completed"):
            await factory_server.report_task_execution("t", status, "s", ["git:abc1234"], "k", execution_id="e")
    with pytest.raises(factory_server.FactoryError, match="4000"):
        await factory_server.dispatch_task("t", "k", command_text="x" * 4001)
    with pytest.raises(factory_server.FactoryError, match="idempotency_key is required"):
        await factory_server.dispatch_task("t", " ")

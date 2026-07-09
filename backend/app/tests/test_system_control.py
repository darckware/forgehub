"""Tests for System Control: per-repo Git status (KNOWN_REPOS) and the
Hermes backup delete endpoint. Doesn't hit the real host-bridge (none runs
against this test environment) -- a fake httpx client scoped to
system_control.py's own `httpx` name stands in, same pattern as
test_demand.py's test_notify_telegram_proxies_to_bridge.
"""
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token


def _admin_headers() -> dict[str, str]:
    # Real seeded admin user (see .env's DEV_USER_USERNAME) -- system
    # control's routes are gated with Depends(get_current_admin), which
    # looks the username up in the DB and checks is_admin, so an arbitrary
    # token subject (as other domains' tests use) won't pass here.
    return {"Authorization": f"Bearer {create_access_token('admin')}"}


@pytest_asyncio.fixture
async def client():
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=_admin_headers()) as ac:
        yield ac


class FakeResponse:
    def __init__(self, json_body, status_code=200):
        self._json = json_body
        self.status_code = status_code
        self.text = str(json_body)

    def json(self):
        return self._json


def _git_ok(stdout: str = "") -> FakeResponse:
    return FakeResponse({"exit_code": 0, "stdout": stdout, "stderr": ""})


class FakeBridgeClient:
    """Records every call and answers with just enough to satisfy
    get_system_control_status's sequence of git/fs calls, or a delete."""

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def request(self, method, url, headers=None, json=None, params=None, **kwargs):
        FakeBridgeClient.calls.append((method, url, json, params))
        if url.endswith("/v1/exec"):
            command = (json or {}).get("command", "")
            if "rev-parse HEAD" in command or "rev-parse --short HEAD" in command:
                return _git_ok("abc1234")
            if "branch --show-current" in command:
                return _git_ok("main")
            if "log -1" in command:
                return _git_ok("abc1234\nSome Author\nMon Jan 1\nA commit")
            if "status --short" in command:
                return _git_ok("")
            return _git_ok("")
        if url.endswith("/v1/fs/mkdir"):
            return FakeResponse({"status": "ok"})
        if url.endswith("/v1/fs/list"):
            return FakeResponse({"entries": []})
        if url.endswith("/v1/fs/delete"):
            return FakeResponse({"status": "ok"})
        raise AssertionError(f"Unexpected bridge call: {method} {url}")

    calls: list = []


async def test_status_defaults_to_default_repo(client: AsyncClient, monkeypatch):
    from app.api.routes import system_control as sc

    FakeBridgeClient.calls = []
    monkeypatch.setattr(sc.httpx, "AsyncClient", FakeBridgeClient)

    resp = await client.get("/api/v1/system-control/status")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["git"]["repo_key"] == "forgehub"
    assert body["git"]["repo_root"] == "/root/project/forgehub"
    assert {"key": "forgehub", "path": "/root/project/forgehub"} in body["available_repos"]
    assert {"key": "forgerouter", "path": "/root/project/forgerouter"} in body["available_repos"]


async def test_status_with_known_repo_key_switches_repo_root(client: AsyncClient, monkeypatch):
    from app.api.routes import system_control as sc

    FakeBridgeClient.calls = []
    monkeypatch.setattr(sc.httpx, "AsyncClient", FakeBridgeClient)

    resp = await client.get("/api/v1/system-control/status", params={"repo": "forgerouter"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["git"]["repo_key"] == "forgerouter"
    assert body["git"]["repo_root"] == "/root/project/forgerouter"
    exec_commands = [c[2]["command"] for c in FakeBridgeClient.calls if c[1].endswith("/v1/exec")]
    assert all("/root/project/forgerouter" in cmd for cmd in exec_commands)


async def test_status_unknown_repo_key_falls_back_to_default(client: AsyncClient, monkeypatch):
    from app.api.routes import system_control as sc

    FakeBridgeClient.calls = []
    monkeypatch.setattr(sc.httpx, "AsyncClient", FakeBridgeClient)

    resp = await client.get("/api/v1/system-control/status", params={"repo": "does-not-exist"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["git"]["repo_key"] == "forgehub"


async def test_delete_backup_rejects_path_traversal(client: AsyncClient, monkeypatch):
    from app.api.routes import system_control as sc

    FakeBridgeClient.calls = []
    monkeypatch.setattr(sc.httpx, "AsyncClient", FakeBridgeClient)

    # A slash-containing attempt (e.g. "../../etc/passwd") never reaches the
    # handler at all -- Starlette's single-segment {filename} path converter
    # 404s on embedded slashes before routing gets there, and a literal ".."
    # segment gets collapsed by httpx's own URL normalization before the
    # request is even sent (same as a browser fetch() would). %2e%2e (the
    # percent-encoded form) survives that client-side normalization -- by
    # the time Starlette decodes it into the `filename` path param, the
    # in-handler check is the only thing standing between it and the
    # bridge, which is exactly what this test is for.
    resp = await client.delete("/api/v1/system-control/backup/%2e%2e")
    assert resp.status_code == 400
    assert FakeBridgeClient.calls == []


async def test_commit_stages_and_commits(client: AsyncClient, monkeypatch):
    from app.api.routes import system_control as sc

    FakeBridgeClient.calls = []
    monkeypatch.setattr(sc.httpx, "AsyncClient", FakeBridgeClient)

    resp = await client.post("/api/v1/system-control/commit", json={"message": "Fix the thing"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["repo_key"] == "forgehub"
    assert body["hash"] == "abc1234"
    assert body["subject"] == "A commit"

    exec_commands = [c[2]["command"] for c in FakeBridgeClient.calls if c[1].endswith("/v1/exec")]
    assert any("add -A" in cmd and "/root/project/forgehub" in cmd for cmd in exec_commands)
    assert any("commit -m" in cmd and "Fix the thing" in cmd for cmd in exec_commands)


async def test_commit_with_specific_repo(client: AsyncClient, monkeypatch):
    from app.api.routes import system_control as sc

    FakeBridgeClient.calls = []
    monkeypatch.setattr(sc.httpx, "AsyncClient", FakeBridgeClient)

    resp = await client.post(
        "/api/v1/system-control/commit", json={"message": "Router fix", "repo": "forgerouter"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["repo_key"] == "forgerouter"
    exec_commands = [c[2]["command"] for c in FakeBridgeClient.calls if c[1].endswith("/v1/exec")]
    assert any("/root/project/forgerouter" in cmd and "add -A" in cmd for cmd in exec_commands)


async def test_commit_rejects_empty_message(client: AsyncClient, monkeypatch):
    from app.api.routes import system_control as sc

    FakeBridgeClient.calls = []
    monkeypatch.setattr(sc.httpx, "AsyncClient", FakeBridgeClient)

    resp = await client.post("/api/v1/system-control/commit", json={"message": ""})
    assert resp.status_code == 422
    assert FakeBridgeClient.calls == []


async def test_delete_backup_calls_bridge_delete(client: AsyncClient, monkeypatch):
    from app.api.routes import system_control as sc

    FakeBridgeClient.calls = []
    monkeypatch.setattr(sc.httpx, "AsyncClient", FakeBridgeClient)

    resp = await client.delete("/api/v1/system-control/backup/hermes-backup-20260101-000000.tar.gz")
    assert resp.status_code == 204, resp.text
    delete_calls = [c for c in FakeBridgeClient.calls if c[1].endswith("/v1/fs/delete")]
    assert len(delete_calls) == 1
    assert delete_calls[0][3] == {"path": "/root/backup/hermes-backup-20260101-000000.tar.gz", "recursive": False}

"""Tests for System Control: per-repo Git status (KNOWN_REPOS + registered
Projects) and the backup endpoints. Doesn't hit the real host-bridge (none
runs against this test environment) -- a fake httpx client scoped to
system_control.py's own `httpx` name stands in, same pattern as
test_demand.py's test_notify_telegram_proxies_to_bridge.
"""
import uuid
from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db.base import AsyncSessionLocal
from app.db.models.product import Product, ProductVersion
from app.db.models.project import Project


@pytest_asyncio.fixture
async def client(admin_headers):
    # system control's routes are gated with Depends(get_current_admin),
    # which checks a real active admin row -- see conftest's admin_headers.
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=admin_headers) as ac:
        yield ac


@pytest_asyncio.fixture
async def test_project():
    """A real registered Project with a working_directory_path -- Git
    Control/Backup's only source for non-Hermes entries now that there's no
    separate ad-hoc registry (see system_control.py's module docstring)."""
    async with AsyncSessionLocal() as session:
        product = Product(name=f"System Control Test Product {uuid.uuid4()}")
        session.add(product)
        await session.flush()
        version = ProductVersion(product_id=product.id, version="0.1.0")
        session.add(version)
        await session.flush()
        project = Project(
            name=f"System Control Test Project {uuid.uuid4()}",
            product_version_id=version.id,
            working_directory_path="/root/project/forgerouter",
            backup_enabled=True,
        )
        session.add(project)
        await session.commit()
        await session.refresh(project)
        yield project
        await session.delete(project)
        await session.delete(version)
        await session.delete(product)
        await session.commit()


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
            if "find " in command:
                lines = []
                if "/profiles/*/logs/" in command or "*.bak*" in command or "cron/output" in command:
                    lines.extend([
                        "1024|1700000000.0|/root/.hermes/profiles/athos/logs/agent.log",
                        "2048|1700000001.0|/root/.hermes/profiles/athos/logs/errors.log",
                        "999|1700000005.0|/root/.hermes/profiles/daedalus/logs/errors.log.1",
                        "512|1700000002.0|/root/.hermes/profiles/athos/cron/logs/some_script.log",
                        "256|1700000003.0|/root/.hermes/profiles/aegis/.env.bak.20260519-005445",
                        "128|1700000004.0|/root/.hermes/profiles/athos/cron/output/42335b7194a4/2026-05-22_15-07-11.md",
                    ])
                if lines:
                    return _git_ok("\n".join(lines) + "\n")
            if "rm -rf --" in command and "deleted_items" in command:
                return _git_ok("deleted_items: 3\nremaining_items: 0")
            return _git_ok("")
        if url.endswith("/v1/fs/mkdir"):
            return FakeResponse({"status": "ok"})
        if url.endswith("/v1/fs/list"):
            return FakeResponse({"entries": []})
        if url.endswith("/v1/fs/delete"):
            return FakeResponse({"status": "ok"})
        if url.endswith("/v1/system/hermes-backup"):
            backup_dir = (json or {}).get("backup_dir", "/root/backup")
            archive_name = (json or {}).get("archive_name", "backup-20260101-000000.tar.gz")
            return FakeResponse(
                {
                    "status": "ok",
                    "source_path": (json or {}).get("source_path"),
                    "archive_path": f"{backup_dir}/{archive_name}",
                    "size_bytes": 1024,
                }
            )
        raise AssertionError(f"Unexpected bridge call: {method} {url}")

    calls: list = []


async def test_status_defaults_to_default_repo(client: AsyncClient, monkeypatch):
    from app.api.routes import system_control as sc

    FakeBridgeClient.calls = []
    monkeypatch.setattr(sc.httpx, "AsyncClient", FakeBridgeClient)

    resp = await client.get("/api/v1/system-control/status")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["git"]["repo_key"] == "hermes"
    assert body["git"]["repo_root"] == "/root/.hermes"
    assert any(r["key"] == "hermes" and r["path"] == "/root/.hermes" for r in body["available_repos"])


async def test_status_with_known_repo_key_switches_repo_root(client: AsyncClient, monkeypatch, test_project):
    from app.api.routes import system_control as sc

    FakeBridgeClient.calls = []
    monkeypatch.setattr(sc.httpx, "AsyncClient", FakeBridgeClient)

    repo_key = f"project:{test_project.id}"
    resp = await client.get("/api/v1/system-control/status", params={"repo": repo_key})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["git"]["repo_key"] == repo_key
    assert body["git"]["repo_root"] == test_project.working_directory_path
    assert any(
        r["key"] == repo_key and r["kind"] == "project" and r["label"] == test_project.name
        for r in body["available_repos"]
    )
    exec_commands = [c[2]["command"] for c in FakeBridgeClient.calls if c[1].endswith("/v1/exec")]
    assert all(test_project.working_directory_path in cmd for cmd in exec_commands)


async def test_status_unknown_repo_key_falls_back_to_default(client: AsyncClient, monkeypatch):
    from app.api.routes import system_control as sc

    FakeBridgeClient.calls = []
    monkeypatch.setattr(sc.httpx, "AsyncClient", FakeBridgeClient)

    resp = await client.get("/api/v1/system-control/status", params={"repo": "does-not-exist"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["git"]["repo_key"] == "hermes"


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
    resp = await client.delete("/api/v1/system-control/backups/hermes/%2e%2e")
    assert resp.status_code == 400
    assert FakeBridgeClient.calls == []


async def test_commit_stages_and_commits(client: AsyncClient, monkeypatch):
    from app.api.routes import system_control as sc

    FakeBridgeClient.calls = []
    monkeypatch.setattr(sc.httpx, "AsyncClient", FakeBridgeClient)

    resp = await client.post("/api/v1/system-control/commit", json={"message": "Fix the thing"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["repo_key"] == "hermes"
    assert body["hash"] == "abc1234"
    assert body["subject"] == "A commit"

    exec_commands = [c[2]["command"] for c in FakeBridgeClient.calls if c[1].endswith("/v1/exec")]
    assert any("add -A" in cmd and "/root/.hermes" in cmd for cmd in exec_commands)
    assert any("commit -m" in cmd and "Fix the thing" in cmd for cmd in exec_commands)


async def test_commit_with_specific_repo(client: AsyncClient, monkeypatch, test_project):
    from app.api.routes import system_control as sc

    FakeBridgeClient.calls = []
    monkeypatch.setattr(sc.httpx, "AsyncClient", FakeBridgeClient)

    repo_key = f"project:{test_project.id}"
    resp = await client.post(
        "/api/v1/system-control/commit", json={"message": "Router fix", "repo": repo_key}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["repo_key"] == repo_key
    exec_commands = [c[2]["command"] for c in FakeBridgeClient.calls if c[1].endswith("/v1/exec")]
    assert any(test_project.working_directory_path in cmd and "add -A" in cmd for cmd in exec_commands)


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

    resp = await client.delete("/api/v1/system-control/backups/hermes/hermes-backup-20260101-000000.tar.gz")
    assert resp.status_code == 204, resp.text
    delete_calls = [c for c in FakeBridgeClient.calls if c[1].endswith("/v1/fs/delete")]
    assert len(delete_calls) == 1
    assert delete_calls[0][3] == {"path": "/root/backup/hermes-backup-20260101-000000.tar.gz", "recursive": False}


async def test_backup_targets_lists_hermes_and_enabled_projects(client: AsyncClient, monkeypatch, test_project):
    from app.api.routes import system_control as sc

    FakeBridgeClient.calls = []
    monkeypatch.setattr(sc.httpx, "AsyncClient", FakeBridgeClient)

    resp = await client.get("/api/v1/system-control/backup-targets")
    assert resp.status_code == 200, resp.text
    targets = {t["key"]: t for t in resp.json()["targets"]}
    assert targets["hermes"] == {
        "key": "hermes", "label": "Hermes", "kind": "system", "ready": True,
        "source": "/root/.hermes", "location": "/root/backup",
    }
    project_key = f"project:{test_project.id}"
    assert targets[project_key]["label"] == test_project.name
    assert targets[project_key]["ready"] is True
    # No backup_location set on the fixture -- defaults to BACKUP_DIR/<slug>.
    assert targets[project_key]["location"] == f"/root/backup/{sc._project_slug(test_project)}"


async def test_run_backup_all_fans_out_to_hermes_and_projects(client: AsyncClient, monkeypatch, test_project):
    from app.api.routes import system_control as sc

    FakeBridgeClient.calls = []
    monkeypatch.setattr(sc.httpx, "AsyncClient", FakeBridgeClient)

    resp = await client.post("/api/v1/system-control/backups/run", json={"target": "all"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["errors"] == []
    # Superset, not equality -- "all" also fans out to any other
    # already-registered backup_enabled project (e.g. ForgeHub/ForgeRouter
    # in a real environment), not just this test's own fixture.
    result_targets = {r["target"] for r in body["results"]}
    assert result_targets >= {"hermes", f"project:{test_project.id}"}

    backup_calls = [c for c in FakeBridgeClient.calls if c[1].endswith("/v1/system/hermes-backup")]
    backup_dirs = {c[2]["backup_dir"] for c in backup_calls}
    assert "/root/backup" in backup_dirs
    # No backup_location set on the fixture -- defaults to
    # BACKUP_DIR/<slug-of-name> (see _project_backup_location).
    assert f"/root/backup/{sc._project_slug(test_project)}" in backup_dirs


async def test_cleanup_scan_groups_logs_by_category(client: AsyncClient, monkeypatch):
    from app.api.routes import system_control as sc

    FakeBridgeClient.calls = []
    monkeypatch.setattr(sc.httpx, "AsyncClient", FakeBridgeClient)
    # Isolate this test from the real ~/.hermes scripts registry -- covered
    # separately by test_cleanup_scan_includes_old_and_duplicate_scripts.
    async def fake_script_categories(_db):
        return [], []

    monkeypatch.setattr(sc, "_script_categories", fake_script_categories)

    resp = await client.get("/api/v1/system-control/cleanup-scan")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_count"] == 6
    assert body["total_size"] == 1024 + 2048 + 999 + 512 + 256 + 128
    categories = {c["category"]: c for c in body["categories"]}
    assert categories["Agent logs"]["count"] == 1
    # errors.log AND its rotated errors.log.1 both categorize the same way.
    assert categories["Error logs"]["count"] == 2
    assert categories["Cron execution logs"]["count"] == 1
    assert categories["Agent logs"]["files"][0]["name"] == "agent.log"
    assert categories["Backup files"]["count"] == 1
    assert categories["Backup files"]["files"][0]["name"] == ".env.bak.20260519-005445"
    assert categories["Cron output files"]["count"] == 1
    assert categories["Cron output files"]["files"][0]["name"] == "2026-05-22_15-07-11.md"


async def test_cleanup_scan_includes_old_and_duplicate_scripts(client: AsyncClient, monkeypatch, tmp_path):
    from app.api.routes import foundation as fnd
    from app.api.routes import system_control as sc

    FakeBridgeClient.calls = []
    monkeypatch.setattr(sc.httpx, "AsyncClient", FakeBridgeClient)

    unused = tmp_path / "unused_script.sh"
    unused.write_text("echo unused\n")
    dup_a = tmp_path / "dup_a.sh"
    dup_a.write_text("echo same content\n")
    dup_b = tmp_path / "dup_b.sh"
    dup_b.write_text("echo same content\n")
    ok_script = tmp_path / "ok_script.sh"
    ok_script.write_text("echo referenced\n")

    async def fake_list_scripts(_db):
        scripts = [
            fnd.ScriptOut(
                name=p.name, location="testprofile", agent="testprofile", description=None, path=str(p),
                exists=True, is_symlink=False, symlink_target=None, executable=True,
                escapes_scripts_dir=False, status=status_val, referenced_by=[],
            )
            for p, status_val in [(unused, "unused"), (dup_a, "unused"), (dup_b, "unused"), (ok_script, "ok")]
        ]
        contents = {("testprofile", s.name): Path(s.path).read_bytes() for s in scripts}
        return scripts, contents

    monkeypatch.setattr(fnd, "_list_scripts", fake_list_scripts)

    resp = await client.get("/api/v1/system-control/cleanup-scan")
    assert resp.status_code == 200, resp.text
    categories = {c["category"]: c for c in resp.json()["categories"]}

    old_names = {f["name"] for f in categories["Old/unused scripts"]["files"]}
    assert old_names == {"testprofile/unused_script.sh", "testprofile/dup_a.sh", "testprofile/dup_b.sh"}

    dup_names = {f["name"] for f in categories["Duplicate scripts"]["files"]}
    assert dup_names == {"testprofile/dup_a.sh", "testprofile/dup_b.sh"}


async def test_cleanup_run_uses_authoritative_athos_policy(client: AsyncClient, monkeypatch):
    """Manual UI execution and the weekly cron use the same script."""
    from app.api.routes import system_control as sc

    FakeBridgeClient.calls = []
    monkeypatch.setattr(sc.httpx, "AsyncClient", FakeBridgeClient)

    resp = await client.post("/api/v1/system-control/cleanup-run")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["trash_root"] == sc.TRASH_ROOT
    assert body["script"] == sc.CLEANUP_SCRIPT
    assert body["policy"] == "no-docker-volume-prune"
    exec_commands = [c[2]["command"] for c in FakeBridgeClient.calls if c[1].endswith("/v1/exec")]
    assert exec_commands == [
        f"TRASH_DIR={sc.TRASH_ROOT} BACKUP_ROOT={sc.BACKUP_DIR} bash {sc.CLEANUP_SCRIPT}"
    ]
    cleanup_call = next(c for c in FakeBridgeClient.calls if c[1].endswith("/v1/exec"))
    assert cleanup_call[2]["timeout_seconds"] == 600


async def test_status_graceful_when_git_fails(client: AsyncClient, monkeypatch):
    """When a repo is not a git repository or git fails, status endpoint falls back gracefully without 500."""
    from app.api.routes import system_control as sc

    class FailingGitBridge(FakeBridgeClient):
        async def request(self, method, url, headers=None, json=None, params=None, **kwargs):
            if url.endswith("/v1/exec") and "git -C" in (json or {}).get("command", ""):
                return FakeResponse({"exit_code": 128, "stdout": "", "stderr": "fatal: not a git repository"}, status_code=200)
            return await super().request(method, url, headers=headers, json=json, params=params, **kwargs)

    FakeBridgeClient.calls = []
    monkeypatch.setattr(sc.httpx, "AsyncClient", FailingGitBridge)

    resp = await client.get("/api/v1/system-control/status", params={"repo": "hermes"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["git"]["branch"] == "detached"
    assert body["git"]["head"] == ""



class FakeDockerBridge(FakeBridgeClient):
    """Answers the Docker card's commands with real-shaped output."""

    async def request(self, method, url, headers=None, json=None, params=None, **kwargs):
        FakeBridgeClient.calls.append((method, url, json, params))
        command = (json or {}).get("command", "")
        if command.startswith("df -B1"):
            return _git_ok(
                "207000000000 168000000000 39000000000\n__SECTION__\n"
                '{"Active":"16","Reclaimable":"10.61GB (44%)","Size":"23.98GB","TotalCount":"78","Type":"Images"}\n'
                '{"Active":"8","Reclaimable":"88.65GB","Size":"92.26GB","TotalCount":"333","Type":"Build Cache"}\n'
                "__SECTION__\n"
                '{"ID":"sha256:used","Repository":"forgehub-backend","Tag":"latest","Size":"660MB","CreatedAt":"x","CreatedSince":"1 hour ago"}\n'
                '{"ID":"sha256:old","Repository":"forgehub-frontend","Tag":"rollback-a","Size":"111MB","CreatedAt":"y","CreatedSince":"1 day ago"}\n'
                '{"ID":"sha256:dangling","Repository":"<none>","Tag":"<none>","Size":"1.5GB","CreatedAt":"z","CreatedSince":"9 days ago"}\n'
                "__SECTION__\nsha256:used\n"
            )
        if command.startswith("docker builder prune"):
            return _git_ok("ID\nabc\nTotal:\t88.65GB\n")
        if command.startswith("docker image prune"):
            return _git_ok("Deleted Images:\nx\nTotal reclaimed space: 10.61GB\n")
        raise AssertionError(f"Unexpected bridge call: {command}")


async def test_docker_usage_parses_sizes_and_lists_only_unused_images(client: AsyncClient, monkeypatch):
    from app.api.routes import system_control as sc

    FakeBridgeClient.calls = []
    monkeypatch.setattr(sc.httpx, "AsyncClient", FakeDockerBridge)

    resp = await client.get("/api/v1/system-control/docker-usage")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["disk"] == {"total": 207000000000, "used": 168000000000, "available": 39000000000}
    build = next(t for t in body["types"] if t["type"] == "Build Cache")
    assert build["size"] == 92_260_000_000
    assert build["reclaimable"] == 88_650_000_000
    images = next(t for t in body["types"] if t["type"] == "Images")
    assert images["reclaimable"] == 10_610_000_000  # "(44%)" suffix ignored
    # The image a container points at is not "unused"; largest first.
    assert [i["name"] for i in body["unused_images"]] == ["<none>", "forgehub-frontend:rollback-a"]


async def test_docker_prune_runs_only_selected_steps_and_never_volumes(client: AsyncClient, monkeypatch):
    from app.api.routes import system_control as sc

    FakeBridgeClient.calls = []
    monkeypatch.setattr(sc.httpx, "AsyncClient", FakeDockerBridge)

    resp = await client.post("/api/v1/system-control/docker:prune", json={"build_cache": True})
    assert resp.status_code == 200, resp.text
    assert resp.json()["results"] == {"build_cache": "Total:\t88.65GB"}
    commands = [c[2]["command"] for c in FakeBridgeClient.calls]
    assert commands == ["docker builder prune --all --force"]

    FakeBridgeClient.calls = []
    resp = await client.post(
        "/api/v1/system-control/docker:prune", json={"build_cache": True, "unused_images": True}
    )
    assert resp.status_code == 200, resp.text
    commands = [c[2]["command"] for c in FakeBridgeClient.calls]
    assert commands == ["docker builder prune --all --force", "docker image prune --all --force"]
    assert not any("volume" in c for c in commands)


async def test_docker_prune_rejects_empty_selection(client: AsyncClient, monkeypatch):
    from app.api.routes import system_control as sc

    FakeBridgeClient.calls = []
    monkeypatch.setattr(sc.httpx, "AsyncClient", FakeDockerBridge)
    resp = await client.post("/api/v1/system-control/docker:prune", json={})
    assert resp.status_code == 400
    assert FakeBridgeClient.calls == []


async def test_backup_listing_skips_hidden_lock_file(client: AsyncClient, monkeypatch):
    """backup_hermes_root.sh leaves .backup_hermes_root.lock in BACKUP_DIR; it
    was being listed (and counted) as a backup archive."""
    from app.api.routes import system_control as sc

    class LockListing(FakeBridgeClient):
        async def request(self, method, url, headers=None, json=None, params=None, **kwargs):
            if url.endswith("/v1/fs/list"):
                return FakeResponse({"entries": [
                    {"name": ".backup_hermes_root.lock", "path": "/root/backup/.backup_hermes_root.lock", "size": 0, "type": "file"},
                    {"name": "hermes-backup-1.tar.gz", "path": "/root/backup/hermes-backup-1.tar.gz", "size": 9, "type": "file"},
                ]})
            return await super().request(method, url, headers=headers, json=json, params=params, **kwargs)

    FakeBridgeClient.calls = []
    monkeypatch.setattr(sc.httpx, "AsyncClient", LockListing)

    resp = await client.get("/api/v1/system-control/backups", params={"target": "hermes"})
    assert resp.status_code == 200, resp.text
    assert [e["name"] for e in resp.json()["entries"]] == ["hermes-backup-1.tar.gz"]

    resp = await client.get("/api/v1/system-control/status")
    assert resp.status_code == 200, resp.text
    assert resp.json()["backups"]["count"] == 1


class FakeBackupBridge(FakeBridgeClient):
    """Answers the backup scan with real-shaped JSON and records the move command."""

    scan = [
        {"path": "/root/backup/forgehub-20260907", "group": "archives", "size": 356_000_000, "mtime": 1789000000.0, "is_dir": True, "protected": None},
        {"path": "/root/backup/hermes-root/weekly/host_2026-W39.tar.zst", "group": "hermes_weekly", "size": 1_200_000_000, "mtime": 1790000000.0, "is_dir": False, "protected": "Newest weekly Hermes backup (latest recovery point)"},
        {"path": "/tmp/db_transfer/foundation.sql.gz", "group": "tmp_dumps", "size": 61_000_000, "mtime": 1788000000.0, "is_dir": False, "protected": None},
    ]

    async def request(self, method, url, headers=None, json=None, params=None, **kwargs):
        import json as _json

        FakeBridgeClient.calls.append((method, url, json, params))
        command = (json or {}).get("command", "")
        if command.startswith("python3 - <<'PYEOF'"):
            return _git_ok(_json.dumps(self.scan))
        if command.startswith("mkdir -p"):
            return _git_ok("")
        raise AssertionError(f"Unexpected bridge call: {command[:80]}")


async def test_backup_files_are_grouped_and_protected_is_not_reclaimable(client: AsyncClient, monkeypatch):
    from app.api.routes import system_control as sc

    FakeBridgeClient.calls = []
    monkeypatch.setattr(sc.httpx, "AsyncClient", FakeBackupBridge)
    resp = await client.get("/api/v1/system-control/backup-files")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_count"] == 3
    assert body["reclaimable_size"] == 356_000_000 + 61_000_000
    assert [g["group"] for g in body["groups"]] == ["archives", "hermes_weekly", "tmp_dumps"]


async def test_backup_delete_refuses_protected_and_unknown_paths(client: AsyncClient, monkeypatch):
    from app.api.routes import system_control as sc

    FakeBridgeClient.calls = []
    monkeypatch.setattr(sc.httpx, "AsyncClient", FakeBackupBridge)
    resp = await client.post("/api/v1/system-control/backup-files/delete", json={"paths": [
        "/root/backup/hermes-root/weekly/host_2026-W39.tar.zst", "/etc/passwd",
    ]})
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["protected"] == ["/root/backup/hermes-root/weekly/host_2026-W39.tar.zst"]
    assert detail["unknown"] == ["/etc/passwd"]
    assert not any((c[2] or {}).get("command", "").startswith("mkdir -p") for c in FakeBridgeClient.calls)


async def test_backup_delete_moves_selected_items_to_trash(client: AsyncClient, monkeypatch):
    from app.api.routes import system_control as sc

    FakeBridgeClient.calls = []
    monkeypatch.setattr(sc.httpx, "AsyncClient", FakeBackupBridge)
    resp = await client.post("/api/v1/system-control/backup-files/delete", json={"paths": [
        "/root/backup/forgehub-20260907", "/tmp/db_transfer/foundation.sql.gz",
    ]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["count"] == 2 and resp.json()["total_size"] == 417_000_000
    move = next(c[2]["command"] for c in FakeBridgeClient.calls if c[2]["command"].startswith("mkdir -p"))
    assert f"{sc.TRASH_ROOT}/cleanup-manual/backups/" in move
    assert "mv -- /root/backup/forgehub-20260907 " in move and "rm " not in move

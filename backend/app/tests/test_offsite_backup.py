"""Off-site backup control (api/routes/offsite_backup.py): the target list the
operator edits on System Control, and the internal endpoints Athos' worker
reports through. The host-bridge is replaced by a recorder -- nothing here
touches the host."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.api.routes import offsite_backup as route
from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.db.base import AsyncSessionLocal
from app.db.models.notification import Notification
from app.db.models.offsite_backup import OffsiteBackupRun, OffsiteBackupTarget
from app.db.models.user import User

pytestmark = pytest.mark.asyncio

PREFIX = "test-ob-"


@pytest_asyncio.fixture
async def client():
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    async with AsyncSessionLocal() as db:
        run_ids = (
            await db.execute(select(OffsiteBackupRun.id).where(OffsiteBackupRun.target_name.like(f"{PREFIX}%")))
        ).scalars().all()
        for run_id in run_ids:
            await db.execute(delete(Notification).where(Notification.event_key == f"offsite-backup:{run_id}"))
        await db.execute(delete(OffsiteBackupRun).where(OffsiteBackupRun.target_name.like(f"{PREFIX}%")))
        await db.execute(delete(OffsiteBackupTarget).where(OffsiteBackupTarget.name.like(f"{PREFIX}%")))
        await db.commit()


@pytest.fixture
def bridge(monkeypatch):
    """Records host commands; `missing` paths and `exit_code` steer the answers."""
    state = {"commands": [], "missing": [], "exit_code": 0, "jobs": "[]"}

    async def fake_exec(command, *, timeout_seconds=60):
        state["commands"].append(command)
        if command.startswith("for p in"):
            return {"exit_code": 0, "stdout": "".join(f"{p}\n" for p in state["missing"]), "stderr": ""}
        if command.startswith("python3 - <<'PYEOF'"):
            return {"exit_code": 0, "stdout": state["jobs"], "stderr": ""}
        if command.startswith("docker ps"):
            return {"exit_code": 0, "stdout": "forgehub_postgres\tpgvector/pgvector:pg16\nforgehub-backend\tforgehub-backend\n", "stderr": ""}
        return {"exit_code": state["exit_code"], "stdout": "", "stderr": ""}

    monkeypatch.setattr(route, "_bridge_exec", fake_exec)
    return state


@pytest_asyncio.fixture
async def non_admin_headers():
    # Not the shared `auth_headers`: its "test-suite" user may be an admin.
    username = f"test-ob-user-{uuid.uuid4().hex[:12]}"
    async with AsyncSessionLocal() as db:
        db.add(User(username=username, hashed_password=hash_password(uuid.uuid4().hex), is_admin=False))
        await db.commit()
    yield {"Authorization": f"Bearer {create_access_token(username)}"}
    async with AsyncSessionLocal() as db:
        await db.execute(delete(User).where(User.username == username))
        await db.commit()


@pytest.fixture
def bridge_headers():
    return {"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN}


def _name() -> str:
    return f"{PREFIX}{uuid.uuid4().hex[:8]}"


async def _create(client, admin_headers, **overrides):
    body = {"name": _name(), "label": "Projeto de teste", "paths": ["/root/project/x", "/root/project/x/"]}
    body.update(overrides)
    return await client.post("/api/v1/offsite-backup/targets", json=body, headers=admin_headers)


async def test_target_crud_normalizes_paths_and_checks_they_exist(client, admin_headers, bridge):
    resp = await _create(client, admin_headers, excludes=["*.log", " ", "*.log"], postgres_container="forgehub_postgres")
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["paths"] == ["/root/project/x"]
    assert created["excludes"] == ["*.log"]
    assert created["last_run"] is None

    bridge["missing"] = ["/root/nope"]
    resp = await client.put(
        f"/api/v1/offsite-backup/targets/{created['id']}",
        json={"label": "Renomeado", "paths": ["/root/nope"]},
        headers=admin_headers,
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["missing"] == ["/root/nope"]

    bridge["missing"] = []
    resp = await client.put(
        f"/api/v1/offsite-backup/targets/{created['id']}",
        json={"label": "Renomeado", "paths": ["/root/project/y"], "enabled": False},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["label"] == "Renomeado" and resp.json()["enabled"] is False
    # The identifier is the snapshots' restic tag: not editable.
    assert resp.json()["name"] == created["name"]

    resp = await client.delete(f"/api/v1/offsite-backup/targets/{created['id']}", headers=admin_headers)
    assert resp.status_code == 204


@pytest.mark.parametrize("paths", [["relative/path"], ["/"], ["/.."], []])
async def test_invalid_paths_are_refused(client, admin_headers, bridge, paths):
    resp = await _create(client, admin_headers, paths=paths)
    assert resp.status_code == 422
    assert bridge["commands"] == []


async def test_identifier_must_be_a_slug_and_unique(client, admin_headers, bridge):
    assert (await _create(client, admin_headers, name="Com Espaço")).status_code == 422
    name = _name()
    assert (await _create(client, admin_headers, name=name)).status_code == 201
    assert (await _create(client, admin_headers, name=name)).status_code == 409


async def test_targets_require_an_admin(client, non_admin_headers, bridge):
    resp = await client.get("/api/v1/offsite-backup/overview", headers=non_admin_headers)
    assert resp.status_code == 403


async def _claim(client, bridge_headers) -> dict:
    resp = await client.post("/api/v1/offsite-backup/internal/runs:claim", headers=bridge_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_queue_cycle_reports_status_and_notifies_failures(client, admin_headers, bridge, bridge_headers):
    first = (await _create(client, admin_headers, label="Primeiro")).json()["name"]
    second = (await _create(client, admin_headers, label="Segundo")).json()["name"]

    assert (await client.post("/api/v1/offsite-backup/internal/runs:claim")).status_code == 401

    # Queued in the order asked, and the worker is woken.
    resp = await client.post("/api/v1/offsite-backup/run", json={"targets": [second, first]}, headers=admin_headers)
    assert resp.status_code == 202, resp.text
    assert resp.json()["queued"] == [second, first]
    assert bridge["commands"][-1] == "/root/.hermes/profiles/athos/scripts/backup_offsite_projects.sh --trigger manual"

    overview = (await client.get("/api/v1/offsite-backup/overview", headers=admin_headers)).json()
    assert overview["queued"] == 2
    assert next(t for t in overview["targets"] if t["name"] == first)["last_run"]["status"] == "queued"

    claim = await _claim(client, bridge_headers)
    assert claim["target"]["name"] == second and claim["target"]["paths"] == ["/root/project/x"]
    assert claim["run"]["trigger"] == "manual"
    await client.post(
        "/api/v1/offsite-backup/internal/runs:finish",
        json={"run_id": claim["run"]["run_id"], "status": "ok", "snapshot_id": "abcd1234", "data_added": 1024},
        headers=bridge_headers,
    )

    # Asking again for a target still waiting doesn't queue it twice.
    resp = await client.post("/api/v1/offsite-backup/run", json={"targets": [first, second]}, headers=admin_headers)
    assert resp.json() == {"queued": [second], "skipped": [first], "worker_already_running": False}

    claim = await _claim(client, bridge_headers)
    assert claim["target"]["name"] == first
    await client.post(
        "/api/v1/offsite-backup/internal/runs:finish",
        json={"run_id": claim["run"]["run_id"], "status": "failed", "error": "rateLimitExceeded"},
        headers=bridge_headers,
    )
    async with AsyncSessionLocal() as db:
        note = (
            await db.execute(select(Notification).where(Notification.event_key == f"offsite-backup:{claim['run']['run_id']}"))
        ).scalar_one()
        assert note.severity == "error" and "Primeiro" in note.title

    claim = await _claim(client, bridge_headers)
    assert claim["target"]["name"] == second
    assert (await _claim(client, bridge_headers))["run"] is None

    overview = (await client.get("/api/v1/offsite-backup/overview", headers=admin_headers)).json()
    row = next(t for t in overview["targets"] if t["name"] == first)
    assert row["last_run"]["status"] == "failed" and row["last_success"] is None
    assert next(t for t in overview["targets"] if t["name"] == second)["last_success"]["snapshot_id"] == "abcd1234"
    assert overview["running"] is True and overview["queued"] == 0
    assert overview["schedule"] is None and overview["schedule_error"] == "not_scheduled"


async def test_cancel_only_a_queued_run(client, admin_headers, bridge, bridge_headers):
    name = (await _create(client, admin_headers)).json()["name"]
    await client.post("/api/v1/offsite-backup/run", json={"targets": [name]}, headers=admin_headers)
    runs = (await client.get(f"/api/v1/offsite-backup/runs?target={name}", headers=admin_headers)).json()
    assert [r["status"] for r in runs] == ["queued"] and runs[0]["started_at"] is None

    resp = await client.delete(f"/api/v1/offsite-backup/runs/{runs[0]['id']}", headers=admin_headers)
    assert resp.status_code == 204
    assert (await client.get(f"/api/v1/offsite-backup/runs?target={name}", headers=admin_headers)).json() == []

    await client.post("/api/v1/offsite-backup/run", json={"targets": [name]}, headers=admin_headers)
    claim = await _claim(client, bridge_headers)
    resp = await client.delete(f"/api/v1/offsite-backup/runs/{claim['run']['run_id']}", headers=admin_headers)
    assert resp.status_code == 409


async def test_target_disabled_while_queued_is_skipped(client, admin_headers, bridge, bridge_headers):
    target = (await _create(client, admin_headers)).json()
    await client.post("/api/v1/offsite-backup/run", json={"targets": [target["name"]]}, headers=admin_headers)
    await client.put(
        f"/api/v1/offsite-backup/targets/{target['id']}",
        json={"label": target["label"], "paths": target["paths"], "enabled": False},
        headers=admin_headers,
    )
    assert (await _claim(client, bridge_headers))["run"] is None
    runs = (await client.get(f"/api/v1/offsite-backup/runs?target={target['name']}", headers=admin_headers)).json()
    assert runs[0]["status"] == "interrupted" and "disabled" in runs[0]["error"]


async def test_schedule_queues_every_enabled_target(client, admin_headers, bridge, bridge_headers):
    on = (await _create(client, admin_headers)).json()["name"]
    off = (await _create(client, admin_headers, enabled=False)).json()["name"]
    resp = await client.post("/api/v1/offsite-backup/internal/enqueue", json={"trigger": "schedule"}, headers=bridge_headers)
    assert on in resp.json()["queued"] and off not in resp.json()["queued"]
    async with AsyncSessionLocal() as db:
        # Other enabled targets in this database were queued too; only ours are checked.
        run = (await db.execute(select(OffsiteBackupRun).where(OffsiteBackupRun.target_name == on))).scalar_one()
        assert run.trigger == "schedule"
        await db.execute(
            delete(OffsiteBackupRun).where(
                OffsiteBackupRun.status == "queued", OffsiteBackupRun.target_name.not_like(f"{PREFIX}%")
            )
        )
        await db.commit()


async def test_a_dead_worker_run_is_closed_when_the_target_runs_again(client, admin_headers, bridge, bridge_headers):
    target = (await _create(client, admin_headers)).json()
    async with AsyncSessionLocal() as db:
        db.add(OffsiteBackupRun(
            target_id=uuid.UUID(target["id"]), target_name=target["name"], trigger="schedule", status="running",
            started_at=datetime.now(timezone.utc) - timedelta(days=2),
        ))
        await db.commit()
    overview = (await client.get("/api/v1/offsite-backup/overview", headers=admin_headers)).json()
    assert next(t for t in overview["targets"] if t["name"] == target["name"])["last_run"]["status"] == "interrupted"

    await client.post("/api/v1/offsite-backup/run", json={"targets": [target["name"]]}, headers=admin_headers)
    await _claim(client, bridge_headers)
    runs = (await client.get(f"/api/v1/offsite-backup/runs?target={target['name']}", headers=admin_headers)).json()
    assert [r["status"] for r in runs] == ["running", "interrupted"]


async def test_targets_run_only_through_the_queue(client, bridge_headers):
    resp = await client.post(
        "/api/v1/offsite-backup/internal/runs", json={"target_name": f"{PREFIX}x"}, headers=bridge_headers
    )
    assert resp.status_code == 400


async def test_run_now_validates_targets_and_tolerates_a_busy_worker(client, admin_headers, bridge):
    name = (await _create(client, admin_headers)).json()["name"]
    bridge["exit_code"] = 75
    resp = await client.post("/api/v1/offsite-backup/run", json={"targets": [name]}, headers=admin_headers)
    assert resp.status_code == 202
    assert resp.json()["worker_already_running"] is True

    resp = await client.post("/api/v1/offsite-backup/run", json={"targets": [f"{PREFIX}nope"]}, headers=admin_headers)
    assert resp.status_code == 400

    bridge["exit_code"] = 1
    other = (await _create(client, admin_headers)).json()["name"]
    resp = await client.post("/api/v1/offsite-backup/run", json={"targets": [other]}, headers=admin_headers)
    assert resp.status_code == 500


async def test_schedule_is_read_from_the_athos_cron_job(client, admin_headers, bridge):
    bridge["jobs"] = (
        '[{"id": "abc", "schedule_display": "0 2 * * *", "enabled": true, '
        '"next_run_at": "2026-10-21T02:00:00-03:00", "last_run_at": null, "last_status": null}]'
    )
    overview = (await client.get("/api/v1/offsite-backup/overview", headers=admin_headers)).json()
    assert overview["schedule"]["expression"] == "0 2 * * *"
    assert overview["schedule_error"] is None


async def test_postgres_container_picker(client, admin_headers, bridge):
    resp = await client.get("/api/v1/offsite-backup/postgres-containers", headers=admin_headers)
    assert resp.json() == {"containers": ["forgehub_postgres"]}

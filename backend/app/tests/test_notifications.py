"""Tests for the notifications record (persistent cron-run notifications).

Covers: list shape (notifications/total/unread_count), server-side read
tracking (mark-read by id and via all=True semantics), and retention
cleanup (keep_days deletes only rows older than the cutoff).

DB strategy: tables come from the Alembic migration; each test creates its
own rows (UUID-suffixed event_key) directly via the session and removes
them in a finally block. The cleanup test only ever asserts on its own old
row — `mode: "all"` is deliberately not exercised against the shared DB.

Auth: main.py's RequireAuthMiddleware guards every /api/v1/* route, so
requests here carry a real signed bearer token (the middleware validates
the JWT itself, not a user row).
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.notification import Notification

_notifications_router_mounted = False


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('test-notifications')}"}


@pytest_asyncio.fixture
async def client():
    global _notifications_router_mounted

    from app.main import app

    from app.api.routes import notifications

    if not _notifications_router_mounted:
        app.include_router(notifications.router)
        _notifications_router_mounted = True

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=_auth_headers()) as ac:
        yield ac


async def _insert_notification(**overrides) -> Notification:
    fields = {
        "id": uuid.uuid4(),
        "source": "cron",
        "severity": "error",
        "title": f"test-job-{uuid.uuid4().hex[:8]}",
        "message": "boom",
        "summary": "did nothing, then failed",
        "job_id": "test-job-id",
        "job_name": "test-job",
        "profile": "test-profile",
        "script_name": "test.sh",
        "event_key": f"test:{uuid.uuid4().hex}",
        "occurred_at": datetime.now(timezone.utc),
        **overrides,
    }
    row = Notification(**fields)
    async with AsyncSessionLocal() as session:
        session.add(row)
        await session.commit()
    return row


async def _delete_notifications(ids: list[uuid.UUID]) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(delete(Notification).where(Notification.id.in_(ids)))
        await session.commit()


async def test_list_and_mark_read(client: AsyncClient):
    row = await _insert_notification()
    try:
        resp = await client.get("/api/v1/notifications")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert {"notifications", "total", "unread_count"} <= body.keys()
        mine = next(n for n in body["notifications"] if n["id"] == str(row.id))
        assert mine["read_at"] is None
        assert mine["summary"] == "did nothing, then failed"
        assert mine["job_name"] == "test-job"

        resp = await client.post("/api/v1/notifications/mark-read", json={"ids": [str(row.id)]})
        assert resp.status_code == 200, resp.text
        assert resp.json()["marked"] == 1

        resp = await client.get("/api/v1/notifications", params={"unread_only": "true"})
        assert resp.status_code == 200
        assert all(n["id"] != str(row.id) for n in resp.json()["notifications"])
    finally:
        await _delete_notifications([row.id])


async def test_mark_read_requires_target(client: AsyncClient):
    resp = await client.post("/api/v1/notifications/mark-read", json={})
    assert resp.status_code == 400


async def test_cleanup_keep_days(client: AsyncClient):
    old = await _insert_notification(occurred_at=datetime.now(timezone.utc) - timedelta(days=90))
    fresh = await _insert_notification()
    try:
        resp = await client.post(
            "/api/v1/notifications/cleanup", json={"mode": "keep_days", "keep_days": 30}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["deleted"] >= 1

        resp = await client.get("/api/v1/notifications")
        ids = {n["id"] for n in resp.json()["notifications"]}
        assert str(old.id) not in ids
        assert str(fresh.id) in ids
    finally:
        await _delete_notifications([old.id, fresh.id])


async def test_cleanup_keep_days_requires_days(client: AsyncClient):
    resp = await client.post("/api/v1/notifications/cleanup", json={"mode": "keep_days"})
    assert resp.status_code == 400


async def test_cleanup_suppresses_reingestion(client: AsyncClient, monkeypatch):
    """Runs purged by cleanup must not be re-ingested from jobs.json as new
    unread notifications: cleanup advances the NotificationIngestState
    watermark, and ingestion skips runs at or before it. Fresh runs (after
    the watermark) must still ingest normally.

    Shared-DB note: the watermark is global and monotonic, so this test
    doesn't assume a clean slate — it runs a keep_days=30 cleanup itself
    (same operation test_cleanup_keep_days already performs) and then checks
    ingestion behavior on both sides of the resulting cutoff.
    """
    from app.api.routes import notifications as notifications_routes

    job_id = f"test-suppress-{uuid.uuid4().hex[:8]}"
    old_run_at = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    fresh_run_at = datetime.now(timezone.utc).isoformat()

    def _fake_job(run_at: str) -> dict:
        return {
            "id": job_id,
            "name": job_id,
            "last_run_at": run_at,
            "last_status": "ok",
            "script": "test.sh",
        }

    async def _my_row_ids() -> list[uuid.UUID]:
        async with AsyncSessionLocal() as session:
            rows = await session.execute(
                select(Notification.id).where(Notification.job_id == job_id)
            )
            return list(rows.scalars())

    try:
        # Cleanup advances the watermark to now-30d (creating it if needed).
        resp = await client.post(
            "/api/v1/notifications/cleanup", json={"mode": "keep_days", "keep_days": 30}
        )
        assert resp.status_code == 200, resp.text

        # A 90-day-old run still sitting in jobs.json must NOT be ingested —
        # this is the "purged notifications reappear as unread" regression.
        monkeypatch.setattr(
            notifications_routes, "_load_all_cron_jobs", lambda: [_fake_job(old_run_at)]
        )
        resp = await client.get("/api/v1/notifications")
        assert resp.status_code == 200, resp.text
        assert await _my_row_ids() == []

        # A fresh run (after the watermark) must still ingest normally.
        monkeypatch.setattr(
            notifications_routes, "_load_all_cron_jobs", lambda: [_fake_job(fresh_run_at)]
        )
        resp = await client.get("/api/v1/notifications")
        assert resp.status_code == 200, resp.text
        assert any(n["job_id"] == job_id for n in resp.json()["notifications"])
    finally:
        await _delete_notifications(await _my_row_ids())

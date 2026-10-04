"""Athos weekly audit scheduler monitoring."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.api.routes import audit as audit_routes
from app.api.routes.foundation import CronJobOut, CronStoreErrorOut
from app.core.athos_audit_monitor import inspect_athos_audit_job
from app.db.base import AsyncSessionLocal
from app.db.models.audit import AuditCheck, AuditCheckRun

NOW = datetime(2026, 10, 4, 20, tzinfo=timezone.utc)


def job(**changes: object) -> CronJobOut:
    values = dict(
        profile="athos", id="weekly", name="ecosystem-weekly-audit",
        script="ecosystem_weekly_audit.sh", script_state="ok", is_audit_job=True, schedule_display="0 19 * * 0",
        enabled=True, state="scheduled", status="active", health="ok",
        last_run_at=(NOW - timedelta(days=7)).isoformat(), last_status="ok",
        next_run_at=(NOW + timedelta(days=7)).isoformat(),
    )
    values.update(changes)
    return CronJobOut(**values)


def inspect(jobs: list[CronJobOut], errors: list[CronStoreErrorOut] | None = None,
            last_cron_run_at: datetime | None = None):
    return inspect_athos_audit_job(jobs, errors or [], last_cron_run_at, NOW)


def test_athos_monitor_healthy_for_canonical_job():
    result = inspect([job()], last_cron_run_at=NOW - timedelta(days=7))
    assert result.state == "healthy"
    assert result.job_id == "weekly"
    assert result.schedule == "0 19 * * 0"
    assert result.issues == []


def test_athos_monitor_missing_or_duplicate_job():
    assert inspect([]).state == "not_configured"
    duplicate = inspect([job(), job(id="second")])
    assert duplicate.state == "degraded"
    assert any("duplic" in issue.lower() for issue in duplicate.issues)


@pytest.mark.parametrize("change", [
    {"schedule_display": "0 20 * * 0"},
    {"script": "other.sh"},
    {"enabled": False, "health": "off"},
    {"health": "overdue"},
    {"name": "renamed-weekly-audit"},
])
def test_athos_monitor_schedule_script_and_disabled_drift(change):
    result = inspect([job(**change)], last_cron_run_at=NOW - timedelta(days=7))
    assert result.state == "degraded"
    assert result.issues


def test_athos_monitor_failed_on_error_status_or_store_error():
    failed = inspect([job(last_status="error", health="error")])
    assert failed.state == "failed"
    corrupted = inspect([], [CronStoreErrorOut(profile="athos", store="jobs.json", error="invalid JSON")])
    assert corrupted.state == "failed"
    assert any("invalid JSON" in issue for issue in corrupted.issues)


def test_athos_monitor_marks_stale_audit():
    result = inspect([job()], last_cron_run_at=NOW - timedelta(days=8, seconds=1))
    assert result.state == "degraded"
    assert any("8" in issue for issue in result.issues)


@pytest_asyncio.fixture
async def client():
    app = FastAPI()
    app.include_router(audit_routes.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def test_status_separates_scheduler_from_check_result(client, monkeypatch):
    check = AuditCheck(name=f"test-athos-monitor-{uuid.uuid4().hex}", command="false",
                       agent_profile="athos", enabled=True, timeout_seconds=5)
    async with AsyncSessionLocal() as db:
        db.add(check)
        await db.flush()
        db.add(AuditCheckRun(check_id=check.id, status="fail", requested_by="cron"))
        await db.commit()
    monkeypatch.setattr(audit_routes.foundation, "_list_cron_jobs", lambda: [job()])
    monkeypatch.setattr(audit_routes.foundation, "_cron_store_errors", lambda: [])
    try:
        response = await client.get("/api/v1/audit/status")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["fail"] >= 1
        assert body["athos_monitor"]["state"] == "healthy"
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AuditCheck).where(AuditCheck.id == check.id))
            await db.commit()

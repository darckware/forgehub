"""Evidence expires independently of the immutable recorded verdict."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.api.routes import audit as routes
from app.db.base import AsyncSessionLocal
from app.db.models.audit import AuditCheck, AuditCheckRun


@pytest_asyncio.fixture
async def client(monkeypatch):
    app = FastAPI()
    app.include_router(routes.router)
    monkeypatch.setattr(routes.foundation, "_list_cron_jobs", lambda: [])
    monkeypatch.setattr(routes.foundation, "_cron_store_errors", lambda: [])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.parametrize("age,state", [(None, "never"), (timedelta(days=7), "fresh"),
    (timedelta(days=8, seconds=1), "stale"), (timedelta(seconds=-60), "stale")])
async def test_check_exposes_freshness_without_rewriting_history(client, age, state):
    now = datetime.now(timezone.utc)
    check = AuditCheck(name=f"test-freshness-{uuid.uuid4().hex}", command="true", enabled=True)
    async with AsyncSessionLocal() as db:
        db.add(check)
        await db.flush()
        if age is not None:
            db.add(AuditCheckRun(check_id=check.id, status="ok", requested_by="manual", created_at=now-age))
        await db.commit()
    try:
        checks = (await client.get("/api/v1/audit/checks")).json()
        actual = next(c for c in checks if c["id"] == str(check.id))
        assert actual["evidence_state"] == state
        assert (datetime.fromisoformat(actual["expires_at"]) if actual["expires_at"] else None) == (now-age+timedelta(days=8) if age is not None else None)
        if age is not None:
            assert actual["last_run"]["status"] == "ok"
            history = (await client.get(f"/api/v1/audit/runs?check_id={check.id}")).json()
            assert history[0]["status"] == "ok"
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AuditCheck).where(AuditCheck.id == check.id))
            await db.commit()


async def test_stale_ok_is_not_counted_green_and_repair_reply_is_not_evidence(client):
    before = (await client.get("/api/v1/audit/status")).json()
    check = AuditCheck(name=f"test-stale-{uuid.uuid4().hex}", command="true", enabled=True)
    async with AsyncSessionLocal() as db:
        db.add(check)
        await db.flush()
        db.add(AuditCheckRun(check_id=check.id, status="ok", requested_by="cron", created_at=datetime.now(timezone.utc)-timedelta(days=9)))
        db.add(AuditCheckRun(check_id=check.id, status="ok", requested_by="athos-remediation"))
        await db.commit()
    try:
        after = (await client.get("/api/v1/audit/status")).json()
        assert after["ok"] == before["ok"]
        assert after["stale"] == before["stale"] + 1
        check_out = next(c for c in (await client.get("/api/v1/audit/checks")).json() if c["id"] == str(check.id))
        assert check_out["last_run"]["requested_by"] == "cron"
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AuditCheck).where(AuditCheck.id == check.id))
            await db.commit()


async def test_unrelated_recent_run_cannot_mask_incomplete_cron_batch(client):
    now = datetime.now(timezone.utc)
    complete_at = now - timedelta(days=9)
    owned_runs = []
    check = AuditCheck(name=f"test-batch-{uuid.uuid4().hex}", command="true", enabled=True)
    async with AsyncSessionLocal() as db:
        db.add(check)
        await db.flush()
        ids = list((await db.scalars(select(AuditCheck.id).where(AuditCheck.enabled.is_(True)))).all())
        # Ensure a partial batch is incomplete even in a minimal database.
        other = AuditCheck(name=f"test-batch-other-{uuid.uuid4().hex}", command="true", enabled=True)
        db.add(other)
        await db.flush()
        ids.append(other.id)
        for check_id in ids:
            run = AuditCheckRun(id=uuid.uuid4(), check_id=check_id, status="ok", requested_by="cron", created_at=complete_at)
            db.add(run)
            owned_runs.append(run.id)
        for source, when in [("cron", now-timedelta(hours=1)), ("cron", now+timedelta(hours=1)), ("manual", now)]:
            run = AuditCheckRun(id=uuid.uuid4(), check_id=check.id, status="ok", requested_by=source, created_at=when)
            db.add(run)
            owned_runs.append(run.id)
        await db.commit()
    try:
        body = (await client.get("/api/v1/audit/status")).json()
        assert datetime.fromisoformat(body["last_complete_cron_run_at"]) == complete_at
        assert body["athos_monitor"]["state"] != "healthy"
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AuditCheckRun).where(AuditCheckRun.id.in_(owned_runs)))
            await db.execute(delete(AuditCheck).where(AuditCheck.id.in_([check.id, other.id])))
            await db.commit()


@pytest.mark.parametrize("offset,state", [(timedelta(days=8), "stale"), (timedelta(days=8, microseconds=-1), "fresh"), (timedelta(microseconds=-1), "stale"), (timedelta(0), "fresh")])
def test_exact_evidence_window(offset, state):
    from app.core.audit_freshness import evidence_freshness

    now = datetime(2026, 11, 12, tzinfo=timezone.utc)
    assert evidence_freshness(now-offset, now)[0] == state


async def test_identified_cron_batches_keep_distinct_observation_times_and_never_mix_ids(client):
    now = datetime.now(timezone.utc)
    check = AuditCheck(name=f"test-batch-identity-{uuid.uuid4().hex}", command="true", enabled=True)
    other = AuditCheck(name=f"test-batch-identity-other-{uuid.uuid4().hex}", command="true", enabled=True)
    run_ids = []
    async with AsyncSessionLocal() as db:
        db.add_all([check, other])
        await db.flush()
        ids = list((await db.scalars(select(AuditCheck.id).where(AuditCheck.enabled.is_(True)))).all())
        valid_batch, invalid_future_batch = uuid.uuid4(), uuid.uuid4()
        for index, check_id in enumerate(ids):
            # A complete batch has distinct command completion times.
            observed_at = now-timedelta(days=2)+timedelta(seconds=index)
            for batch_id, instant in [(valid_batch, observed_at),
                    # Unrelated one-check batches must not combine even at one timestamp.
                    (uuid.uuid4(), now-timedelta(hours=1)),
                    # One future observation invalidates the whole identified batch.
                    (invalid_future_batch, now+timedelta(hours=1) if index == len(ids)-1 else now)]:
                run = AuditCheckRun(id=uuid.uuid4(), check_id=check_id, batch_id=batch_id, status="ok", requested_by="cron", created_at=instant)
                db.add(run)
                run_ids.append(run.id)
        await db.commit()
    try:
        body = (await client.get("/api/v1/audit/status")).json()
        assert datetime.fromisoformat(body["last_complete_cron_run_at"]) == now-timedelta(days=2)+timedelta(seconds=len(ids)-1)
        history = (await client.get(f"/api/v1/audit/runs?check_id={check.id}")).json()
        assert {run["batch_id"] for run in history} >= {str(valid_batch), str(invalid_future_batch)}
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AuditCheckRun).where(AuditCheckRun.id.in_(run_ids)))
            await db.execute(delete(AuditCheck).where(AuditCheck.id.in_([check.id, other.id])))
            await db.commit()

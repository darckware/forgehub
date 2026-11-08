"""Retention integration checks; run only against the isolated test database."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select

from app.core.host_output_retention import run_host_output_retention
from app.db.base import AsyncSessionLocal
from app.db.models.host_execution import HostExecution, HostExecutionResult


@pytest.mark.asyncio
async def test_retention_boundary_active_preservation_batches_and_idempotency():
    now = datetime(2026, 11, 7, tzinfo=timezone.utc)
    cutoff = now - timedelta(days=90)
    ids = []
    async with AsyncSessionLocal() as db:
        try:
            for label, parent_status, result_status, finished in [
                ("old", "completed", "succeeded", cutoff - timedelta(microseconds=1)),
                ("cancelled", "cancelled", "failed", cutoff - timedelta(days=1)),
                ("boundary", "completed", "succeeded", cutoff),
                ("recent", "completed", "succeeded", cutoff + timedelta(days=1)),
                ("active-parent", "running", "succeeded", cutoff - timedelta(days=2)),
                ("active-result", "completed", "running", cutoff - timedelta(days=2)),
                ("pending-result", "cancelled", "pending", cutoff - timedelta(days=2)),
                ("unfinished", "completed", "succeeded", None),
            ]:
                execution = HostExecution(id=uuid.uuid4(), shell="sh", command="whoami", timeout_seconds=30,
                    requested_by="retention-test", reason="audit must remain", status=parent_status,
                    started_at=cutoff - timedelta(days=3), finished_at=finished)
                ids.append(execution.id)
                db.add(execution)
                await db.flush()
                db.add(HostExecutionResult(execution_id=execution.id, server_name=label,
                    status=result_status, stdout="sensitive stdout", stderr="sensitive stderr",
                    exit_code=0, duration_ms=5, started_at=cutoff - timedelta(days=3), finished_at=finished))
            await db.commit()
            before = {r.server_name: {c.name: getattr(r, c.name) for c in r.__table__.columns}
                for r in (await db.scalars(select(HostExecutionResult).where(HostExecutionResult.execution_id.in_(ids)))).all()}
            assert await run_host_output_retention(db, now=now, retention_days=90, batch_size=1) == 1
            assert await run_host_output_retention(db, now=now, retention_days=90, batch_size=1) == 1
            assert await run_host_output_retention(db, now=now, retention_days=90, batch_size=1) == 0
            db.expire_all()
            results = (await db.scalars(select(HostExecutionResult).where(HostExecutionResult.execution_id.in_(ids)))).all()
            assert len(results) == len(ids)
            for row in results:
                old = row.server_name in ("old", "cancelled")
                assert row.output_expired is old
                assert row.stdout == (None if old else "sensitive stdout")
                assert row.stderr == (None if old else "sensitive stderr")
                for key, value in before[row.server_name].items():
                    if key not in ("stdout", "stderr", "output_expired"):
                        assert getattr(row, key) == value, key
            from app.api.routes.host_execution import _detail
            old_execution = await db.get(HostExecution, next(r.execution_id for r in results if r.server_name == 'old'))
            detail = await _detail(db, old_execution)
            assert detail.output_expired_count == 1 and detail.results[0].output_expired is True
            assert detail.results[0].stdout is None
            for execution in (await db.scalars(select(HostExecution).where(HostExecution.id.in_(ids)))).all():
                assert execution.command == "whoami"
                assert execution.requested_by == "retention-test"
                assert execution.reason == "audit must remain"
        finally:
            await db.rollback()
            await db.execute(delete(HostExecution).where(HostExecution.id.in_(ids)))
            await db.commit()


@pytest.mark.asyncio
async def test_retention_worker_does_not_connect_when_background_workers_disabled(monkeypatch):
    from app.core import host_output_retention as worker
    from app.core.config import settings
    assert settings.background_workers_enabled is False
    def forbidden_connection():
        raise AssertionError('disabled worker attempted database access')
    monkeypatch.setattr(worker, 'AsyncSessionLocal', forbidden_connection)
    await worker.host_output_retention_loop()

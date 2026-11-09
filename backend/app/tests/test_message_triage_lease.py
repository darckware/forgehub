"""Durable lease heartbeats and advisory task cleanup without wall-clock waits."""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete

from app.core import message_triage
from app.db.base import AsyncSessionLocal
from app.db.models.message_triage import MessageAnalysisRun


@pytest.fixture
async def leased_analysis(monkeypatch):
    clock = {"now": datetime.now(timezone.utc)}
    monkeypatch.setattr(message_triage, "now", lambda: clock["now"])
    token = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        run = MessageAnalysisRun(
            scope_key=uuid.uuid4().hex, scope={}, requested_by="test:triage-lease",
            status="running", lease_token=token,
            lease_until=clock["now"] + timedelta(seconds=message_triage.LEASE_SECONDS),
        )
        db.add(run)
        await db.commit()
        run_id = run.id
    try:
        yield run_id, token, clock
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(MessageAnalysisRun).where(MessageAnalysisRun.id == run_id))
            await db.commit()


async def test_heartbeat_keeps_healthy_advisory_alive_beyond_original_lease(leased_analysis, monkeypatch):
    run_id, token, clock = leased_analysis
    initial = clock["now"]
    release = asyncio.Event()
    real_wait = asyncio.wait
    ticks = 0

    async def advisory():
        await release.wait()
        return ["advisory result"]

    async def advance(tasks, *, timeout):
        nonlocal ticks
        assert timeout == 30
        # Check the previously persisted heartbeat from another transaction.
        async with AsyncSessionLocal() as db:
            run = await db.get(MessageAnalysisRun, run_id)
            assert run.lease_until == clock["now"] + timedelta(seconds=message_triage.LEASE_SECONDS)
        ticks += 1
        if ticks == 8:
            release.set()
            return await real_wait(tasks)
        clock["now"] += timedelta(seconds=30)
        return await real_wait(tasks, timeout=0)

    monkeypatch.setattr(message_triage.asyncio, "wait", advance)
    assert await message_triage._analyze_with_lease(run_id, token, advisory()) == ["advisory result"]
    assert (clock["now"] - initial).total_seconds() == 210
    async with AsyncSessionLocal() as db:
        run = await db.get(MessageAnalysisRun, run_id)
        assert run.status == "running" and run.lease_token == token
        assert run.lease_until > clock["now"]


async def test_lost_lease_token_cancels_and_awaits_advisory(leased_analysis, monkeypatch):
    run_id, token, clock = leased_analysis
    cancelled = asyncio.Event()
    blocked = asyncio.Event()
    real_wait = asyncio.wait
    replacement = uuid.uuid4()

    async def advisory():
        try:
            await blocked.wait()
        finally:
            cancelled.set()

    async def replace_token(tasks, *, timeout):
        await real_wait(tasks, timeout=0)
        async with AsyncSessionLocal() as db:
            run = await db.get(MessageAnalysisRun, run_id)
            run.lease_token = replacement
            await db.commit()
        clock["now"] += timedelta(seconds=30)
        return set(), tasks

    monkeypatch.setattr(message_triage.asyncio, "wait", replace_token)
    with pytest.raises(RuntimeError, match="lease lost"):
        await message_triage._analyze_with_lease(run_id, token, advisory())
    assert cancelled.is_set()
    async with AsyncSessionLocal() as db:
        run = await db.get(MessageAnalysisRun, run_id)
        assert run.lease_token == replacement


async def test_cancelled_worker_does_not_leave_advisory_task_running(leased_analysis, monkeypatch):
    run_id, token, _ = leased_analysis
    started = asyncio.Event()
    cancelled = asyncio.Event()
    blocked = asyncio.Event()
    advisory_tasks = []

    async def advisory():
        advisory_tasks.append(asyncio.current_task())
        started.set()
        try:
            await blocked.wait()
        finally:
            cancelled.set()

    async def wait_until_cancelled(tasks, *, timeout):
        await blocked.wait()
        raise AssertionError("The test should cancel the worker before releasing the advisory")

    monkeypatch.setattr(message_triage.asyncio, "wait", wait_until_cancelled)
    worker = asyncio.create_task(message_triage._analyze_with_lease(run_id, token, advisory()))
    try:
        await started.wait()
        worker.cancel()
        with pytest.raises(asyncio.CancelledError):
            await worker
        assert cancelled.is_set()
        assert len(advisory_tasks) == 1
        assert advisory_tasks[0].done() and advisory_tasks[0].cancelled()
    finally:
        if not worker.done():
            worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)

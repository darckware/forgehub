"""Auditor frequencies (2026-11-13): checks classified by tier, each tier run
as one Auditor batch by its Operação 24x7 audit routine -- no Messages task,
no LLM -- with the batch recorded as the occurrence's evidence."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from app.api.routes import audit as audit_routes
from app.api.routes import operations as ops
from app.core import audit_routines
from app.core.athos_audit_monitor import inspect_athos_audit_job
from app.core.audit_catalog import CANONICAL_AUDIT_CHECKS, audit_check_frequency
from app.core.audit_freshness import evidence_freshness
from app.core.deps import get_current_admin
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.audit import AuditCheck, AuditCheckRun
from app.db.models.demand import AgentDemand
from app.db.models.operations import AgentCharter, AgentRoutine, AgentRoutineRun

UTC = timezone.utc


@pytest.fixture
def fake_checks(monkeypatch):
    """Every check passes instantly, without the host bridge."""
    executed: list[str] = []

    async def fake(check: AuditCheck, requested_by: str) -> AuditCheckRun:
        executed.append(check.name)
        return AuditCheckRun(check_id=check.id, status="ok", exit_code=0, output="ok", duration_ms=1,
                             requested_by=requested_by, created_at=datetime.now(UTC))

    monkeypatch.setattr(audit_routes, "_execute_check", fake)
    return executed


@pytest_asyncio.fixture
async def owner():
    row = Agent(name=f"test-audit-owner-{uuid.uuid4().hex[:8]}", profile_slug=f"taud{uuid.uuid4().hex[:6]}")
    async with AsyncSessionLocal() as db:
        db.add(row)
        await db.commit()
        await db.refresh(row)
    yield row
    async with AsyncSessionLocal() as db:
        batches = select(AgentRoutineRun.audit_batch_id).join(
            AgentRoutine, AgentRoutine.id == AgentRoutineRun.routine_id).where(AgentRoutine.agent_id == row.id)
        await db.execute(delete(AuditCheckRun).where(AuditCheckRun.batch_id.in_(batches)))
        await db.execute(delete(AgentRoutine).where(AgentRoutine.agent_id == row.id))
        await db.execute(delete(AgentDemand).where(
            (AgentDemand.target_agent_id == row.id) | (AgentDemand.from_agent_id == row.id)))
        await db.execute(delete(Agent).where(Agent.id == row.id))
        await db.commit()


@pytest_asyncio.fixture
async def tier_check():
    """A check of our own in the quarterly tier, so a batch is never empty."""
    check = AuditCheck(name=f"test-tier-{uuid.uuid4().hex[:8]}", command="true", agent_profile="athos",
                       frequency="quarterly")
    async with AsyncSessionLocal() as db:
        db.add(check)
        await db.commit()
        await db.refresh(check)
    yield check
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AuditCheck).where(AuditCheck.id == check.id))
        await db.commit()


async def _tier_routine(owner: Agent, frequency: str = "quarterly", **changes) -> AgentRoutine:
    tier = audit_routines.TIER_BY_FREQUENCY[frequency]
    values = audit_routines.tier_routine_values(tier, owner.id) | {"enabled": True} | changes
    routine = AgentRoutine(**values)
    async with AsyncSessionLocal() as db:
        db.add(routine)
        await db.commit()
        await db.refresh(routine)
    return routine


async def _runs(routine_id: uuid.UUID) -> list[AgentRoutineRun]:
    async with AsyncSessionLocal() as db:
        return list((await db.execute(select(AgentRoutineRun).where(
            AgentRoutineRun.routine_id == routine_id).order_by(AgentRoutineRun.occurrence_at))).scalars())


# ---------------------------------------------------------------- classification


def test_catalog_classifies_every_enabled_check():
    for name, check in CANONICAL_AUDIT_CHECKS.items():
        if check.enabled:
            assert name in audit_routines.TIER_BY_FREQUENCY or audit_check_frequency(name) in (
                "daily", "weekly", "monthly")
    assert audit_check_frequency("ECO-058") == "quarterly"
    assert audit_check_frequency("ECO-005") == "daily"
    assert audit_check_frequency("ECO-031") == "monthly"
    assert audit_check_frequency("ECO-999") == "weekly"


async def test_migration_backfilled_the_approved_classification():
    async with AsyncSessionLocal() as db:
        rows = dict((await db.execute(
            select(AuditCheck.name, AuditCheck.frequency).where(AuditCheck.name.like("ECO-%")))).all())
    if not set(CANONICAL_AUDIT_CHECKS).issubset(rows):
        pytest.skip("Catalog rows are not present in this test database")
    assert {name: rows[name] for name in CANONICAL_AUDIT_CHECKS} == {
        name: audit_check_frequency(name) for name in CANONICAL_AUDIT_CHECKS}


def test_evidence_validity_follows_frequency():
    now = datetime(2026, 11, 13, tzinfo=UTC)
    nine_days = now - timedelta(days=9)
    assert evidence_freshness(nine_days, now, "weekly")[0] == "stale"
    assert evidence_freshness(nine_days, now, "monthly")[0] == "fresh"
    assert evidence_freshness(now - timedelta(days=3), now, "daily")[0] == "stale"
    assert evidence_freshness(now - timedelta(days=80), now, "quarterly")[0] == "fresh"


# ---------------------------------------------------------------- runner


async def test_tier_batch_runs_only_that_tier_in_one_batch(tier_check, fake_checks):
    batch_id = uuid.uuid4()
    try:
        async with AsyncSessionLocal() as db:
            runs = await audit_routes.run_audit_batch(db, "quarterly", "routine", batch_id=batch_id)
            frequencies = {(await db.get(AuditCheck, run.check_id)).frequency for run in runs}
        assert frequencies == {"quarterly"}
        assert tier_check.name in fake_checks
        assert {run.batch_id for run in runs} == {batch_id}
        assert {run.requested_by for run in runs} == {"routine"}
        with pytest.raises(ValueError):
            async with AsyncSessionLocal() as db:
                await audit_routes.run_audit_batch(db, "hourly", "routine")
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AuditCheckRun).where(AuditCheckRun.batch_id == batch_id))
            await db.commit()


async def test_check_command_carries_its_frequency_to_the_verifier(monkeypatch):
    sent: dict = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"exit_code": 0, "stdout": "ok", "stderr": ""}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json, headers):
            sent.update(json)
            return FakeResponse()

    monkeypatch.setattr(audit_routes.httpx, "AsyncClient", FakeClient)
    check = AuditCheck(id=uuid.uuid4(), name="ECO-031", command="python3 v.py --check ECO-031",
                       timeout_seconds=55, frequency="monthly")
    run = await audit_routes._execute_check(check, "routine")
    assert run.status == "ok"
    assert sent["command"].startswith("FORGEHUB_AUDIT_FREQUENCY=monthly timeout 55 bash -c ")


async def test_frequency_edit_is_admin_only(tier_check):
    app = FastAPI()
    app.include_router(audit_routes.router)

    def not_admin():
        raise HTTPException(status_code=403, detail="Admin access required")

    app.dependency_overrides[get_current_admin] = not_admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        url = f"/api/v1/audit/checks/{tier_check.id}/frequency"
        assert (await client.put(url, json={"frequency": "daily"})).status_code == 403
        app.dependency_overrides[get_current_admin] = lambda: object()
        assert (await client.put(url, json={"frequency": "hourly"})).status_code == 422
        response = await client.put(url, json={"frequency": "daily"})
        assert response.status_code == 200 and response.json()["frequency"] == "daily"
        assert (await client.post("/api/v1/audit/run?frequency=hourly")).status_code == 422


# ---------------------------------------------------------------- routines


async def test_ensure_creates_four_disabled_tiers_once(owner):
    async with AsyncSessionLocal() as db:
        existing = (await db.execute(select(func.count()).where(AgentRoutine.kind == "audit"))).scalar_one()
    if existing:
        pytest.skip("audit routines already exist in this database")
    async with AsyncSessionLocal() as db:
        first = await audit_routines.ensure_audit_routines(db, owner=owner)
    async with AsyncSessionLocal() as db:
        second = await audit_routines.ensure_audit_routines(db, owner=owner)
        rows = list((await db.execute(select(AgentRoutine).where(AgentRoutine.kind == "audit"))).scalars())
    assert first["created"] == ["daily", "weekly", "monthly", "quarterly"]
    assert second["created"] == [] and second["existing"] == ["daily", "monthly", "quarterly", "weekly"]
    schedules = {r.audit_frequency: (r.schedule, r.timezone, r.enabled, r.agent_id) for r in rows}
    assert schedules == {
        "daily": ("0 19 * * *", "America/Sao_Paulo", False, owner.id),
        "weekly": ("0 19 * * 0", "America/Sao_Paulo", False, owner.id),
        "monthly": ("0 19 1 * *", "America/Sao_Paulo", False, owner.id),
        "quarterly": ("0 19 1 1,4,7,10 *", "America/Sao_Paulo", False, owner.id),
    }


async def test_ensure_without_owner_creates_nothing():
    async with AsyncSessionLocal() as db:
        athos = (await db.execute(select(Agent).where(Agent.profile_slug == "athos"))).scalar_one_or_none()
        if athos is not None:
            pytest.skip("this database has an athos agent")
        result = await audit_routines.ensure_audit_routines(db)
    assert result["created"] == [] and "not found" in result["error"]


async def test_occurrence_runs_the_tier_batch_without_a_messages_task(owner, tier_check, fake_checks):
    async with AsyncSessionLocal() as db:
        db.add(AgentCharter(agent_id=owner.id, mission="Testar auditoria", daily_run_budget=0))
        await db.commit()
    # An hourly schedule keeps "now" real: the pass also visits every other
    # routine of the shared database, whose cursors must not jump ahead.
    now = datetime.now(UTC).replace(minute=5, second=0, microsecond=0)
    routine = await _tier_routine(owner, schedule="0 * * * *", timezone="UTC",
                                  last_occurrence_at=now - timedelta(minutes=10))

    async with AsyncSessionLocal() as db:
        await ops.run_routine_generation_pass(db, now=now)
    [run] = await _runs(routine.id)
    # A zero run budget doesn't stop it: an audit batch spends no LLM run.
    assert run.status == "scheduled" and run.demand_id is None and run.audit_batch_id is not None

    async with AsyncSessionLocal() as db:
        # The Messages sync never touches an audit run (it has no task).
        await ops.run_routine_sync_pass(db)
    assert (await _runs(routine.id))[0].status == "scheduled"

    async with AsyncSessionLocal() as db:
        assert await audit_routines.run_audit_routine_pass(db, background=False) >= 1
    [run] = await _runs(routine.id)
    assert run.status == "completed"
    assert run.evidence_received is True and run.no_action is True
    assert run.cost_usd == 0 and run.finished_at is not None
    assert tier_check.name in fake_checks
    async with AsyncSessionLocal() as db:
        batch = list((await db.execute(
            select(AuditCheckRun).where(AuditCheckRun.batch_id == run.audit_batch_id))).scalars())
        assert {row.requested_by for row in batch} == {"routine"}
        assert tier_check.id in {row.check_id for row in batch}
        # A second claim of the same run does nothing.
        assert await audit_routines.execute_audit_run(db, run.id) is None
        tiers, source = await audit_routes.audit_tiers(
            db, list((await db.execute(select(AuditCheck))).scalars()), datetime.now(UTC))
    quarterly = next(tier for tier in tiers if tier.frequency == "quarterly")
    assert quarterly.routine_id == routine.id and quarterly.routine_enabled
    assert quarterly.last_complete_run_at is not None and quarterly.next_due_at is not None
    assert source == "hermes_cron"  # the other three tiers have no routine here


async def test_failing_checks_complete_the_run_with_their_names(owner, tier_check, monkeypatch):
    async def failing(check: AuditCheck, requested_by: str) -> AuditCheckRun:
        return AuditCheckRun(check_id=check.id, status="fail" if check.id == tier_check.id else "ok",
                             exit_code=1, output="no", duration_ms=1, requested_by=requested_by,
                             created_at=datetime.now(UTC))

    async def no_incident(db, check, run):
        return False

    monkeypatch.setattr(audit_routes, "_execute_check", failing)
    monkeypatch.setattr(audit_routes, "_sync_check_incident", no_incident)
    routine = await _tier_routine(owner)
    async with AsyncSessionLocal() as db:
        run = audit_routines.new_audit_run(routine, datetime.now(UTC))
        db.add(run)
        await db.commit()
        run = await audit_routines.execute_audit_run(db, run.id)
    assert run.status == "completed" and run.no_action is False
    assert tier_check.name in run.detail


async def test_interrupted_batch_is_recorded_as_failed(owner):
    routine = await _tier_routine(owner)
    long_ago = datetime.now(UTC) - timedelta(days=1)
    async with AsyncSessionLocal() as db:
        run = audit_routines.new_audit_run(routine, long_ago)
        run.status = "running"
        db.add(run)
        await db.commit()
        await db.execute(AgentRoutineRun.__table__.update().where(
            AgentRoutineRun.id == run.id).values(updated_at=long_ago))
        await db.commit()
    async with AsyncSessionLocal() as db:  # a fresh identity map sees the old updated_at
        assert await audit_routines.fail_interrupted_audit_runs(db) >= 1
    [run] = await _runs(routine.id)
    assert run.status == "failed" and run.evidence_received is False


async def test_run_now_starts_the_batch_in_the_background(owner, tier_check, fake_checks):
    routine = await _tier_routine(owner)
    app = FastAPI()
    app.include_router(ops.router)
    app.dependency_overrides[get_current_admin] = lambda: type("Admin", (), {"username": "tester"})()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"/api/v1/operations/routines/{routine.id}:run-now")
        assert response.status_code == 201, response.text
        assert response.json()["audit_batch_id"] and response.json()["demand_id"] is None
        await audit_routines.drain_audit_runs()
    [run] = await _runs(routine.id)
    assert run.status == "completed" and tier_check.name in fake_checks


async def test_routes_never_create_or_convert_audit_routines(owner):
    app = FastAPI()
    app.include_router(ops.router)
    app.dependency_overrides[get_current_admin] = lambda: type("Admin", (), {"username": "tester"})()
    routine = await _tier_routine(owner)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post("/api/v1/operations/routines", json={
            "agent_id": str(owner.id), "title": "x", "instructions": "y", "schedule": "0 19 * * *",
            "kind": "audit"})
        assert created.status_code == 422
        changed = await client.patch(f"/api/v1/operations/routines/{routine.id}", json={"kind": "report"})
        assert changed.status_code == 422
        # Pausing (the screen resends the whole routine, kind included) still works.
        paused = await client.patch(f"/api/v1/operations/routines/{routine.id}",
                                    json={"kind": "audit", "enabled": False})
        assert paused.status_code == 200 and paused.json()["audit_frequency"] == "quarterly"


# ---------------------------------------------------------------- monitor


def test_monitor_reports_the_cron_as_replaced_once_routines_run():
    from app.api.routes.foundation import CronJobOut

    now = datetime(2026, 11, 20, tzinfo=UTC)
    job = CronJobOut(profile="athos", id="weekly", name="ecosystem-weekly-audit", script="ecosystem_weekly_audit.sh",
                     script_state="ok", is_audit_job=True, schedule_display="0 19 * * 0", enabled=False,
                     state="paused", status="paused", health="off")
    replaced = inspect_athos_audit_job([job], [], None, now, replaced_by_routines=True)
    assert replaced.state == "replaced" and replaced.issues == []
    assert inspect_athos_audit_job([], [], None, now, replaced_by_routines=True).state == "replaced"
    still_on = job.model_copy(update={"enabled": True, "state": "scheduled", "status": "active", "health": "ok"})
    both = inspect_athos_audit_job([still_on], [], None, now, replaced_by_routines=True)
    assert both.state == "degraded" and "still enabled" in both.issues[0]


# ---------------------------------------------------------------- review fixes


async def _cleanup_notifications(run_ids) -> None:
    from app.db.models.notification import Notification

    async with AsyncSessionLocal() as db:
        await db.execute(delete(Notification).where(
            Notification.event_key.in_([f"audit-routine-run:{run_id}" for run_id in run_ids])))
        await db.commit()


async def test_lost_quarterly_run_is_notified_and_retried_once(owner):
    from app.db.models.notification import Notification

    routine = await _tier_routine(owner)  # quarterly
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as db:
        lost = audit_routines.new_audit_run(routine, now - timedelta(hours=2))
        lost.status, lost.detail = "failed", "Lote do Auditor interrompido"
        db.add(lost)
        await db.commit()
    try:
        async with AsyncSessionLocal() as db:
            assert await audit_routines.handle_lost_audit_runs(db, now) == {"notified": 1, "retries": 1}
        async with AsyncSessionLocal() as db:
            # A second sweep neither notifies again nor retries again.
            assert await audit_routines.handle_lost_audit_runs(db, now) == {"notified": 0, "retries": 0}
            note = (await db.execute(select(Notification).where(
                Notification.event_key == f"audit-routine-run:{lost.id}"))).scalar_one()
        assert note.severity == "warning" and "nova tentativa" in note.message.lower()
        runs = await _runs(routine.id)
        [retry] = [run for run in runs if run.retry_of_run_id == lost.id]
        assert retry.status == "scheduled" and retry.occurrence_at == now + audit_routines.RETRY_DELAY
        async with AsyncSessionLocal() as db:
            # Not due yet: the pass leaves it for its own time.
            assert await audit_routines.run_audit_routine_pass(db, background=False, now=now) == 0
            # The retry failing too is notified but never retried again.
            row = await db.get(AgentRoutineRun, retry.id)
            row.status = "failed"
            await db.commit()
        async with AsyncSessionLocal() as db:
            assert await audit_routines.handle_lost_audit_runs(db, now + timedelta(hours=2)) == {
                "notified": 1, "retries": 0}
    finally:
        await _cleanup_notifications([run.id for run in await _runs(routine.id)])


async def test_lost_daily_run_is_notified_without_retry(owner):
    routine = await _tier_routine(owner, "daily")
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as db:
        lost = audit_routines.new_audit_run(routine, now - timedelta(hours=3))
        lost.status = "missed"
        db.add(lost)
        await db.commit()
    try:
        async with AsyncSessionLocal() as db:
            assert await audit_routines.handle_lost_audit_runs(db, now) == {"notified": 1, "retries": 0}
        assert [run.id for run in await _runs(routine.id)] == [lost.id]
    finally:
        await _cleanup_notifications([lost.id])


async def test_manual_run_is_refused_while_a_batch_holds_the_lock():
    app = FastAPI()
    app.include_router(audit_routes.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with audit_routines.audit_batch_lock():
            response = await client.post("/api/v1/audit/run?frequency=daily")
    assert response.status_code == 409


async def test_a_tier_waiting_for_the_lock_stays_scheduled_and_is_not_failed(owner, tier_check, fake_checks):
    import asyncio

    routine = await _tier_routine(owner)
    async with AsyncSessionLocal() as db:
        run = audit_routines.new_audit_run(routine, datetime.now(UTC) - timedelta(days=1))
        db.add(run)
        await db.commit()
    lock = audit_routines.audit_batch_lock()
    await lock.acquire()
    try:
        task = audit_routines.start_audit_run(run.id)
        assert audit_routines.start_audit_run(run.id) is None  # one task per run
        await asyncio.sleep(0.2)
        async with AsyncSessionLocal() as db:
            assert await audit_routines.fail_interrupted_audit_runs(db) == 0
        assert (await _runs(routine.id))[0].status == "scheduled"
    finally:
        lock.release()
    await task
    assert (await _runs(routine.id))[0].status == "completed"


async def test_enabling_a_routine_records_when(owner):
    routine = await _tier_routine(owner, enabled=False)
    app = FastAPI()
    app.include_router(ops.router)
    app.dependency_overrides[get_current_admin] = lambda: type("Admin", (), {"username": "tester"})()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(f"/api/v1/operations/routines/{routine.id}", json={"enabled": True})
    assert response.status_code == 200
    async with AsyncSessionLocal() as db:
        row = await db.get(AgentRoutine, routine.id)
    assert row.enabled_at is not None and datetime.now(UTC) - row.enabled_at < timedelta(minutes=1)

"""A failed control has one actionable owner until verification recovers."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.api.routes import audit as audit_routes
from app.db.base import AsyncSessionLocal
from app.db.models.audit import AuditCheck, AuditCheckRun
from app.db.models.demand import AgentDemand
from app.db.models.notification import Notification


@pytest_asyncio.fixture
async def client():
    app = FastAPI()
    app.include_router(audit_routes.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def athos_agent():
    """The Auditor files its Tasks from Athos; a Task needs both agents
    registered (otherwise it becomes an incubation). The fresh test database
    has only the fictitious seed, so register the slug if it isn't there and
    remove only what was created here."""
    from app.db.models.agent import Agent

    async with AsyncSessionLocal() as db:
        existing = (await db.execute(select(Agent).where(Agent.profile_slug == "athos"))).scalar_one_or_none()
        if existing is not None:
            yield existing.id
            return
        agent = Agent(name=f"Athos (test) {uuid.uuid4().hex[:6]}", profile_slug="athos", is_active=True)
        db.add(agent)
        await db.commit()
        agent_id = agent.id
    yield agent_id
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AgentDemand).where(
            (AgentDemand.from_agent_id == agent_id) | (AgentDemand.target_agent_id == agent_id)))
        await db.execute(delete(Agent).where(Agent.id == agent_id))
        await db.commit()


async def test_failed_check_creates_one_owner_task_and_recovery_closes_it(client, monkeypatch, athos_agent, test_suite_agent):
    check = AuditCheck(
        name=f"test-incident-{uuid.uuid4().hex[:10]}",
        command="verify-test-control",
        agent_profile="test-suite",
        enabled=True,
        timeout_seconds=10,
    )
    async with AsyncSessionLocal() as db:
        db.add(check)
        await db.commit()
        await db.refresh(check)

    outcomes = iter(("fail", "fail", "ok"))

    async def fake_execute(current: AuditCheck, requested_by: str) -> AuditCheckRun:
        outcome = next(outcomes)
        return AuditCheckRun(
            check_id=current.id, status=outcome, exit_code=0 if outcome == "ok" else 1,
            output=f"test evidence: {outcome}", duration_ms=1, requested_by=requested_by,
        )

    monkeypatch.setattr(audit_routes, "_execute_check", fake_execute)
    monkeypatch.setattr("app.core.dispatch_signal.wake_scheduled_dispatch", lambda: None)
    prefix = f"[Auditor:{check.id}]"
    try:
        for index, expected_status in enumerate(("fail", "fail", "ok")):
            response = await client.post(f"/api/v1/audit/checks/{check.id}/run")
            assert response.status_code == 200, response.text
            assert response.json()["status"] == expected_status
            async with AsyncSessionLocal() as db:
                demands = list((await db.execute(
                    select(AgentDemand).where(AgentDemand.subject.startswith(prefix))
                )).scalars())
                assert len(demands) == 1
                assert demands[0].origin_type == "task"
                assert demands[0].target_agent_id is not None
                assert "verify-test-control" in demands[0].body
                assert demands[0].status == ("archived" if expected_status == "ok" else "new")
                if expected_status == "ok":
                    assert "test evidence: ok" in demands[0].body
                if index == 0:
                    # The owner tried and failed; a second failed verification
                    # must surface one escalation instead of another Task.
                    demands[0].dispatch_status = "failed"
                    await db.commit()
                if index == 1:
                    notifications = list((await db.execute(
                        select(Notification).where(Notification.event_key == f"audit-escalation:{demands[0].id}")
                    )).scalars())
                    assert len(notifications) == 1
                    assert notifications[0].severity == "error"
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Notification).where(Notification.event_key.like("audit-escalation:%"), Notification.title.contains(check.name)))
            await db.execute(delete(AgentDemand).where(AgentDemand.subject.startswith(prefix)))
            await db.execute(delete(AuditCheck).where(AuditCheck.id == check.id))
            await db.commit()


async def test_check_with_unknown_owner_records_failure_without_losing_run(client, monkeypatch):
    check = AuditCheck(
        name=f"test-unowned-{uuid.uuid4().hex[:10]}", command="verify-test-control",
        agent_profile=f"absent-{uuid.uuid4().hex[:10]}", enabled=True, timeout_seconds=10,
    )
    async with AsyncSessionLocal() as db:
        db.add(check)
        await db.commit()
        await db.refresh(check)

    async def fake_execute(current: AuditCheck, requested_by: str) -> AuditCheckRun:
        return AuditCheckRun(
            check_id=current.id, status="fail", exit_code=1, output="broken",
            duration_ms=1, requested_by=requested_by,
        )

    monkeypatch.setattr(audit_routes, "_execute_check", fake_execute)
    try:
        response = await client.post(f"/api/v1/audit/checks/{check.id}/run")
        assert response.status_code == 200, response.text
        async with AsyncSessionLocal() as db:
            assert (await db.execute(select(AuditCheckRun).where(AuditCheckRun.check_id == check.id))).scalar_one().status == "fail"
            warning = (await db.execute(select(Notification).where(
                Notification.event_key == f"audit-unowned:{check.id}"
            ))).scalar_one()
            assert warning.severity == "error"
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Notification).where(Notification.event_key == f"audit-unowned:{check.id}"))
            await db.execute(delete(AuditCheck).where(AuditCheck.id == check.id))
            await db.commit()


async def test_remediation_reconciles_existing_incident_and_does_not_queue_duplicate_repair(client, monkeypatch, athos_agent, test_suite_agent):
    from app.core.deps import get_current_admin

    client._transport.app.dependency_overrides[get_current_admin] = lambda: object()
    check = AuditCheck(name=f"test-recovery-{uuid.uuid4().hex}", command="true", agent_profile="test-suite", enabled=True)
    async with AsyncSessionLocal() as db:
        db.add(check)
        await db.commit()
    outcome = "fail"

    async def execute(current, requested_by):
        return AuditCheckRun(check_id=current.id, status=outcome, exit_code=0 if outcome == "ok" else 1,
                             output=f"verification {outcome}", requested_by=requested_by)

    async def delegate(current, previous):
        return AuditCheckRun(check_id=current.id, status="ok", exit_code=0, output="repair done", requested_by="athos-remediation")

    monkeypatch.setattr(audit_routes, "_execute_check", execute)
    monkeypatch.setattr(audit_routes, "_delegate_remediation_to_athos", delegate)
    monkeypatch.setattr("app.core.dispatch_signal.wake_scheduled_dispatch", lambda: None)
    prefix = f"[Auditor:{check.id}]"
    try:
        assert (await client.post(f"/api/v1/audit/checks/{check.id}/run")).status_code == 200
        outcome = "ok"
        result = await client.post(f"/api/v1/audit/checks/{check.id}/remediate")
        assert result.status_code == 200, result.text
        assert result.json()["escalated_to_inbox"] is False
        assert (await client.post(f"/api/v1/audit/checks/{check.id}/run")).status_code == 200
        async with AsyncSessionLocal() as db:
            demands = list((await db.scalars(select(AgentDemand).where(AgentDemand.subject.startswith(prefix)))).all())
            assert len(demands) == 1
            assert demands[0].status == "archived"
            assert demands[0].scheduled_at is None
            assert demands[0].body.count("[Auditor recovery]") == 1
            assert str(result.json()["verification_run"]["id"]) in demands[0].body
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AgentDemand).where(AgentDemand.subject.startswith(prefix)))
            await db.execute(delete(AuditCheck).where(AuditCheck.id == check.id))
            await db.commit()


async def test_concurrent_remediation_and_verification_keep_one_recovered_incident(client, monkeypatch, athos_agent, test_suite_agent):
    import asyncio
    from app.core.deps import get_current_admin

    client._transport.app.dependency_overrides[get_current_admin] = lambda: object()
    check = AuditCheck(name=f"test-concurrent-recovery-{uuid.uuid4().hex}", command="true", agent_profile="test-suite", enabled=True)
    async with AsyncSessionLocal() as db:
        db.add(check)
        await db.commit()
    outcome = "fail"

    async def execute(current, requested_by):
        return AuditCheckRun(check_id=current.id, status=outcome, exit_code=0 if outcome == "ok" else 1,
                             output=f"verification {outcome}", requested_by=requested_by)

    async def delegate(current, previous):
        return AuditCheckRun(check_id=current.id, status="ok", exit_code=0, output="repair done", requested_by="athos-remediation")

    monkeypatch.setattr(audit_routes, "_execute_check", execute)
    monkeypatch.setattr(audit_routes, "_delegate_remediation_to_athos", delegate)
    monkeypatch.setattr("app.core.dispatch_signal.wake_scheduled_dispatch", lambda: None)
    prefix = f"[Auditor:{check.id}]"
    try:
        assert (await client.post(f"/api/v1/audit/checks/{check.id}/run")).status_code == 200
        outcome = "ok"
        barrier = asyncio.Barrier(2)
        original_sync = audit_routes._sync_check_incident

        async def simultaneous_sync(db, current, run):
            # Both transactions have inserted evidence/FK references before
            # either acquires the incident mutex, as remediation can do.
            await db.flush()
            await barrier.wait()
            return await original_sync(db, current, run)

        monkeypatch.setattr(audit_routes, "_sync_check_incident", simultaneous_sync)
        responses = await asyncio.wait_for(asyncio.gather(
            client.post(f"/api/v1/audit/checks/{check.id}/remediate"),
            client.post(f"/api/v1/audit/checks/{check.id}/run"),
            return_exceptions=True,
        ), timeout=10)
        assert all(not isinstance(response, BaseException) and response.status_code == 200 for response in responses), responses
        async with AsyncSessionLocal() as db:
            demands = list((await db.scalars(select(AgentDemand).where(AgentDemand.subject.startswith(prefix)))).all())
            assert len(demands) == 1
            assert demands[0].status == "archived"
            assert demands[0].scheduled_at is None
            assert demands[0].body.count("[Auditor recovery]") == 1
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AgentDemand).where(AgentDemand.subject.startswith(prefix)))
            await db.execute(delete(AuditCheck).where(AuditCheck.id == check.id))
            await db.commit()


@pytest.mark.parametrize("older_status,newer_status,older_source", [("ok", "fail", "manual"), ("fail", "ok", "manual"), ("fail", "ok", "remediation")])
async def test_delayed_opposite_verdict_cannot_reverse_newer_incident(client, monkeypatch, athos_agent, test_suite_agent, older_status, newer_status, older_source):
    import asyncio
    from app.core.deps import get_current_admin

    client._transport.app.dependency_overrides[get_current_admin] = lambda: object()

    check = AuditCheck(name=f"test-ordered-incident-{uuid.uuid4().hex}", command="true", agent_profile="test-suite", enabled=True)
    async with AsyncSessionLocal() as db:
        db.add(check)
        await db.commit()
    now = datetime.now(timezone.utc)
    outcomes = iter((("fail", now-timedelta(seconds=3), "initial"),
                     (older_status, now-timedelta(seconds=2), "older"),
                     (newer_status, now-timedelta(seconds=1), "newer")))

    async def execute(current, requested_by):
        verdict, completed_at, output = next(outcomes)
        return AuditCheckRun(check_id=current.id, status=verdict, exit_code=0 if verdict == "ok" else 1,
                             output=output, requested_by=requested_by, created_at=completed_at)

    async def delegate(current, previous):
        return AuditCheckRun(check_id=current.id, status="ok", exit_code=0,
            output="repair done", requested_by="athos-remediation", created_at=now-timedelta(seconds=2))

    monkeypatch.setattr(audit_routes, "_delegate_remediation_to_athos", delegate)
    waiting = asyncio.Event()
    release = asyncio.Event()
    original_sync = audit_routes._sync_check_incident

    async def delayed_sync(db, current, run):
        if run.output == "older":
            waiting.set()
            await release.wait()
        return await original_sync(db, current, run)

    monkeypatch.setattr(audit_routes, "_execute_check", execute)
    monkeypatch.setattr(audit_routes, "_sync_check_incident", delayed_sync)
    monkeypatch.setattr("app.core.dispatch_signal.wake_scheduled_dispatch", lambda: None)
    prefix = f"[Auditor:{check.id}]"
    older_request = None
    try:
        assert (await client.post(f"/api/v1/audit/checks/{check.id}/run")).status_code == 200
        older_endpoint = "remediate" if older_source == "remediation" else "run"
        older_request = asyncio.create_task(client.post(f"/api/v1/audit/checks/{check.id}/{older_endpoint}"))
        await asyncio.wait_for(waiting.wait(), timeout=5)
        newer_response = await client.post(f"/api/v1/audit/checks/{check.id}/run")
        assert newer_response.status_code == 200, newer_response.text
        release.set()
        older_response = await asyncio.wait_for(older_request, timeout=5)
        assert older_response.status_code == 200
        if older_source == "remediation":
            assert older_response.json()["escalated_to_inbox"] is False
            assert older_response.json()["inbox_demand_id"] is None
        actual = next(c for c in (await client.get("/api/v1/audit/checks")).json() if c["id"] == str(check.id))
        assert actual["last_run"]["id"] == newer_response.json()["id"]
        async with AsyncSessionLocal() as db:
            demands = list((await db.scalars(select(AgentDemand).where(AgentDemand.subject.startswith(prefix)))).all())
            assert list((await db.scalars(select(AgentDemand).where(
                AgentDemand.subject == f"[Auditor] Manual correction required: {check.name}"
            ))).all()) == []
            assert len(demands) == 1
            assert demands[0].status == ("archived" if newer_status == "ok" else "new")
            if newer_status == "ok":
                assert newer_response.json()["id"] in demands[0].body
            else:
                assert "[Auditor recovery]" not in demands[0].body
    finally:
        release.set()
        if older_request is not None:
            await asyncio.gather(older_request, return_exceptions=True)
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AgentDemand).where(
                AgentDemand.subject.startswith(prefix) | (AgentDemand.subject == f"[Auditor] Manual correction required: {check.name}")
            ))
            await db.execute(delete(AuditCheck).where(AuditCheck.id == check.id))
            await db.commit()


async def test_slow_batch_does_not_redate_failure_after_manual_recovery(client, monkeypatch, athos_agent, test_suite_agent):
    import asyncio

    suffix = uuid.uuid4().hex
    first = AuditCheck(name=f"test-batch-race-first-{suffix}", command="true", agent_profile="test-suite", enabled=True)
    slow = AuditCheck(name=f"test-batch-race-slow-{suffix}", command="true", agent_profile="test-suite", enabled=True)
    async with AsyncSessionLocal() as db:
        db.add_all([first, slow])
        await db.commit()
    failure_observed = asyncio.Event()
    slow_started = asyncio.Event()
    release = asyncio.Event()
    manual_calls = 0
    initial_failed_at = None
    batch_runs = []
    prefix = f"[Auditor:{first.id}]"
    original_sync = audit_routes._sync_check_incident

    async def execute(current, requested_by):
        nonlocal manual_calls, initial_failed_at
        verdict = "ok"
        if requested_by == "cron" and current.id == first.id:
            verdict = "fail"
            initial_failed_at = datetime.now(timezone.utc)
            failure_observed.set()
        elif requested_by == "cron" and current.id == slow.id:
            slow_started.set()
            await release.wait()
        elif current.id == first.id:
            manual_calls += 1
            verdict = "fail" if manual_calls == 1 else "ok"
        return AuditCheckRun(check_id=current.id, status=verdict, exit_code=0 if verdict == "ok" else 1,
            output=f"test batch {suffix}", requested_by=requested_by,
            created_at=initial_failed_at if requested_by == "cron" and current.id == first.id else datetime.now(timezone.utc))

    async def sync(db, current, run):
        return await original_sync(db, current, run) if current.id == first.id else False

    async def batch():
        async with AsyncSessionLocal() as db:
            batch_runs.extend(await audit_routes._run_enabled_checks(db, "cron"))

    monkeypatch.setattr(audit_routes, "_execute_check", execute)
    monkeypatch.setattr(audit_routes, "_sync_check_incident", sync)
    monkeypatch.setattr("app.core.dispatch_signal.wake_scheduled_dispatch", lambda: None)
    batch_task = None
    try:
        assert (await client.post(f"/api/v1/audit/checks/{first.id}/run")).status_code == 200
        batch_task = asyncio.create_task(batch())
        await asyncio.wait_for(asyncio.gather(failure_observed.wait(), slow_started.wait()), timeout=5)
        recovered = await client.post(f"/api/v1/audit/checks/{first.id}/run")
        assert recovered.status_code == 200, recovered.text
        release.set()
        await asyncio.wait_for(batch_task, timeout=10)
        actual = next(c for c in (await client.get("/api/v1/audit/checks")).json() if c["id"] == str(first.id))
        assert actual["last_run"]["id"] == recovered.json()["id"]
        assert next(run for run in batch_runs if run.check_id == first.id).created_at == initial_failed_at
        assert len({run.batch_id for run in batch_runs}) == 1
        assert batch_runs[0].batch_id is not None
        async with AsyncSessionLocal() as db:
            demands = list((await db.scalars(select(AgentDemand).where(AgentDemand.subject.startswith(prefix)))).all())
            assert len(demands) == 1
            assert demands[0].status == "archived"
    finally:
        release.set()
        if batch_task is not None:
            await asyncio.gather(batch_task, return_exceptions=True)
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AgentDemand).where(AgentDemand.subject.startswith(prefix)))
            await db.execute(delete(AuditCheckRun).where(AuditCheckRun.output == f"test batch {suffix}"))
            await db.execute(delete(AuditCheck).where(AuditCheck.id.in_([first.id, slow.id])))
            await db.commit()

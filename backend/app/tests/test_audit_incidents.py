"""A failed control has one actionable owner until verification recovers."""

import uuid

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


async def test_failed_check_creates_one_owner_task_and_recovery_closes_it(client, monkeypatch):
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

"""Audit remediation: explicit repair, persisted evidence, and recheck."""

import uuid
from types import SimpleNamespace

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.api.routes import audit as audit_routes
from app.core.deps import get_current_admin
from app.db.base import AsyncSessionLocal
from app.db.models.audit import AuditCheck, AuditCheckRun


@pytest_asyncio.fixture
async def client():
    app = FastAPI()
    app.include_router(audit_routes.router)
    app.dependency_overrides[get_current_admin] = lambda: object()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def _cleanup(check_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AuditCheck).where(AuditCheck.id == check_id))
        await db.commit()


async def test_remediation_is_delegated_to_athos_and_followed_by_verification(
    client: AsyncClient, monkeypatch
):
    check = AuditCheck(
        name=f"test-remediation-{uuid.uuid4().hex[:8]}",
        description="Test control",
        command="verify-command",
        remediation_description="Repair test state",
        remediation_command="repair-command",
        agent_profile="athos",
        enabled=True,
        timeout_seconds=10,
    )
    async with AsyncSessionLocal() as db:
        db.add(check)
        await db.commit()
        await db.refresh(check)

    calls: list[tuple[str, str]] = []

    async def fake_delegate(current: AuditCheck, previous: AuditCheckRun | None) -> AuditCheckRun:
        calls.append((current.name, "athos-remediation"))
        return AuditCheckRun(
            check_id=current.id,
            status="ok",
            exit_code=0,
            output="Athos corrected the control",
            duration_ms=1,
            requested_by="athos-remediation",
        )

    async def fake_verify(current: AuditCheck, requested_by: str) -> AuditCheckRun:
        calls.append((current.command, requested_by))
        return AuditCheckRun(
            check_id=current.id,
            status="ok",
            exit_code=0,
            output="verification passed",
            duration_ms=1,
            requested_by=requested_by,
        )

    monkeypatch.setattr(audit_routes, "_delegate_remediation_to_athos", fake_delegate)
    monkeypatch.setattr(audit_routes, "_execute_check", fake_verify)
    try:
        response = await client.post(f"/api/v1/audit/checks/{check.id}/remediate")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["remediation_run"]["requested_by"] == "athos-remediation"
        assert body["verification_run"]["requested_by"] == "remediation-verification"
        assert body["escalated_to_inbox"] is False
        assert body["inbox_demand_id"] is None
        assert calls == [
            (check.name, "athos-remediation"),
            ("verify-command", "remediation-verification"),
        ]
    finally:
        await _cleanup(check.id)


async def test_failed_athos_remediation_is_escalated_to_inbox(
    client: AsyncClient, monkeypatch
):
    check = AuditCheck(
        name=f"test-no-remediation-{uuid.uuid4().hex[:8]}",
        command="verify-command",
        agent_profile="athos",
        enabled=True,
        timeout_seconds=10,
    )
    async with AsyncSessionLocal() as db:
        db.add(check)
        await db.commit()
        await db.refresh(check)

    async def fake_delegate(current: AuditCheck, previous: AuditCheckRun | None) -> AuditCheckRun:
        return AuditCheckRun(
            check_id=current.id,
            status="error",
            exit_code=None,
            output="Athos could not apply a safe correction",
            duration_ms=1,
            requested_by="athos-remediation",
        )

    async def fake_verify(current: AuditCheck, requested_by: str) -> AuditCheckRun:
        return AuditCheckRun(
            check_id=current.id,
            status="fail",
            exit_code=1,
            output="control remains unhealthy",
            duration_ms=1,
            requested_by=requested_by,
        )

    demand_id = uuid.uuid4()
    submitted = []

    async def fake_create_demand(db, payload):
        submitted.append(payload)
        await db.commit()
        return SimpleNamespace(id=demand_id)

    monkeypatch.setattr(audit_routes, "_delegate_remediation_to_athos", fake_delegate)
    monkeypatch.setattr(audit_routes, "_execute_check", fake_verify)
    monkeypatch.setattr(audit_routes, "create_demand_and_notify", fake_create_demand)
    try:
        response = await client.post(f"/api/v1/audit/checks/{check.id}/remediate")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["escalated_to_inbox"] is True
        assert body["inbox_demand_id"] == str(demand_id)
        assert len(submitted) == 1
        assert submitted[0].from_agent == "athos"
        assert check.name in submitted[0].subject
        assert "control remains unhealthy" in submitted[0].body
    finally:
        await _cleanup(check.id)

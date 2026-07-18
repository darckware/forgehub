"""Audit remediation: explicit repair, persisted evidence, and recheck."""

import uuid

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


async def test_remediation_is_recorded_and_followed_by_verification(client: AsyncClient, monkeypatch):
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

    async def fake_execute(current: AuditCheck, command: str, requested_by: str) -> AuditCheckRun:
        calls.append((command, requested_by))
        return AuditCheckRun(
            check_id=current.id,
            status="ok",
            exit_code=0,
            output=f"{requested_by} completed",
            duration_ms=1,
            requested_by=requested_by,
        )

    monkeypatch.setattr(audit_routes, "_execute_command", fake_execute)
    try:
        response = await client.post(f"/api/v1/audit/checks/{check.id}/remediate")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["remediation_run"]["requested_by"] == "remediation"
        assert body["verification_run"]["requested_by"] == "remediation-verification"
        assert calls == [
            ("repair-command", "remediation"),
            ("verify-command", "remediation-verification"),
        ]
    finally:
        await _cleanup(check.id)


async def test_remediation_requires_configured_command(client: AsyncClient):
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
    try:
        response = await client.post(f"/api/v1/audit/checks/{check.id}/remediate")
        assert response.status_code == 409
    finally:
        await _cleanup(check.id)

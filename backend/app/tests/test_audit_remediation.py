"""Audit remediation guard: never hand Athos a correction that targets retired
infrastructure, violates the single-gateway policy, or calls a missing file."""

import uuid

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.api.routes import audit as audit_routes
from app.core.audit_remediation import remediation_problems, structural_remediation_problems
from app.core.deps import get_current_admin
from app.db.base import AsyncSessionLocal
from app.db.models.audit import AuditCheck


def _exists(*present: str):
    return lambda path: path in present


def test_remediation_problems_flags_retired_containers():
    problems = remediation_problems(
        "docker restart company_postgres foundation_postgres", path_exists=_exists()
    )
    assert any("company_postgres" in p for p in problems)
    assert any("foundation_postgres" in p for p in problems)


def test_remediation_problems_flags_per_profile_gateway_units():
    problems = remediation_problems(
        "for p in athos aegis; do systemctl restart hermes-gateway-$p.service; done",
        path_exists=_exists(),
    )
    assert problems and "gateway" in problems[0]
    assert remediation_problems("systemctl restart hermes-gateway-athos.service", path_exists=_exists())


def test_remediation_problems_flags_second_gateway_or_kill():
    assert remediation_problems("hermes gateway run --force", path_exists=_exists())
    assert remediation_problems("pkill -f hermes", path_exists=_exists())


def test_remediation_problems_flags_missing_script_and_redirect():
    problems = remediation_problems(
        "bash /root/.hermes/profiles/athos/scripts/weekly_backup.sh", path_exists=_exists()
    )
    assert problems == ["referenced file does not exist: /root/.hermes/profiles/athos/scripts/weekly_backup.sh"]
    assert remediation_problems(
        "docker exec -i hindsight_postgres psql < /root/missing.sql", path_exists=_exists()
    )


def test_remediation_problems_accepts_current_commands():
    script = "/root/.hermes/profiles/athos/scripts/backup_hermes_root.sh"
    for command in (
        f"bash {script}",
        "XDG_RUNTIME_DIR=/run/user/0 systemctl --user restart hermes-gateway",
        "docker start forgehub_postgres hindsight_postgres forgerouter_postgres",
        "systemctl restart forgehub-chat-bridge.service",
        "timedatectl set-timezone America/Sao_Paulo",
    ):
        assert remediation_problems(command, path_exists=_exists(script)) == [], command


def test_structural_problems_ignore_missing_files():
    # A file can legitimately appear on the host after the check is saved.
    assert structural_remediation_problems("bash /root/not-yet-there.sh") == []
    assert structural_remediation_problems("docker restart foundation_postgres")


@pytest_asyncio.fixture
async def client():
    app = FastAPI()
    app.include_router(audit_routes.router)
    app.dependency_overrides[get_current_admin] = lambda: object()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def _create_check(remediation_command: str | None) -> AuditCheck:
    check = AuditCheck(
        name=f"test-guard-{uuid.uuid4().hex[:8]}",
        command="verify-command",
        remediation_command=remediation_command,
        agent_profile="athos",
        enabled=True,
        timeout_seconds=10,
    )
    async with AsyncSessionLocal() as db:
        db.add(check)
        await db.commit()
        await db.refresh(check)
    return check


async def _cleanup(*names: str) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AuditCheck).where(AuditCheck.name.in_(names)))
        await db.commit()


async def test_remediate_refuses_broken_command(client: AsyncClient, monkeypatch):
    check = await _create_check("systemctl restart hermes-gateway-athos.service")
    called = []

    async def must_not_run(*args, **kwargs):
        called.append(args)
        raise AssertionError("remediation must not be delegated")

    monkeypatch.setattr(audit_routes, "_delegate_remediation_to_athos", must_not_run)
    monkeypatch.setattr(audit_routes, "_execute_check", must_not_run)
    try:
        response = await client.post(f"/api/v1/audit/checks/{check.id}/remediate")
        assert response.status_code == 409, response.text
        assert "gateway" in str(response.json()["detail"])
        assert called == []
    finally:
        await _cleanup(check.name)


async def test_create_check_rejects_retired_target(client: AsyncClient):
    name = f"test-guard-{uuid.uuid4().hex[:8]}"
    try:
        response = await client.post(
            "/api/v1/audit/checks",
            json={
                "name": name,
                "command": "true",
                "remediation_command": "docker restart company_postgres",
            },
        )
        assert response.status_code == 422, response.text
    finally:
        await _cleanup(name)


async def test_update_check_rejects_retired_target(client: AsyncClient):
    check = await _create_check(None)
    try:
        response = await client.patch(
            f"/api/v1/audit/checks/{check.id}",
            json={"remediation_command": "hermes gateway run"},
        )
        assert response.status_code == 422, response.text
    finally:
        await _cleanup(check.name)

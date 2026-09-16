"""Persistent client report behavior against the dedicated PostgreSQL test DB."""
import uuid
from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.client import Client, Irregularity, Workstation
from app.db.models.governance import AuditEvent
from app.db.models.user import User
from app.main import app


@pytest_asyncio.fixture
async def report_world():
    suffix = uuid.uuid4().hex
    async with AsyncSessionLocal() as db:
        admin = User(username=f"report-admin-{suffix}", hashed_password="unused", is_admin=True)
        viewer = User(username=f"report-viewer-{suffix}", hashed_password="unused", is_admin=False)
        a = Client(name=f"Report A {suffix}", notes="private note", created_at=datetime(2026, 7, 1, tzinfo=timezone.utc))
        b = Client(name=f"Report B {suffix}", created_at=datetime(2026, 7, 1, tzinfo=timezone.utc))
        db.add_all([admin, viewer, a, b])
        await db.flush()
        wa = Workstation(client_id=a.id, hostname="<script>alert(1)</script>", os_kind="linux", device_token_hash=uuid.uuid4().hex, device_token_issued_at=datetime(2026, 8, 1, tzinfo=timezone.utc))
        wb = Workstation(client_id=b.id, hostname="other-client", os_kind="linux", device_token_hash=uuid.uuid4().hex, device_token_issued_at=datetime(2026, 8, 1, tzinfo=timezone.utc))
        db.add_all([wa, wb])
        await db.flush()
        ia = Irregularity(workstation_id=wa.id, rule_key="backup_stale", severity="warning", detail="<script>bad()</script>", detected_at=datetime(2026, 8, 31, 23, 59, tzinfo=timezone.utc))
        ib = Irregularity(workstation_id=wb.id, rule_key="disk_space_low", severity="critical", detail="private-other-client", detected_at=datetime(2026, 8, 10, tzinfo=timezone.utc))
        db.add_all([ia, ib])
        await db.commit()
        world = {"a": a.id, "b": b.id, "ia": ia.id, "ib": ib.id, "wa": wa.id, "admin": admin.id, "admin_headers": {"Authorization": f"Bearer {create_access_token(admin.username)}"}, "viewer_headers": {"Authorization": f"Bearer {create_access_token(viewer.username)}"}}
    yield world
    from app.db.models.client_report import ClientReadCredential, ClientReport
    async with AsyncSessionLocal() as db:
        report_ids = select(ClientReport.id).where(ClientReport.client_id.in_([world["a"], world["b"]]))
        await db.execute(delete(AuditEvent).where(AuditEvent.entity_type == "client_report", AuditEvent.entity_id.in_(report_ids)))
        await db.execute(delete(AuditEvent).where(AuditEvent.entity_type == "client_read_credential", AuditEvent.entity_id.in_(select(ClientReadCredential.id).where(ClientReadCredential.client_id.in_([world["a"], world["b"]])))))
        await db.execute(delete(ClientReport).where(ClientReport.client_id.in_([world["a"], world["b"]])))
        await db.execute(delete(ClientReadCredential).where(ClientReadCredential.client_id.in_([world["a"], world["b"]])))
        await db.execute(delete(Client).where(Client.id.in_([world["a"], world["b"]])))
        await db.execute(delete(User).where(User.id.in_([world["admin"]])))
        await db.execute(delete(User).where(User.username == f"report-viewer-{suffix}"))
        await db.commit()


@pytest.mark.asyncio
async def test_monthly_report_is_unique_escaped_and_stable(report_world):
    from app.core.client_reports import generate_client_report

    async with AsyncSessionLocal() as db:
        first = await generate_client_report(db, report_world["a"], date(2026, 8, 1), date(2026, 8, 31), kind="monthly")
        await db.commit()
        initial_html = first.html_content
        initial_snapshot = first.snapshot
        again = await generate_client_report(db, report_world["a"], date(2026, 8, 1), date(2026, 8, 31), kind="monthly")
        assert again.id == first.id
        assert "<script>" not in first.html_content
        assert "&lt;script&gt;" in first.html_content
        assert "Dados de atendimentos e horas não disponíveis nesta fonte" in first.html_content
        assert "private note" not in first.html_content
        assert "private-other-client" not in first.html_content
        assert len(first.snapshot["irregularities"]) == 1
        issue = await db.get(Irregularity, report_world["ia"])
        issue.detail = "changed after generation"
        await db.commit()
        await db.refresh(first)
        assert first.html_content == initial_html
        assert first.snapshot == initial_snapshot


@pytest.mark.asyncio
async def test_report_generation_validates_client_interval_and_incident(report_world):
    from fastapi import HTTPException
    from app.core.client_reports import generate_client_report

    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as invalid:
            await generate_client_report(db, report_world["a"], date(2026, 8, 31), date(2026, 8, 1), kind="on_demand")
        assert invalid.value.status_code == 422
        with pytest.raises(HTTPException) as foreign:
            await generate_client_report(db, report_world["a"], date(2026, 8, 1), date(2026, 8, 31), kind="on_demand", irregularity_id=report_world["ib"])
        assert foreign.value.status_code == 404
        with pytest.raises(HTTPException) as missing:
            await generate_client_report(db, uuid.uuid4(), date(2026, 8, 1), date(2026, 8, 31), kind="on_demand")
        assert missing.value.status_code == 404


@pytest.mark.asyncio
async def test_admin_report_workflow_and_download(report_world):
    path = f"/api/v1/clients/{report_world['a']}/reports"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        assert (await http.get(path, headers=report_world["viewer_headers"])).status_code == 403
        bad = await http.post(path, json={"period_start": "2026-09-01", "period_end": "2026-08-31"}, headers=report_world["admin_headers"])
        assert bad.status_code == 422
        foreign = await http.post(path, json={"period_start": "2026-08-01", "period_end": "2026-08-31", "irregularity_id": str(report_world["ib"])}, headers=report_world["admin_headers"])
        assert foreign.status_code == 404
        created = await http.post(path, json={"period_start": "2026-08-01", "period_end": "2026-08-31"}, headers=report_world["admin_headers"])
        assert created.status_code == 201, created.text
        report = created.json()
        assert report["kind"] == "on_demand" and report["reviewed_at"] is None
        assert "snapshot" not in report and "html_content" not in report
        report_id = report["id"]
        listed = await http.get(path, headers=report_world["admin_headers"])
        assert listed.status_code == 200 and listed.json()[0]["id"] == report_id
        detail = await http.get(f"/api/v1/client-reports/{report_id}", headers=report_world["admin_headers"])
        assert detail.status_code == 200 and detail.json()["snapshot"]["client"]["name"]
        download = await http.get(f"/api/v1/client-reports/{report_id}/download", headers=report_world["admin_headers"])
        assert download.status_code == 200 and "attachment" in download.headers["content-disposition"]
        assert download.headers["x-content-type-options"] == "nosniff"
        reviewed = await http.patch(f"/api/v1/client-reports/{report_id}/review", json={"reviewed": True}, headers=report_world["admin_headers"])
        assert reviewed.status_code == 200 and reviewed.json()["reviewed_by_user_id"] == str(report_world["admin"])
        repeated = await http.patch(f"/api/v1/client-reports/{report_id}/review", json={"reviewed": True}, headers=report_world["admin_headers"])
        assert repeated.status_code == 200 and repeated.json()["reviewed_at"] == reviewed.json()["reviewed_at"]
        revoked = await http.patch(f"/api/v1/client-reports/{report_id}/review", json={"reviewed": False}, headers=report_world["admin_headers"])
        assert revoked.status_code == 200 and revoked.json()["reviewed_at"] is None
        assert (await http.get(f"/api/v1/client-reports/{report_id}", headers=report_world["viewer_headers"])).status_code == 403


@pytest.mark.asyncio
async def test_monthly_route_accepts_only_closed_month_and_is_repeatable(report_world):
    path = f"/api/v1/clients/{report_world['a']}/reports/monthly"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        current = datetime.now(timezone.utc).strftime("%Y-%m")
        assert (await http.post(path, json={"month": current}, headers=report_world["admin_headers"])).status_code == 422
        first = await http.post(path, json={"month": "2026-08"}, headers=report_world["admin_headers"])
        second = await http.post(path, json={"month": "2026-08"}, headers=report_world["admin_headers"])
        assert first.status_code == 200 and second.status_code == 200
        assert first.json()["id"] == second.json()["id"]


@pytest.mark.asyncio
async def test_report_retention_rejects_client_delete(report_world, monkeypatch):
    from app.core import headscale_client

    async def no_policy_push(db):
        return None

    monkeypatch.setattr(headscale_client, "rebuild_and_push_policy", no_policy_push)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        created = await http.post(f"/api/v1/clients/{report_world['a']}/reports", json={"period_start": "2026-08-01", "period_end": "2026-08-31"}, headers=report_world["admin_headers"])
        assert created.status_code == 201
        deleted = await http.delete(f"/api/v1/clients/{report_world['a']}", headers=report_world["admin_headers"])
        assert deleted.status_code == 409
        assert (await http.get(f"/api/v1/clients/{report_world['a']}", headers=report_world["admin_headers"])).status_code == 200

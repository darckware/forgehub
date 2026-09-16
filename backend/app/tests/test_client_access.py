"""Scoped client read credentials and external projections."""
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

pytest_plugins = ["app.tests.test_client_reports"]


@pytest.mark.asyncio
async def test_read_credential_scope_draft_visibility_revocation_and_safe_projection(report_world):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        issued = await http.post(f"/api/v1/clients/{report_world['a']}/read-credentials", json={}, headers=report_world["admin_headers"])
        assert issued.status_code == 201, issued.text
        body = issued.json()
        token = body["token"]
        credential_id = body["credential"]["id"]
        assert token.startswith("clr_") and "token_hash" not in issued.text
        listed_credentials = await http.get(f"/api/v1/clients/{report_world['a']}/read-credentials", headers=report_world["admin_headers"])
        assert listed_credentials.status_code == 200
        assert "token_hash" not in listed_credentials.text and "token" not in listed_credentials.text

        draft = await http.post(f"/api/v1/clients/{report_world['a']}/reports", json={"period_start": "2026-08-01", "period_end": "2026-08-31"}, headers=report_world["admin_headers"])
        draft_id = draft.json()["id"]
        client_headers = {"Authorization": f"Bearer {token}"}
        reports = await http.get(f"/api/v1/client-access/clients/{report_world['a']}/reports", headers=client_headers)
        assert reports.status_code == 200 and reports.json() == []
        hidden = await http.get(f"/api/v1/client-access/clients/{report_world['a']}/reports/{draft_id}/download", headers=client_headers)
        assert hidden.status_code == 404
        assert (await http.get(f"/api/v1/client-access/clients/{report_world['b']}/reports", headers=client_headers)).status_code == 404
        assert (await http.get(f"/api/v1/client-access/clients/{report_world['b']}/reports/{draft_id}/download", headers=client_headers)).status_code == 404

        await http.patch(f"/api/v1/client-reports/{draft_id}/review", json={"reviewed": True}, headers=report_world["admin_headers"])
        visible = await http.get(f"/api/v1/client-access/clients/{report_world['a']}/reports", headers=client_headers)
        assert visible.status_code == 200 and visible.json()[0]["id"] == draft_id
        issues = await http.get(f"/api/v1/client-access/clients/{report_world['a']}/irregularities", headers=client_headers)
        assert issues.status_code == 200 and issues.json()[0]["hostname"]
        assert "private note" not in issues.text and "device_token" not in issues.text
        assert (await http.get(f"/api/v1/clients/{report_world['a']}/reports", headers=client_headers)).status_code == 401

        await http.patch(f"/api/v1/client-reports/{draft_id}/review", json={"reviewed": False}, headers=report_world["admin_headers"])
        assert (await http.get(f"/api/v1/client-access/clients/{report_world['a']}/reports/{draft_id}/download", headers=client_headers)).status_code == 404
        revoked = await http.delete(f"/api/v1/clients/{report_world['a']}/read-credentials/{credential_id}", headers=report_world["admin_headers"])
        assert revoked.status_code == 204
        assert (await http.get(f"/api/v1/client-access/clients/{report_world['a']}/reports", headers=client_headers)).status_code == 401


@pytest.mark.asyncio
async def test_expired_invalid_and_pagination_credentials(report_world):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        assert (await http.post(f"/api/v1/clients/{report_world['a']}/read-credentials", json={"expires_at": past}, headers=report_world["admin_headers"])).status_code == 422
        path = f"/api/v1/client-access/clients/{report_world['a']}/reports"
        assert (await http.get(path, headers={"Authorization": "Bearer clr_invalid"})).status_code == 401
        assert (await http.get(path, headers=report_world["admin_headers"])).status_code == 401
        assert (await http.get(path, params={"limit": 0}, headers={"Authorization": "Bearer clr_invalid"})).status_code in {401, 422}


@pytest.mark.asyncio
async def test_monthly_poll_isolates_client_failure(report_world, monkeypatch):
    from app.core import client_reports
    from app.db.base import AsyncSessionLocal

    original = client_reports.generate_client_report

    async def one_failure(db, client_id, *args, **kwargs):
        if client_id == report_world["a"]:
            raise RuntimeError("isolated fixture failure")
        if client_id == report_world["b"]:
            return await original(db, client_id, *args, **kwargs)
        raise RuntimeError("unrelated fixture client")

    monkeypatch.setattr(client_reports, "generate_client_report", one_failure)
    count = await client_reports.run_monthly_report_pass(AsyncSessionLocal, datetime(2026, 9, 15, tzinfo=timezone.utc))
    assert count == 1

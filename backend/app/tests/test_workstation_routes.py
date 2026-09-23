"""Workstation CRUD + token lifecycle route tests -- real DB, no mocking."""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.routes.workstation import hash_device_token
from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.client import Client
from app.db.models.user import User
from app.main import app


async def _admin_token() -> str:
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        result = await db.execute(select(User).where(User.is_admin.is_(True), User.is_active.is_(True)).order_by(User.username).limit(1))
        admin = result.scalar_one_or_none()
        assert admin is not None
        return create_access_token(admin.username)


async def _make_client() -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        client = Client(name=f"Test Client {uuid.uuid4()}")
        db.add(client)
        await db.commit()
        await db.refresh(client)
        return client.id


@pytest.mark.asyncio
async def test_create_workstation_issues_token_once_then_reissue_revoke():
    token = await _admin_token()
    headers = {"Authorization": f"Bearer {token}"}
    client_id = await _make_client()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        create_resp = await http.post(
            "/api/v1/workstations",
            json={"client_id": str(client_id), "os_kind": "linux"},
            headers=headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        body = create_resp.json()
        raw_token = body["device_token"]
        workstation_id = body["workstation"]["id"]
        assert raw_token.startswith("nxw_")

        get_resp = await http.get(f"/api/v1/workstations/{workstation_id}", headers=headers)
        assert get_resp.status_code == 200
        assert "device_token" not in get_resp.json()

        reissue_resp = await http.post(
            f"/api/v1/workstations/{workstation_id}/token:reissue", headers=headers
        )
        assert reissue_resp.status_code == 200
        new_raw_token = reissue_resp.json()["device_token"]
        assert new_raw_token != raw_token
        assert hash_device_token(new_raw_token) != hash_device_token(raw_token)

        revoke_resp = await http.post(
            f"/api/v1/workstations/{workstation_id}/token:revoke", headers=headers
        )
        assert revoke_resp.status_code == 200
        assert revoke_resp.json()["device_token_revoked_at"] is not None

        delete_resp = await http.delete(f"/api/v1/workstations/{workstation_id}", headers=headers)
        assert delete_resp.status_code == 204

    async with AsyncSessionLocal() as db:
        client = await db.get(Client, client_id)
        await db.delete(client)
        await db.commit()


@pytest.mark.asyncio
async def test_create_workstation_rejects_invalid_os_kind():
    token = await _admin_token()
    headers = {"Authorization": f"Bearer {token}"}
    client_id = await _make_client()

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            resp = await http.post(
                "/api/v1/workstations",
                json={"client_id": str(client_id), "os_kind": "invalid"},
                headers=headers,
            )
            assert resp.status_code == 400, resp.text
    finally:
        async with AsyncSessionLocal() as db:
            client = await db.get(Client, client_id)
            await db.delete(client)
            await db.commit()

"""Client CRUD route tests -- real DB, real ASGI app, no mocking."""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.user import User
from app.main import app


async def _admin_token() -> str:
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        result = await db.execute(select(User).where(User.is_admin.is_(True)).limit(1))
        admin = result.scalar_one_or_none()
        assert admin is not None, "expected at least one admin user to exist for this test"
        return create_access_token(admin.username)


@pytest.mark.asyncio
async def test_create_get_list_delete_client():
    token = await _admin_token()
    headers = {"Authorization": f"Bearer {token}"}
    name = f"Test Client {uuid.uuid4()}"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_resp = await client.post("/api/v1/clients", json={"name": name}, headers=headers)
        assert create_resp.status_code == 201, create_resp.text
        client_id = create_resp.json()["id"]

        try:
            get_resp = await client.get(f"/api/v1/clients/{client_id}", headers=headers)
            assert get_resp.status_code == 200
            assert get_resp.json()["name"] == name

            list_resp = await client.get("/api/v1/clients", headers=headers)
            assert list_resp.status_code == 200
            assert any(c["id"] == client_id for c in list_resp.json())
        finally:
            delete_resp = await client.delete(f"/api/v1/clients/{client_id}", headers=headers)
            assert delete_resp.status_code == 204

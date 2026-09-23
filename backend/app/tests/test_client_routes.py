"""Client CRUD route tests -- real DB, real ASGI app, no mocking."""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core import headscale_client
from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.client import Client
from app.db.models.user import User
from app.main import app


@pytest.fixture(autouse=True)
def fake_headscale_policy_push(monkeypatch):
    calls = []

    async def fake_rebuild(db):
        calls.append(db)

    monkeypatch.setattr(headscale_client, "rebuild_and_push_policy", fake_rebuild)
    return calls


async def _admin_token() -> str:
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        result = await db.execute(select(User).where(User.is_admin.is_(True), User.is_active.is_(True)).order_by(User.username).limit(1))
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


@pytest.mark.asyncio
async def test_create_client_rejects_invalid_support_plan():
    token = await _admin_token()
    headers = {"Authorization": f"Bearer {token}"}
    name = f"Test Client {uuid.uuid4()}"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/clients",
            json={"name": name, "support_plan": "invalid"},
            headers=headers,
        )
        assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_update_client_rejects_invalid_support_plan():
    token = await _admin_token()
    headers = {"Authorization": f"Bearer {token}"}
    name = f"Test Client {uuid.uuid4()}"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_resp = await client.post("/api/v1/clients", json={"name": name}, headers=headers)
        assert create_resp.status_code == 201, create_resp.text
        client_id = create_resp.json()["id"]

        try:
            update_resp = await client.put(
                f"/api/v1/clients/{client_id}",
                json={"support_plan": "invalid"},
                headers=headers,
            )
            assert update_resp.status_code == 400, update_resp.text
        finally:
            delete_resp = await client.delete(f"/api/v1/clients/{client_id}", headers=headers)
            assert delete_resp.status_code == 204


@pytest.mark.asyncio
async def test_update_client_rejects_explicit_null_name():
    token = await _admin_token()
    headers = {"Authorization": f"Bearer {token}"}
    name = f"Test Client {uuid.uuid4()}"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_resp = await client.post("/api/v1/clients", json={"name": name}, headers=headers)
        assert create_resp.status_code == 201, create_resp.text
        client_id = create_resp.json()["id"]

        try:
            update_resp = await client.put(
                f"/api/v1/clients/{client_id}",
                json={"name": None},
                headers=headers,
            )
            assert update_resp.status_code == 400, update_resp.text
        finally:
            delete_resp = await client.delete(f"/api/v1/clients/{client_id}", headers=headers)
            assert delete_resp.status_code == 204


@pytest.mark.asyncio
async def test_client_lifecycle_keeps_headscale_tag_and_policy_in_sync(fake_headscale_policy_push):
    token = await _admin_token()
    headers = {"Authorization": f"Bearer {token}"}
    suffix = uuid.uuid4().hex[:8]
    original_name = f"Tagged Client {suffix}"
    updated_name = f"Renamed Client {suffix}"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_resp = await client.post("/api/v1/clients", json={"name": original_name}, headers=headers)
        assert create_resp.status_code == 201, create_resp.text
        client_id = create_resp.json()["id"]
        assert create_resp.json()["headscale_tag"] == f"tag:cliente-tagged-client-{suffix}"
        assert len(fake_headscale_policy_push) == 1

        update_resp = await client.put(
            f"/api/v1/clients/{client_id}",
            json={"name": updated_name},
            headers=headers,
        )
        assert update_resp.status_code == 200, update_resp.text
        assert update_resp.json()["headscale_tag"] == f"tag:cliente-renamed-client-{suffix}"
        assert len(fake_headscale_policy_push) == 2

        delete_resp = await client.delete(f"/api/v1/clients/{client_id}", headers=headers)
        assert delete_resp.status_code == 204
        assert len(fake_headscale_policy_push) == 3


@pytest.mark.asyncio
async def test_create_client_rolls_back_when_policy_cannot_be_published(monkeypatch):
    from fastapi import HTTPException

    async def fail_rebuild(db):
        raise HTTPException(502, "bridge unavailable")

    monkeypatch.setattr(headscale_client, "rebuild_and_push_policy", fail_rebuild)
    token = await _admin_token()
    name = f"Unpublished Client {uuid.uuid4()}"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/clients",
            json={"name": name},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 502
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(Client).where(Client.name == name))).scalar_one_or_none() is None

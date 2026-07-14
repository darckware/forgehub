"""Workspace browser proxy contracts."""

import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.db.models.product import Product, ProductVersion


@pytest_asyncio.fixture
async def client(auth_headers):
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=auth_headers) as ac:
        yield ac


def _state(url: str = "http://127.0.0.1:5173/") -> dict:
    return {
        "running": True,
        "cdp_url": "http://127.0.0.1:9223",
        "url": url,
        "title": "ForgeHub",
        "ready_state": "complete",
        "viewport_width": 1440,
        "viewport_height": 757,
        "image_base64": "aW1hZ2U=",
        "captured_at": "2026-07-13T16:00:00",
    }


class FakeResponse:
    status_code = 200
    text = ""

    def __init__(self, payload: dict):
        self._payload = payload

    def json(self):
        return self._payload


class FakeBridgeClient:
    calls: list[tuple[str, str, dict | None]] = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def request(self, method, url, headers=None, json=None):
        self.calls.append((method, url, json))
        return FakeResponse(_state())

    async def post(self, url, headers=None, json=None):
        self.calls.append(("POST", url, json))
        return FakeResponse({
            "status": "passed",
            "steps": [{"index": 1, "action": "assert_text", "status": "passed", "outcome": "asserted"}],
            "browser": _state(json["start_url"]),
        })


async def test_browser_state_proxies_live_cdp_metadata(client: AsyncClient, monkeypatch):
    from app.api.routes import workspace_browser

    FakeBridgeClient.calls = []
    monkeypatch.setattr(workspace_browser.httpx, "AsyncClient", FakeBridgeClient)

    response = await client.get("/api/v1/workspace-browser/state")

    assert response.status_code == 200, response.text
    assert response.json()["viewport_height"] == 757
    assert FakeBridgeClient.calls[0][1].endswith("/v1/workspace-browser/state")


async def test_login_credential_is_injected_server_side(client: AsyncClient, monkeypatch):
    from app.api.routes import workspace_browser

    FakeBridgeClient.calls = []
    monkeypatch.setattr(workspace_browser.httpx, "AsyncClient", FakeBridgeClient)

    response = await client.post(
        "/api/v1/workspace-browser/login-forgehub",
        json={"url": "http://127.0.0.1:5173/login"},
    )

    assert response.status_code == 200, response.text
    payload = FakeBridgeClient.calls[0][2]
    assert payload == {
        "url": "http://127.0.0.1:5173/login",
        "username": settings.DEV_USER_USERNAME,
        "password": settings.DEV_USER_PASSWORD,
    }


async def test_product_web_automation_routine_crud_and_run(client: AsyncClient, monkeypatch):
    from app.api.routes import workspace_browser

    product_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        product = Product(
            id=product_id,
            name=f"Automation Product {product_id}",
            application_url="http://127.0.0.1:5173/login",
        )
        db.add(product)
        db.add(ProductVersion(product=product, version="0.1.0", status="planned"))
        await db.commit()

    FakeBridgeClient.calls = []
    monkeypatch.setattr(workspace_browser.httpx, "AsyncClient", FakeBridgeClient)
    try:
        created = await client.post("/api/v1/workspace-browser/routines", json={
            "product_id": str(product_id),
            "name": "Login smoke test",
            "steps": [
                {"action": "type", "selector": "#username", "value": "admin"},
                {"action": "assert_text", "value": "Welcome back"},
            ],
        })
        assert created.status_code == 201, created.text
        routine_id = created.json()["id"]

        listed = await client.get(f"/api/v1/workspace-browser/routines?product_id={product_id}")
        assert listed.status_code == 200
        assert [item["name"] for item in listed.json()] == ["Login smoke test"]

        run = await client.post(f"/api/v1/workspace-browser/routines/{routine_id}:run")
        assert run.status_code == 200, run.text
        assert run.json()["status"] == "passed"
        assert FakeBridgeClient.calls[-1][2]["start_url"] == "http://127.0.0.1:5173/login"
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Product).where(Product.id == product_id))
            await db.commit()

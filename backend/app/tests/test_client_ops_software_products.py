"""Tests for Darckware commercial software products linkage in client_ops domain."""
from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core import darckware_client
from app.core.config import settings
from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.governance import AuditEvent
from app.db.models.product import Product, ProductVersion
from app.main import app

OFFER_1_ID = "11111111-0000-0000-0000-000000000001"
OFFER_2_ID = "11111111-0000-0000-0000-000000000002"


class FakeDarckwareSoftwareProducts:
    def __init__(self) -> None:
        self.offers: dict[str, dict[str, Any]] = {
            OFFER_1_ID: {
                "id": OFFER_1_ID,
                "name": "Oferta Starter",
                "slug": "starter",
                "category": "saas",
                "description": "Oferta inicial",
                "is_active": True,
                "base_monthly_price": 100.0,
                "available_modules": ["base"],
                "forgehub_product_id": None,
            },
            OFFER_2_ID: {
                "id": OFFER_2_ID,
                "name": "Oferta Pro",
                "slug": "pro",
                "category": "saas",
                "description": "Oferta profissional",
                "is_active": True,
                "base_monthly_price": 250.0,
                "available_modules": ["base", "pro"],
                "forgehub_product_id": None,
            },
        }
        self.down = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("Connection refused", request=request)

        path = request.url.path
        prefix = "/api/internal/agent/software-products"

        if path == prefix and request.method == "GET":
            return httpx.Response(200, json=list(self.offers.values()))

        if path.startswith(prefix) and path.endswith("/forgehub-link") and request.method == "PUT":
            offer_id = path.removeprefix(f"{prefix}/").removesuffix("/forgehub-link")
            offer = self.offers.get(offer_id)
            if offer is None:
                return httpx.Response(404, json={"detail": "software product not found"})
            import json
            body = json.loads(request.content.decode("utf-8")) if request.content else {}
            link_id = body.get("forgehub_product_id")
            offer["forgehub_product_id"] = str(link_id) if link_id is not None else None
            return httpx.Response(200, json=dict(offer))

        return httpx.Response(404, json={"detail": "not found"})


@pytest.fixture
def fake_darckware(monkeypatch):
    fake = FakeDarckwareSoftwareProducts()
    monkeypatch.setattr(darckware_client, "transport", httpx.MockTransport(fake.handler))
    monkeypatch.setattr(settings, "DARCKWARE_API_URL", "http://darckware.test")
    monkeypatch.setattr(settings, "DARCKWARE_AGENT_TOKEN", "test-agent-token")
    monkeypatch.setattr(settings, "DARCKWARE_APPROVER_TOKEN", "test-approver-token")
    return fake


@pytest_asyncio.fixture
async def test_product():
    product_id = uuid.uuid4()
    version_id = uuid.uuid4()
    product_name = f"Test System {uuid.uuid4().hex[:6]}"

    async with AsyncSessionLocal() as db:
        prod = Product(
            id=product_id,
            name=product_name,
            description="Test system description",
            status="active",
        )
        ver = ProductVersion(
            id=version_id,
            product_id=product_id,
            version="1.0.0",
            status="planned",
        )
        db.add(prod)
        db.add(ver)
        await db.commit()

    yield {"id": product_id, "name": product_name, "version_id": version_id}

    async with AsyncSessionLocal() as db:
        await db.execute(delete(ProductVersion).where(ProductVersion.product_id == product_id))
        await db.execute(delete(Product).where(Product.id == product_id))
        await db.execute(
            delete(AuditEvent).where(
                AuditEvent.entity_type == "darckware_software_product",
                AuditEvent.entity_id.in_([uuid.UUID(OFFER_1_ID), uuid.UUID(OFFER_2_ID)]),
            )
        )
        await db.commit()


@pytest_asyncio.fixture
async def client(admin_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=admin_headers) as ac:
        yield ac


@pytest.mark.asyncio
async def test_list_software_products_with_resolved_name(client, fake_darckware, test_product):
    # Set offer 1 to point to test_product
    fake_darckware.offers[OFFER_1_ID]["forgehub_product_id"] = str(test_product["id"])

    resp = await client.get("/api/v1/client-ops/software-products")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data) == 2

    by_id = {item["id"]: item for item in data}
    assert by_id[OFFER_1_ID]["forgehub_product_id"] == str(test_product["id"])
    assert by_id[OFFER_1_ID]["forgehub_product_name"] == test_product["name"]

    assert by_id[OFFER_2_ID]["forgehub_product_id"] is None
    assert by_id[OFFER_2_ID]["forgehub_product_name"] is None


@pytest.mark.asyncio
async def test_link_and_unlink_software_product(client, fake_darckware, test_product):
    # Link offer 2 to test_product
    resp = await client.put(
        f"/api/v1/client-ops/software-products/{OFFER_2_ID}/forgehub-link",
        json={"forgehub_product_id": str(test_product["id"])},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["forgehub_product_id"] == str(test_product["id"])
    assert fake_darckware.offers[OFFER_2_ID]["forgehub_product_id"] == str(test_product["id"])

    # Verify AuditEvent was created
    async with AsyncSessionLocal() as db:
        events = (
            await db.execute(
                select(AuditEvent).where(
                    AuditEvent.entity_type == "darckware_software_product",
                    AuditEvent.entity_id == uuid.UUID(OFFER_2_ID),
                ).order_by(AuditEvent.created_at)
            )
        ).scalars().all()
        assert len(events) >= 1
        assert events[-1].event_type == "forgehub_link_updated"
        assert events[-1].payload == {"forgehub_product_id": str(test_product["id"])}

    # Unlink offer 2
    resp_unlink = await client.put(
        f"/api/v1/client-ops/software-products/{OFFER_2_ID}/forgehub-link",
        json={"forgehub_product_id": None},
    )
    assert resp_unlink.status_code == 200, resp_unlink.text
    assert resp_unlink.json()["forgehub_product_id"] is None
    assert fake_darckware.offers[OFFER_2_ID]["forgehub_product_id"] is None

    # Verify another AuditEvent
    async with AsyncSessionLocal() as db:
        events = (
            await db.execute(
                select(AuditEvent).where(
                    AuditEvent.entity_type == "darckware_software_product",
                    AuditEvent.entity_id == uuid.UUID(OFFER_2_ID),
                ).order_by(AuditEvent.created_at)
            )
        ).scalars().all()
        assert len(events) >= 2
        assert events[-1].payload == {"forgehub_product_id": None}


@pytest.mark.asyncio
async def test_link_nonexistent_product_returns_422(client, fake_darckware):
    nonexistent_id = uuid.uuid4()
    resp = await client.put(
        f"/api/v1/client-ops/software-products/{OFFER_1_ID}/forgehub-link",
        json={"forgehub_product_id": str(nonexistent_id)},
    )
    assert resp.status_code == 422, resp.text
    assert "product_not_found" in resp.text or "not found" in resp.text


@pytest.mark.asyncio
async def test_non_admin_returns_403(fake_darckware):
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {create_access_token(f'operator-{uuid.uuid4().hex}')}"}
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as ac:
        r_get = await ac.get("/api/v1/client-ops/software-products")
        assert r_get.status_code in (401, 403)

        r_put = await ac.put(
            f"/api/v1/client-ops/software-products/{OFFER_1_ID}/forgehub-link",
            json={"forgehub_product_id": None},
        )
        assert r_put.status_code in (401, 403)


@pytest.mark.asyncio
async def test_darckware_down_returns_502(client, fake_darckware):
    fake_darckware.down = True
    resp = await client.get("/api/v1/client-ops/software-products")
    assert resp.status_code == 502, resp.text

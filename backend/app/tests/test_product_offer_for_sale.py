"""Offering a product for sale: only marked products reach Darckware."""
from __future__ import annotations

import json
import uuid

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core import darckware_client
from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.db.models.governance import AuditEvent
from app.db.models.product import Product
from app.main import app


class FakeCatalog:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.fail = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.fail:
            return httpx.Response(500, json={"detail": "fora do ar"})
        body = json.loads(request.content) if request.content else {}
        self.calls.append((request.url.path, body))
        assert request.headers["authorization"] == "Bearer test-approver-token"
        if request.url.path.endswith("/withdraw"):
            return httpx.Response(200, json={"withdrawn": 1})
        return httpx.Response(201, json={"id": str(uuid.uuid4()), "is_active": False, **body})


@pytest.fixture
def catalog(monkeypatch):
    fake = FakeCatalog()
    monkeypatch.setattr(darckware_client, "transport", httpx.MockTransport(fake.handler))
    monkeypatch.setattr(settings, "DARCKWARE_API_URL", "http://darckware.test")
    monkeypatch.setattr(settings, "DARCKWARE_APPROVER_TOKEN", "test-approver-token")
    return fake


@pytest_asyncio.fixture
async def client(admin_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=admin_headers) as ac:
        yield ac


@pytest_asyncio.fixture
async def make_product():
    ids: list[uuid.UUID] = []

    async def build(**fields) -> uuid.UUID:
        product_id = uuid.uuid4()
        ids.append(product_id)
        async with AsyncSessionLocal() as db:
            db.add(Product(id=product_id, name=f"Venda {product_id.hex[:8]}", status="active", **fields))
            await db.commit()
        return product_id

    yield build
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AuditEvent).where(AuditEvent.entity_type == "product", AuditEvent.entity_id.in_(ids)))
        await db.execute(delete(Product).where(Product.id.in_(ids)))
        await db.commit()


async def _product(product_id: uuid.UUID) -> Product:
    async with AsyncSessionLocal() as db:
        return await db.get(Product, product_id)


@pytest.mark.asyncio
async def test_marked_product_goes_to_catalog_and_is_audited(client, catalog, make_product):
    product_id = await make_product(sellable=True)
    response = await client.post(f"/api/v1/client-ops/products/{product_id}:offer-for-sale")
    assert response.status_code == 200, response.text
    path, body = catalog.calls[0]
    assert path.endswith("/api/internal/approver/software-products/from-forgehub")
    assert body["forgehub_product_id"] == str(product_id)
    assert (await _product(product_id)).offered_for_sale_at is not None
    async with AsyncSessionLocal() as db:
        events = (await db.execute(select(AuditEvent).where(AuditEvent.entity_id == product_id))).scalars().all()
    assert [event.event_type for event in events] == ["product_offered_for_sale"]


@pytest.mark.asyncio
async def test_unmarked_or_client_product_never_reaches_darckware(client, catalog, make_product):
    for fields in ({}, {"darckware_client_id": uuid.uuid4()}):
        product_id = await make_product(**fields)
        response = await client.post(f"/api/v1/client-ops/products/{product_id}:offer-for-sale")
        assert response.status_code == 409, response.text
    assert catalog.calls == []


@pytest.mark.asyncio
async def test_withdraw_clears_the_offer(client, catalog, make_product):
    product_id = await make_product(sellable=True)
    await client.post(f"/api/v1/client-ops/products/{product_id}:offer-for-sale")
    response = await client.post(f"/api/v1/client-ops/products/{product_id}:withdraw-from-sale")
    assert response.status_code == 200, response.text
    assert catalog.calls[-1][0].endswith(f"/from-forgehub/{product_id}/withdraw")
    assert (await _product(product_id)).offered_for_sale_at is None


@pytest.mark.asyncio
async def test_unmarking_withdraws_from_darckware(client, catalog, make_product):
    product_id = await make_product(sellable=True)
    await client.post(f"/api/v1/client-ops/products/{product_id}:offer-for-sale")
    response = await client.put(f"/api/v1/products/{product_id}", json={"sellable": False})
    assert response.status_code == 200, response.text
    assert catalog.calls[-1][0].endswith("/withdraw")
    product = await _product(product_id)
    assert product.sellable is False and product.offered_for_sale_at is None


@pytest.mark.asyncio
async def test_unmarking_changes_nothing_when_darckware_fails(client, catalog, make_product):
    product_id = await make_product(sellable=True)
    await client.post(f"/api/v1/client-ops/products/{product_id}:offer-for-sale")
    catalog.fail = True
    response = await client.put(f"/api/v1/products/{product_id}", json={"sellable": False})
    assert response.status_code == 502, response.text
    product = await _product(product_id)
    assert product.sellable is True and product.offered_for_sale_at is not None


@pytest.mark.asyncio
async def test_failed_offer_records_nothing(client, catalog, make_product):
    product_id = await make_product(sellable=True)
    catalog.fail = True
    response = await client.post(f"/api/v1/client-ops/products/{product_id}:offer-for-sale")
    assert response.status_code == 502, response.text
    assert (await _product(product_id)).offered_for_sale_at is None

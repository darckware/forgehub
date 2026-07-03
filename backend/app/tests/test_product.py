"""Tests for the Product domain (products, product_modules,
product_versions, releases).

Uses httpx.AsyncClient with ASGITransport against the real FastAPI app and
the real async DB session/engine from app.db.base. Each test creates its
own rows and explicitly deletes them in a `finally` block so the shared
company_postgres database is left clean regardless of test outcome.

NOTE: these tests require the `company.products` / `company.product_versions`
/ `company.product_modules` / `company.releases` tables to already exist
(created via the project's Alembic migration once the wiring step populates
app/db/models/__init__.py and a migration is generated/applied). They are
not runnable in total isolation before that migration exists -- this is
expected and matches the foundation's stated migration workflow.
"""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.db.base import AsyncSessionLocal
from app.db.models.product import Product, ProductVersion
from app.main import app


@pytest_asyncio.fixture
async def client(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=auth_headers) as ac:
        yield ac


async def _cleanup_product(product_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(delete(ProductVersion).where(ProductVersion.product_id == product_id))
        await session.execute(delete(Product).where(Product.id == product_id))
        await session.commit()


@pytest.mark.asyncio
async def test_create_get_list_product(client: AsyncClient):
    unique_name = f"Test Product {uuid.uuid4()}"
    create_resp = await client.post(
        "/api/v1/products",
        json={"name": unique_name, "description": "A product created in tests"},
    )
    try:
        assert create_resp.status_code == 201, create_resp.text
        body = create_resp.json()
        assert body["name"] == unique_name
        # Business rule 6.1.3: a product is created with at least one version.
        assert len(body["versions"]) == 1
        assert body["versions"][0]["version"] == "0.1.0"
        assert body["versions"][0]["status"] == "planned"

        product_id = body["id"]

        get_resp = await client.get(f"/api/v1/products/{product_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == unique_name

        list_resp = await client.get("/api/v1/products")
        assert list_resp.status_code == 200
        names = [p["name"] for p in list_resp.json()]
        assert unique_name in names
    finally:
        await _cleanup_product(uuid.UUID(create_resp.json()["id"]))


@pytest.mark.asyncio
async def test_create_product_duplicate_name_returns_409(client: AsyncClient):
    unique_name = f"Dup Product {uuid.uuid4()}"
    first = await client.post("/api/v1/products", json={"name": unique_name})
    assert first.status_code == 201
    product_id = first.json()["id"]

    try:
        second = await client.post("/api/v1/products", json={"name": unique_name})
        assert second.status_code == 409
    finally:
        await _cleanup_product(uuid.UUID(product_id))


@pytest.mark.asyncio
async def test_published_version_cannot_be_mutated(client: AsyncClient):
    """Business rule 6.1.4: published versions cannot be mutated directly."""
    unique_name = f"Published Product {uuid.uuid4()}"
    create_resp = await client.post("/api/v1/products", json={"name": unique_name})
    assert create_resp.status_code == 201
    body = create_resp.json()
    product_id = body["id"]
    version_id = body["versions"][0]["id"]

    try:
        # First transition the version to "published" -- allowed, since the
        # rule only blocks mutating a version that is *already* published.
        publish_resp = await client.put(
            f"/api/v1/products/versions/{version_id}", json={"status": "published"}
        )
        assert publish_resp.status_code == 200
        assert publish_resp.json()["status"] == "published"

        # Now any further mutation must be rejected with a 4xx.
        mutate_resp = await client.put(
            f"/api/v1/products/versions/{version_id}", json={"version": "0.2.0"}
        )
        assert mutate_resp.status_code == 422
    finally:
        await _cleanup_product(uuid.UUID(product_id))


@pytest.mark.asyncio
async def test_cannot_delete_only_remaining_version(client: AsyncClient):
    """Business rule 6.1.3: every product must have at least one version."""
    unique_name = f"Single Version Product {uuid.uuid4()}"
    create_resp = await client.post("/api/v1/products", json={"name": unique_name})
    assert create_resp.status_code == 201
    body = create_resp.json()
    product_id = body["id"]
    version_id = body["versions"][0]["id"]

    try:
        delete_resp = await client.delete(f"/api/v1/products/versions/{version_id}")
        assert delete_resp.status_code == 422
    finally:
        await _cleanup_product(uuid.UUID(product_id))


@pytest.mark.asyncio
async def test_product_module_crud(client: AsyncClient):
    unique_name = f"Modular Product {uuid.uuid4()}"
    create_resp = await client.post("/api/v1/products", json={"name": unique_name})
    assert create_resp.status_code == 201
    product_id = create_resp.json()["id"]

    try:
        module_resp = await client.post(
            f"/api/v1/products/{product_id}/modules",
            json={"name": "Core Module", "description": "Primary module"},
        )
        assert module_resp.status_code == 201
        assert module_resp.json()["name"] == "Core Module"

        list_resp = await client.get(f"/api/v1/products/{product_id}/modules")
        assert list_resp.status_code == 200
        assert len(list_resp.json()) == 1
    finally:
        await _cleanup_product(uuid.UUID(product_id))

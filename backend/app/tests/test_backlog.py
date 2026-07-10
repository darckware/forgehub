"""Tests for the Backlog domain (planning_items, feature_requests,
bug_reports, version_scope_items, triage_decisions).

DB strategy: this suite runs against the real, shared `company_postgres`
database used by every domain agent's tests, so it must be careful never
to assume exclusive ownership of any table -- other domain agents may be
creating/using `company.projects` and `company.product_versions`
concurrently. Specifically:
- Table creation uses `checkfirst=True` (the default) and only ever
  *creates* tables, never drops them -- so this module is safe to import
  whether the real `projects`/`product_versions` tables already exist
  (created by another domain agent) or not (in which case minimal stub
  tables with just an `id` column are created here, sufficient to satisfy
  this domain's string FKs; a later domain migration may legitimately
  add more columns to those same tables without conflict since we never
  redefine columns that already exist).
- Each test cleans up only the specific rows it created (by id), never a
  blanket `DELETE FROM <table>` / `DROP TABLE`, so concurrently-running
  tests from other domains are not affected.
"""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db.base import AsyncSessionLocal, Base, engine
from app.db.models.backlog import (  # noqa: F401  (ensures tables register on Base.metadata)
    BugReport,
    FeatureRequest,
    PlanningItem,
    TriageDecision,
    VersionScopeItem,
)
from app.db.models.product import Product, ProductVersion
from app.db.models.project import Project
from app.main import app
from app.api.routes import backlog as backlog_routes

# Make sure this domain's router is mounted even though the central wiring
# step (main.py) hasn't added it yet -- keeps this test self-contained.
app.include_router(backlog_routes.router)


# NOTE: this module previously declared local stub `Table()` objects for the
# other-domain FK targets (`projects`, `product_versions`) to satisfy
# string-FK resolution before the unified Alembic migration existed. The
# real ORM models for those tables now exist (Project and Product domains)
# and are migration-managed, so those stubs were removed -- a duplicate
# `Table(..., extend_existing=True)` registration for an already-mapped
# table corrupts SQLAlchemy's mapper configuration for any other test
# module that also touches that table in the same test session. Where this
# module needs a real `product_versions` row (the triage/scope test below),
# it now creates one through the real Product/ProductVersion models.

_ALL_TEST_TABLES = [
    PlanningItem.__table__,
    FeatureRequest.__table__,
    BugReport.__table__,
    VersionScopeItem.__table__,
    TriageDecision.__table__,
]


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _setup_schema():
    # checkfirst=True (default): only creates tables that don't exist yet.
    # Never drops anything -- this DB is shared with other domain agents'
    # concurrent test runs.
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn, tables=_ALL_TEST_TABLES, checkfirst=True
            )
        )
    yield


@pytest_asyncio.fixture
async def client(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=auth_headers) as ac:
        yield ac


@pytest_asyncio.fixture
async def created_ids():
    """Tracks ids of rows created during a test, per table, so the test
    can delete exactly those rows on teardown instead of truncating
    shared tables."""
    ids: dict[str, list[uuid.UUID]] = {
        "triage_decisions": [],
        "version_scope_items": [],
        "bug_reports": [],
        "feature_requests": [],
        "planning_items": [],
        "product_versions": [],
        "products": [],
        "projects": [],
    }
    yield ids
    async with engine.begin() as conn:
        for table in (
            "triage_decisions",
            "version_scope_items",
            "bug_reports",
            "feature_requests",
            "planning_items",
            "projects",
            "product_versions",
            "products",
        ):
            row_ids = ids.get(table) or []
            if row_ids:
                await conn.execute(
                    text(f"DELETE FROM company.{table} WHERE id = ANY(:ids)"),
                    {"ids": row_ids},
                )


@pytest_asyncio.fixture
async def project_id(created_ids):
    """A real Project (via a real Product -> ProductVersion chain), since
    PlanningItem.project_id is now required on create (core traceability
    invariant) -- see create_planning_item in app/api/routes/backlog.py."""
    async with AsyncSessionLocal() as session:
        product = Product(name=f"Backlog Test Product {uuid.uuid4()}")
        session.add(product)
        await session.flush()
        version = ProductVersion(product_id=product.id, version="0.1.0")
        session.add(version)
        await session.flush()
        project = Project(
            name=f"Backlog Test Project {uuid.uuid4()}", product_version_id=version.id
        )
        session.add(project)
        await session.commit()
        pid = project.id

    created_ids["projects"].append(pid)
    created_ids["product_versions"].append(version.id)
    created_ids["products"].append(product.id)
    yield pid


@pytest.mark.asyncio
async def test_create_get_list_planning_item(client: AsyncClient, created_ids, project_id):
    payload = {
        "title": "Add dark mode",
        "description": "Users want a dark theme",
        "item_type": "feature",
        "priority": "high",
        "project_id": str(project_id),
    }
    create_resp = await client.post("/api/v1/planning-items", json=payload)
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    assert created["title"] == payload["title"]
    assert created["status"] == "new"
    assert created["baselined"] is False
    item_id = created["id"]
    created_ids["planning_items"].append(item_id)

    get_resp = await client.get(f"/api/v1/planning-items/{item_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == item_id

    list_resp = await client.get("/api/v1/planning-items")
    assert list_resp.status_code == 200
    ids = [item["id"] for item in list_resp.json()]
    assert item_id in ids


@pytest.mark.asyncio
async def test_invalid_item_type_rejected(client: AsyncClient, project_id):
    payload = {
        "title": "Bad type",
        "item_type": "not_a_real_type",
        "project_id": str(project_id),
    }
    resp = await client.post("/api/v1/planning-items", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_missing_project_id_returns_422(client: AsyncClient):
    payload = {"title": "No project", "item_type": "feature"}
    resp = await client.post("/api/v1/planning-items", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_nonexistent_project_id_returns_400(client: AsyncClient):
    payload = {
        "title": "Bad project",
        "item_type": "feature",
        "project_id": str(uuid.uuid4()),
    }
    resp = await client.post("/api/v1/planning-items", json=payload)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_baselined_planning_item_cannot_be_mutated(
    client: AsyncClient, created_ids, project_id
):
    create_resp = await client.post(
        "/api/v1/planning-items",
        json={
            "title": "Baseline me",
            "item_type": "improvement",
            "project_id": str(project_id),
        },
    )
    item_id = create_resp.json()["id"]
    created_ids["planning_items"].append(item_id)

    # Simulate baseline approval directly (no public endpoint flips this --
    # that happens via the Project domain's baseline flow).
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE company.planning_items SET baselined = true WHERE id = :id"
            ),
            {"id": item_id},
        )

    update_resp = await client.put(
        f"/api/v1/planning-items/{item_id}", json={"title": "Changed"}
    )
    assert update_resp.status_code == 409

    delete_resp = await client.delete(f"/api/v1/planning-items/{item_id}")
    assert delete_resp.status_code == 409


@pytest.mark.asyncio
async def test_feature_request_convert_flow(client: AsyncClient, created_ids, project_id):
    fr_resp = await client.post(
        "/api/v1/feature-requests",
        json={
            "title": "Export to CSV",
            "description": "Allow exporting reports",
            "requested_by": "alice",
        },
    )
    assert fr_resp.status_code == 201
    fr_id = fr_resp.json()["id"]
    created_ids["feature_requests"].append(fr_id)

    convert_resp = await client.post(
        f"/api/v1/feature-requests/{fr_id}/convert",
        json={"priority": "high", "project_id": str(project_id)},
    )
    assert convert_resp.status_code == 200
    planning_item = convert_resp.json()
    assert planning_item["item_type"] == "feature"
    assert planning_item["priority"] == "high"
    created_ids["planning_items"].append(planning_item["id"])

    # Re-converting must fail.
    second_convert = await client.post(
        f"/api/v1/feature-requests/{fr_id}/convert",
        json={"project_id": str(project_id)},
    )
    assert second_convert.status_code == 409


@pytest.mark.asyncio
async def test_bug_report_severity_validation(client: AsyncClient):
    resp = await client.post(
        "/api/v1/bug-reports",
        json={"title": "Crash on save", "severity": "catastrophic"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_triage_decision_advances_status_and_scope_requires_triage(
    client: AsyncClient, created_ids, project_id
):
    item_resp = await client.post(
        "/api/v1/planning-items",
        json={
            "title": "Improve logging",
            "item_type": "improvement",
            "project_id": str(project_id),
        },
    )
    item_id = item_resp.json()["id"]
    created_ids["planning_items"].append(item_id)

    async with AsyncSessionLocal() as session:
        product = Product(name=f"Triage Test Product {uuid.uuid4()}")
        session.add(product)
        await session.flush()
        version = ProductVersion(product_id=product.id, version="0.1.0")
        session.add(version)
        await session.commit()
        version_id = str(version.id)
    created_ids["products"].append(product.id)
    created_ids["product_versions"].append(version_id)

    # Scoping before triage must fail (status still "new").
    scope_resp = await client.post(
        "/api/v1/version-scope-items",
        json={"planning_item_id": item_id, "product_version_id": version_id},
    )
    assert scope_resp.status_code == 409

    triage_resp = await client.post(
        "/api/v1/triage-decisions",
        json={
            "planning_item_id": item_id,
            "outcome": "accepted",
            "decided_by": "bob",
        },
    )
    assert triage_resp.status_code == 201
    created_ids["triage_decisions"].append(triage_resp.json()["id"])

    get_item = await client.get(f"/api/v1/planning-items/{item_id}")
    assert get_item.json()["status"] == "triaged"

    scope_resp_2 = await client.post(
        "/api/v1/version-scope-items",
        json={"planning_item_id": item_id, "product_version_id": version_id},
    )
    assert scope_resp_2.status_code == 201
    assert scope_resp_2.json()["product_version_id"] == version_id
    created_ids["version_scope_items"].append(scope_resp_2.json()["id"])

    # Duplicate scope into the same version must fail.
    scope_resp_3 = await client.post(
        "/api/v1/version-scope-items",
        json={"planning_item_id": item_id, "product_version_id": version_id},
    )
    assert scope_resp_3.status_code == 409

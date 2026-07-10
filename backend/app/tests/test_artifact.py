"""Tests for the Artifact domain (artifacts, artifact_versions).

Run against the real `company_postgres` async engine/session from
app.db.base. No migration has been generated yet for this domain (the
wiring step owns alembic/versions), so -- mirroring the pattern used by
the other domain test modules (see test_pipeline.py) -- this module
ensures its own tables exist via `Base.metadata.create_all(checkfirst=True)`
(a harmless no-op if another process/agent already created them with
the same definition) and registers its router on the shared `app`
instance for the lifetime of the test process if the wiring step
hasn't already mounted it.

Each test creates its own rows and explicitly deletes them in a
`finally` block so the shared database is left clean, per the
foundation's testing convention (no destructive transaction-rollback
trickery needed since we own row lifecycle explicitly).
"""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db.base import AsyncSessionLocal, Base, engine
from app.db.models.artifact import (  # noqa: F401  (registers tables on Base.metadata)
    Artifact,
    ArtifactVersion,
)
from app.api.routes import artifact as artifact_routes
from app.main import app

if not any(getattr(r, "path", "").startswith("/api/v1/artifacts") for r in app.routes):
    app.include_router(artifact_routes.router)

_OUR_TABLES = [Artifact.__table__, ArtifactVersion.__table__]


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _setup_schema():
    # checkfirst=True (the create_all default): only creates tables that
    # don't already exist. NOTE: if another domain's test/process already
    # created a partial/stub `artifacts` table (e.g. as an FK target) with
    # fewer columns than this model defines, create_all will skip it
    # (checkfirst sees the table exists) and this domain's columns will be
    # missing until the real Alembic migration runs in the wiring step --
    # that is an infra-ordering limitation of cross-domain string FKs, not
    # a bug in this module.
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(sync_conn, tables=_OUR_TABLES)
        )
    yield


@pytest_asyncio.fixture
async def client(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=auth_headers) as ac:
        yield ac


async def _cleanup_artifact(artifact_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as session:
        obj = await session.get(Artifact, artifact_id)
        if obj is not None:
            await session.delete(obj)
            await session.commit()


@pytest.mark.asyncio
async def test_create_get_list_artifact(client: AsyncClient):
    payload = {
        "name": "PRD - Foundation MVP",
        "artifact_type": "prd",
        "description": "Product requirements for the foundation MVP",
        "requires_approval": True,
    }
    created_id = None
    try:
        resp = await client.post("/api/v1/artifacts", json=payload)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        created_id = body["id"]
        assert body["name"] == payload["name"]
        assert body["artifact_type"] == "prd"
        assert body["status"] == "draft"
        assert body["versions"] == []

        resp_get = await client.get(f"/api/v1/artifacts/{created_id}")
        assert resp_get.status_code == 200
        assert resp_get.json()["id"] == created_id

        resp_list = await client.get("/api/v1/artifacts")
        assert resp_list.status_code == 200
        ids = [a["id"] for a in resp_list.json()]
        assert created_id in ids
    finally:
        if created_id:
            await _cleanup_artifact(uuid.UUID(created_id))


@pytest.mark.asyncio
async def test_create_artifact_with_initial_version_and_add_version(
    client: AsyncClient,
):
    payload = {
        "name": "SPEC - Foundation MVP",
        "artifact_type": "spec",
        "initial_version": {
            "location_uri": "https://repo/example/SPEC.md",
            "status": "draft",
        },
    }
    created_id = None
    try:
        resp = await client.post("/api/v1/artifacts", json=payload)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        created_id = body["id"]
        assert len(body["versions"]) == 1
        assert body["versions"][0]["version_number"] == 1

        resp_v2 = await client.post(
            f"/api/v1/artifacts/{created_id}/versions",
            json={"location_uri": "https://repo/example/SPEC_v2.md", "status": "final"},
        )
        assert resp_v2.status_code == 201, resp_v2.text
        v2 = resp_v2.json()
        assert v2["version_number"] == 2

        resp_versions = await client.get(f"/api/v1/artifacts/{created_id}/versions")
        assert resp_versions.status_code == 200
        numbers = sorted(v["version_number"] for v in resp_versions.json())
        assert numbers == [1, 2]
    finally:
        if created_id:
            await _cleanup_artifact(uuid.UUID(created_id))


@pytest.mark.asyncio
async def test_approve_without_final_version_is_rejected(client: AsyncClient):
    """Business rule (SPEC 6.2.8): an artifact cannot be approved unless
    it has at least one FINAL version. Approving with only a DRAFT
    version must return 4xx."""
    payload = {
        "name": "Test Report - regression suite",
        "artifact_type": "test_report",
        "requires_approval": True,
        "initial_version": {
            "location_uri": "https://repo/example/report-draft.html",
            "status": "draft",
        },
    }
    created_id = None
    try:
        resp = await client.post("/api/v1/artifacts", json=payload)
        assert resp.status_code == 201, resp.text
        created_id = resp.json()["id"]

        resp_approve = await client.post(
            f"/api/v1/artifacts/{created_id}/approve", json={"approve": True}
        )
        assert resp_approve.status_code == 400
        assert "FINAL" in resp_approve.json()["detail"]

        # Mark the version FINAL, then approval should succeed.
        versions_resp = await client.get(f"/api/v1/artifacts/{created_id}/versions")
        version_id = versions_resp.json()[0]["id"]
        patch_resp = await client.patch(
            f"/api/v1/artifacts/{created_id}/versions/{version_id}",
            json={"status": "final"},
        )
        assert patch_resp.status_code == 200

        resp_approve_2 = await client.post(
            f"/api/v1/artifacts/{created_id}/approve", json={"approve": True}
        )
        assert resp_approve_2.status_code == 200
        assert resp_approve_2.json()["status"] == "approved"
    finally:
        if created_id:
            await _cleanup_artifact(uuid.UUID(created_id))


@pytest.mark.asyncio
async def test_get_unknown_artifact_returns_404(client: AsyncClient):
    resp = await client.get(f"/api/v1/artifacts/{uuid.uuid4()}")
    assert resp.status_code == 404

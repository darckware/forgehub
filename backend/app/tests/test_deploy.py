"""Tests for the Deploy domain: sync-ignore behavior and group CRUD.

Sync-ignore — covers the delete → sync round-trip bug: deleting an
installation whose container still exists in Docker must record the
container_name in deploy_sync_ignores so POST /deploy/sync does not
auto-recreate it, and manually re-registering the same container_name must
lift the ignore.

Groups — covers create/list/rename/delete plus the API-layer cascades:
renaming a group rewrites matching installations' group_name; deleting a
group leaves its installations ungrouped (group_name = NULL).

Container removal — DELETE /deploy/containers/{name} must remove the
container via the host-bridge (mocked) and drop both the installation and
any sync-ignore rows; a Docker-side failure must leave the registry intact.

DB strategy: same as the other domain tests — no isolation/rollback; each
test uses UUID-suffixed unique names and cleans up its rows in a finally
block. The sync test patches the host-bridge call so no live Docker/bridge
is required.
"""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.deploy import DeployGroup, DeployInstallation, DeploySyncIgnore


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('test-deploy')}"}


@pytest_asyncio.fixture
async def client():
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=_auth_headers()) as ac:
        yield ac


async def _cleanup(container_name: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(DeployInstallation).where(DeployInstallation.container_name == container_name)
        )
        await session.execute(
            delete(DeploySyncIgnore).where(DeploySyncIgnore.container_name == container_name)
        )
        await session.commit()


async def _ignore_exists(container_name: str) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(DeploySyncIgnore).where(DeploySyncIgnore.container_name == container_name)
        )
        return result.scalars().first() is not None


@pytest.mark.asyncio
async def test_delete_installation_ignores_container_on_sync(client):
    cname = f"test-deploy-sync-{uuid.uuid4().hex[:8]}"
    try:
        resp = await client.post(
            "/api/v1/deploy/installations",
            json={"name": cname, "container_name": cname},
        )
        assert resp.status_code == 201
        inst_id = resp.json()["id"]

        resp = await client.delete(f"/api/v1/deploy/installations/{inst_id}")
        assert resp.status_code == 204
        assert await _ignore_exists(cname)

        # Sync sees the container live in Docker but must not recreate it.
        fake_ps = {"containers": [{"Names": cname, "Ports": "0.0.0.0:9999->9999/tcp"}]}
        with patch("app.api.routes.deploy._bridge", new=AsyncMock(return_value=fake_ps)):
            resp = await client.post("/api/v1/deploy/sync")
        assert resp.status_code == 200
        body = resp.json()
        assert cname not in body["names_created"]
        assert body["ignored"] >= 1

        resp = await client.get("/api/v1/deploy/installations")
        assert cname not in [i["container_name"] for i in resp.json()]
    finally:
        await _cleanup(cname)


@pytest.mark.asyncio
async def test_recreating_installation_lifts_sync_ignore(client):
    cname = f"test-deploy-sync-{uuid.uuid4().hex[:8]}"
    try:
        resp = await client.post(
            "/api/v1/deploy/installations",
            json={"name": cname, "container_name": cname},
        )
        assert resp.status_code == 201
        inst_id = resp.json()["id"]

        resp = await client.delete(f"/api/v1/deploy/installations/{inst_id}")
        assert resp.status_code == 204
        assert await _ignore_exists(cname)

        # Manual re-registration removes the ignore entry.
        resp = await client.post(
            "/api/v1/deploy/installations",
            json={"name": cname, "container_name": cname},
        )
        assert resp.status_code == 201
        assert not await _ignore_exists(cname)
    finally:
        await _cleanup(cname)


@pytest.mark.asyncio
async def test_remove_container_deletes_docker_and_registry(client):
    cname = f"test-deploy-rm-{uuid.uuid4().hex[:8]}"
    try:
        resp = await client.post(
            "/api/v1/deploy/installations",
            json={"name": cname, "container_name": cname},
        )
        assert resp.status_code == 201
        inst_id = resp.json()["id"]
        # Leave an ignore entry behind to prove removal also clears it.
        resp = await client.delete(f"/api/v1/deploy/installations/{inst_id}")
        assert resp.status_code == 204
        resp = await client.post(
            "/api/v1/deploy/installations",
            json={"name": cname, "container_name": cname},
        )
        assert resp.status_code == 201
        async with AsyncSessionLocal() as session:
            session.add(DeploySyncIgnore(container_name=cname))
            await session.commit()

        with patch("app.api.routes.deploy._bridge", new=AsyncMock(return_value={"success": True})):
            resp = await client.delete(f"/api/v1/deploy/containers/{cname}")
        assert resp.status_code == 200
        assert resp.json()["installations_removed"] == 1
        assert not await _ignore_exists(cname)

        resp = await client.get("/api/v1/deploy/installations")
        assert cname not in [i["container_name"] for i in resp.json()]
    finally:
        await _cleanup(cname)


@pytest.mark.asyncio
async def test_remove_container_docker_failure_leaves_registry(client):
    cname = f"test-deploy-rm-{uuid.uuid4().hex[:8]}"
    try:
        resp = await client.post(
            "/api/v1/deploy/installations",
            json={"name": cname, "container_name": cname},
        )
        assert resp.status_code == 201

        fake_fail = {"success": False, "stderr": "No such container"}
        with patch("app.api.routes.deploy._bridge", new=AsyncMock(return_value=fake_fail)):
            resp = await client.delete(f"/api/v1/deploy/containers/{cname}")
        assert resp.status_code == 502

        resp = await client.get("/api/v1/deploy/installations")
        assert cname in [i["container_name"] for i in resp.json()]
    finally:
        await _cleanup(cname)


async def _cleanup_group(*names: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(delete(DeployGroup).where(DeployGroup.name.in_(names)))
        await session.commit()


@pytest.mark.asyncio
async def test_group_crud_and_duplicate_name(client):
    gname = f"test-group-{uuid.uuid4().hex[:8]}"
    renamed = f"{gname}-renamed"
    try:
        resp = await client.post("/api/v1/deploy/groups", json={"name": gname})
        assert resp.status_code == 201
        group_id = resp.json()["id"]

        resp = await client.post("/api/v1/deploy/groups", json={"name": gname})
        assert resp.status_code == 409

        resp = await client.get("/api/v1/deploy/groups")
        assert resp.status_code == 200
        assert gname in [g["name"] for g in resp.json()]

        resp = await client.put(f"/api/v1/deploy/groups/{group_id}", json={"name": renamed})
        assert resp.status_code == 200
        assert resp.json()["name"] == renamed

        resp = await client.delete(f"/api/v1/deploy/groups/{group_id}")
        assert resp.status_code == 204

        resp = await client.get("/api/v1/deploy/groups")
        assert renamed not in [g["name"] for g in resp.json()]
    finally:
        await _cleanup_group(gname, renamed)


@pytest.mark.asyncio
async def test_group_rename_and_delete_cascade_to_installations(client):
    gname = f"test-group-{uuid.uuid4().hex[:8]}"
    renamed = f"{gname}-renamed"
    iname = f"test-deploy-grp-{uuid.uuid4().hex[:8]}"
    try:
        resp = await client.post("/api/v1/deploy/groups", json={"name": gname})
        assert resp.status_code == 201
        group_id = resp.json()["id"]

        resp = await client.post(
            "/api/v1/deploy/installations",
            json={"name": iname, "group_name": gname},
        )
        assert resp.status_code == 201
        inst_id = resp.json()["id"]

        # Rename propagates to the installation.
        resp = await client.put(f"/api/v1/deploy/groups/{group_id}", json={"name": renamed})
        assert resp.status_code == 200
        resp = await client.get(f"/api/v1/deploy/installations/{inst_id}")
        assert resp.json()["group_name"] == renamed

        # Delete leaves the installation ungrouped.
        resp = await client.delete(f"/api/v1/deploy/groups/{group_id}")
        assert resp.status_code == 204
        resp = await client.get(f"/api/v1/deploy/installations/{inst_id}")
        assert resp.json()["group_name"] is None
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(DeployInstallation).where(DeployInstallation.name == iname))
            await session.commit()
        await _cleanup_group(gname, renamed)

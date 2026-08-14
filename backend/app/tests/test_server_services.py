"""Server services — what runs on a server, and where to open it.

Covers the two things the feature promises: a URL always built from the
parent's *current* address, and one entry per port — including the case a
plain UNIQUE would have let through.
"""
import uuid

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.routes import server as server_routes
from app.db.base import AsyncSessionLocal, Base, engine
from app.db.models.server import Server, ServerService


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _ensure_tables():
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn, tables=[Server.__table__, ServerService.__table__], checkfirst=True
            )
        )
    yield


@pytest_asyncio.fixture
async def client(auth_headers):
    app = FastAPI()
    app.include_router(server_routes.router)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=auth_headers) as ac:
        yield ac


@pytest_asyncio.fixture
async def server_row():
    row = Server(
        id=uuid.uuid4(),
        name=f"test-services-{uuid.uuid4().hex[:8]}",
        ip_address="10.255.255.9",
        remote_user="aegis",
        ssh_port=22,
    )
    async with AsyncSessionLocal() as db:
        db.add(row)
        await db.commit()
    yield row
    # Services cascade with the server, so deleting the parent is enough.
    async with AsyncSessionLocal() as db:
        found = await db.get(Server, row.id)
        if found:
            await db.delete(found)
            await db.commit()


@pytest.mark.asyncio
async def test_url_is_built_from_the_server_and_follows_it(client, server_row):
    created = await client.post(
        f"/api/v1/servers/{server_row.id}/services",
        json={"name": "Moodle", "port": 8000, "scheme": "http"},
    )
    assert created.status_code == 201
    assert created.json()["url"] == "http://10.255.255.9:8000"

    # The URL is derived, not stored: moving the server moves its services.
    await client.put(f"/api/v1/servers/{server_row.id}", json={"ip_address": "10.255.255.10"})
    listed = await client.get(f"/api/v1/servers/{server_row.id}/services")
    assert listed.json()[0]["url"] == "http://10.255.255.10:8000"


@pytest.mark.asyncio
async def test_a_second_service_on_the_same_port_is_refused(client, server_row):
    """Regression (2026-08-14): the constraint is (server, port, path) and the
    common case has no path at all. Under a plain UNIQUE, Postgres treats each
    NULL as distinct, so the same port could be registered over and over --
    caught by registering three services on port 8000 by accident. The table
    is declared NULLS NOT DISTINCT for exactly this.
    """
    first = await client.post(
        f"/api/v1/servers/{server_row.id}/services",
        json={"name": "Moodle", "port": 8000, "scheme": "http"},
    )
    assert first.status_code == 201

    duplicate = await client.post(
        f"/api/v1/servers/{server_row.id}/services",
        json={"name": "Something else", "port": 8000, "scheme": "http"},
    )
    assert duplicate.status_code == 409

    # A different path on the same port is a different endpoint, and allowed.
    other_path = await client.post(
        f"/api/v1/servers/{server_row.id}/services",
        json={"name": "Moodle admin", "port": 8000, "scheme": "http", "path": "/admin"},
    )
    assert other_path.status_code == 201


@pytest.mark.asyncio
async def test_path_is_normalised(client, server_row):
    created = await client.post(
        f"/api/v1/servers/{server_row.id}/services",
        json={"name": "Adminer", "port": 8080, "scheme": "http", "path": "db"},
    )
    assert created.json()["path"] == "/db"
    assert created.json()["url"] == "http://10.255.255.9:8080/db"


@pytest.mark.asyncio
async def test_scan_refuses_a_parked_server(client, server_row):
    """No probe of any kind on a server the operator turned off — the same rule
    the status check follows."""
    await client.post(f"/api/v1/servers/{server_row.id}/access:toggle")
    resp = await client.post(f"/api/v1/servers/{server_row.id}/services:scan")
    assert resp.status_code == 409

"""Workspace Explorer on a remote server (`server_id`): which bridge route and
SSH target a request resolves to, and how the audit trail keys a remote path.
The bridge is mocked -- nothing here touches the host or any server."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.api.routes import file_explorer
from app.db.base import AsyncSessionLocal
from app.db.models.governance import AuditEvent
from app.db.models.server import Server

BASE = "/api/v1/file-explorer"


@pytest_asyncio.fixture
async def client():
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def server_row():
    row = Server(
        id=uuid.uuid4(),
        name=f"test-explorer-{uuid.uuid4().hex[:8]}",
        ip_address="10.255.255.7",
        remote_user="deploy",
        ssh_port=2222,
        ssh_key_path="/root/.ssh/test_explorer_key",
    )
    async with AsyncSessionLocal() as db:
        db.add(row)
        await db.commit()
    yield row
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AuditEvent).where(AuditEvent.payload["server_id"].astext == str(row.id)))
        found = await db.get(Server, row.id)
        if found:
            await db.delete(found)
        await db.commit()


def _listing(path: str) -> dict:
    return {"path": path, "parent": None, "entries": []}


async def test_without_server_the_vps_is_listed(client, admin_headers):
    bridge = AsyncMock(return_value=_listing("/root"))
    with patch.object(file_explorer, "_bridge", bridge):
        resp = await client.get(BASE, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    target, method, op = bridge.await_args.args
    assert target.server is None and target.url(op).endswith("/v1/fs/list")
    assert "X-Ssh-Host" not in target.headers
    assert bridge.await_args.kwargs["params"] == {"path": "/root"}


async def test_with_server_the_ssh_target_is_sent(client, admin_headers, server_row):
    bridge = AsyncMock(return_value=_listing("/home/deploy"))
    with patch.object(file_explorer, "_bridge", bridge):
        resp = await client.get(BASE, params={"server_id": str(server_row.id)}, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    target, _, op = bridge.await_args.args
    assert target.url(op).endswith("/v1/remote-fs/list")
    assert target.headers["X-Ssh-Host"] == "10.255.255.7"
    assert target.headers["X-Ssh-User"] == "deploy"
    assert target.headers["X-Ssh-Port"] == "2222"
    assert target.headers["X-Ssh-Key"] == "/root/.ssh/test_explorer_key"
    # No path: the server decides its own home, not the VPS's /root.
    assert bridge.await_args.kwargs["params"] == {}


async def test_unknown_or_disabled_server_is_refused(client, admin_headers, server_row):
    resp = await client.get(BASE, params={"server_id": str(uuid.uuid4())}, headers=admin_headers)
    assert resp.status_code == 404

    async with AsyncSessionLocal() as db:
        (await db.get(Server, server_row.id)).access_enabled = False
        await db.commit()
    resp = await client.get(BASE, params={"server_id": str(server_row.id)}, headers=admin_headers)
    assert resp.status_code == 403


async def test_remote_mutation_is_audited_per_server(client, admin_headers, server_row):
    bridge = AsyncMock(return_value={"name": "x", "path": "/srv/x", "type": "dir"})
    with patch.object(file_explorer, "_bridge", bridge):
        resp = await client.post(
            f"{BASE}/directory",
            params={"server_id": str(server_row.id)},
            json={"path": "/srv/x"},
            headers=admin_headers,
        )
    assert resp.status_code == 201, resp.text
    async with AsyncSessionLocal() as db:
        event = (
            await db.execute(
                select(AuditEvent).where(AuditEvent.payload["server_id"].astext == str(server_row.id))
            )
        ).scalar_one()
    assert event.event_type == "folder_created"
    assert event.payload["server"] == server_row.name
    # Same path on the VPS is a different entity.
    assert event.entity_id == uuid.uuid5(uuid.NAMESPACE_URL, f"ssh://{server_row.id}/srv/x")
    assert event.entity_id != uuid.uuid5(uuid.NAMESPACE_URL, "file:///srv/x")

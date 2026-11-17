"""Isolated API tests for host editing (`PUT /api/v1/servers/{id}`)."""
import uuid

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.api.routes import host_group as host_group_routes
from app.api.routes import server as server_routes
from app.core.secrets import encrypt_secret
from app.db.base import AsyncSessionLocal
from app.db.models.server import HostGroup, Server


@pytest_asyncio.fixture
async def client(admin_headers):
    app = FastAPI()
    app.include_router(server_routes.router)
    app.include_router(host_group_routes.router)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=admin_headers
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def marker():
    tag = f"hostedit-{uuid.uuid4().hex[:8]}"
    yield tag
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Server).where(Server.name.like(f"%{tag}%")))
        await db.execute(delete(HostGroup).where(HostGroup.name.like(f"%{tag}%")))
        await db.commit()


@pytest.mark.asyncio
async def test_name_only_edit_preserves_access_and_rejects_duplicates_clearly(client, marker):
    group = await client.post("/api/v1/host-groups", json={"name": f"Grp {marker}"})
    assert group.status_code == 201, group.text
    group_id = uuid.UUID(group.json()["id"])

    client_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        host = Server(
            name=f"host-a-{marker}",
            ip_address="100.64.10.10",
            remote_user="darckware",
            ssh_port=2222,
            kind="workstation",
            os_family="windows",
            environment="client",
            darckware_client_id=client_id,
            darckware_client_name="Client Alpha",
            ssh_key_ref="vault-key-ref-1",
            key_passphrase_encrypted=encrypt_secret("top-secret-pass"),
            pending_ssh_key_ref="pending-ref-1",
        )
        other = Server(
            name=f"host-b-{marker}",
            ip_address="100.64.10.11",
            remote_user="",
            kind="workstation",
            os_family="windows",
            environment="client",
            tailnet_node_id=f"node-{marker}",
            tailnet_name=f"host-b-{marker}",
        )
        db.add_all([host, other])
        await db.flush()
        host_id = host.id
        other_id = other.id
        await server_routes._set_server_groups(db, host_id, [group_id])
        await db.commit()

    # Record verified state after flush
    async with AsyncSessionLocal() as db:
        row = await db.get(Server, host_id)
        from datetime import datetime, timezone
        verified_at = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)
        row.access_verified_at = verified_at
        await db.commit()

    # Name-only edit on a host (even with pending_ssh_key_ref set) succeeds and preserves everything.
    renamed = await client.put(f"/api/v1/servers/{host_id}", json={"name": f"host-a-renamed-{marker}"})
    assert renamed.status_code == 200, renamed.text
    body = renamed.json()
    assert body["name"] == f"host-a-renamed-{marker}"
    assert body["ip_address"] == "100.64.10.10"
    assert body["remote_user"] == "darckware"
    assert body["ssh_port"] == 2222
    assert body["key_passphrase_stored"] is True
    assert body["ssh_key_in_vault"] is True
    assert body["group_ids"] == [str(group_id)]
    assert body["kind"] == "workstation"
    assert body["darckware_client_id"] == str(client_id)
    assert body["access_verified_at"] is not None

    # Name-only edit on a tailnet-synced host with empty remote_user also succeeds.
    renamed_other = await client.put(f"/api/v1/servers/{other_id}", json={"name": f"host-b-renamed-{marker}"})
    assert renamed_other.status_code == 200, renamed_other.text
    assert renamed_other.json()["remote_user"] == ""

    # Duplicate name must return 409 naming the host conflict, NOT tailnet link conflict.
    dup = await client.put(f"/api/v1/servers/{other_id}", json={"name": f"host-a-renamed-{marker}"})
    assert dup.status_code == 409
    assert "already exists" in dup.json()["detail"].lower()

    # Whitespace-only name must be rejected with 422.
    blank = await client.put(f"/api/v1/servers/{other_id}", json={"name": "   "})
    assert blank.status_code == 422

"""Remote Access phase 2 — workstation inventory, host groups, tailnet sync and
readiness. The tailnet and the SSH probe are mocked; the tests only touch rows
they create (names/IPs/node ids carry a per-test marker) and delete them."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.api.routes import host_group as host_group_routes
from app.api.routes import server as server_routes
from app.api.schemas.vpn import VpnNode, VpnStatus
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
    tag = f"t{uuid.uuid4().hex[:8]}"
    yield tag
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Server).where(Server.name.like(f"%{tag}%")))
        await db.execute(delete(Server).where(Server.tailnet_node_id.like(f"{tag}%")))
        await db.execute(delete(HostGroup).where(HostGroup.name.like(f"%{tag}%")))
        await db.commit()


def _status(peers: list[VpnNode], *, available: bool = True) -> VpnStatus:
    return VpnStatus(
        backend_state="Running" if available else "Unavailable",
        server=VpnNode(id="self", state="online" if available else "unavailable"),
        peers=peers,
        checked_at=datetime.now(timezone.utc),
    )


def _peer(node_id: str, name: str, ip: str, os: str = "windows", online: bool = True, tags=()):
    return VpnNode(
        id=node_id, name=name, tailscale_ipv4=ip, os=os, state="online" if online else "offline",
        online=online, tags=list(tags),
    )


def _row(**kw) -> Server:
    defaults = dict(ip_address="100.127.0.1", remote_user="admin", ssh_port=22)
    return Server(name=kw.pop("name", "x"), **{**defaults, **kw})


@pytest.mark.parametrize(
    "row, tailnet_online, ssh, expected",
    [
        (dict(access_enabled=False), True, "active", "disabled"),
        (dict(remote_user=""), True, None, "not_prepared"),
        (dict(tailnet_node_id="n1"), False, None, "offline"),
        (dict(tailnet_node_id="n1"), True, "active", "ready"),
        (dict(tailnet_node_id="n1"), True, "not_installed", "online_no_access"),
        (dict(tailnet_node_id="n1"), True, "off", "not_prepared"),
        (dict(), None, "off", "offline"),
        # A probe that couldn't be read is "unknown", never "offline".
        (dict(tailnet_node_id="n1"), True, None, "unknown"),
        (dict(), None, None, "unknown"),
    ],
)
def test_classify_readiness(row, tailnet_online, ssh, expected):
    server = _row(access_enabled=row.pop("access_enabled", True), **row)
    readiness, _ = server_routes.classify_readiness(
        server, tailnet_available=True, tailnet_online=tailnet_online, ssh=ssh
    )
    assert readiness == expected


@pytest.mark.asyncio
async def test_workstation_fields_and_groups_roundtrip(client, marker):
    group = await client.post("/api/v1/host-groups", json={"name": f"Secretaria {marker}"})
    assert group.status_code == 201, group.text
    group_id = group.json()["id"]

    client_id = str(uuid.uuid4())
    created = await client.post(
        "/api/v1/servers",
        json={
            "name": f"PC01-{marker}", "ip_address": "100.127.1.1", "remote_user": "darckware-adm",
            "kind": "workstation", "os_family": "windows", "admin_user": "Administrador",
            "environment": "client", "darckware_client_id": client_id,
            "darckware_client_name": "Cliente X", "location": "Térreo", "group_ids": [group_id],
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["kind"] == "workstation" and body["os_family"] == "windows"
    assert body["group_ids"] == [group_id]

    groups = (await client.get("/api/v1/host-groups")).json()
    mine = next(g for g in groups if g["id"] == group_id)
    assert mine["server_ids"] == [body["id"]]

    # Duplicate name within the same (absent) client is refused.
    dup = await client.post("/api/v1/host-groups", json={"name": f"Secretaria {marker}"})
    assert dup.status_code == 409

    cleared = await client.put(f"/api/v1/servers/{body['id']}", json={"group_ids": []})
    assert cleared.json()["group_ids"] == []

    bad = await client.put(f"/api/v1/servers/{body['id']}", json={"group_ids": [str(uuid.uuid4())]})
    assert bad.status_code == 422

    # Deleting a group never deletes its machines.
    await client.put(f"/api/v1/host-groups/{group_id}", json={"server_ids": [body["id"]]})
    assert (await client.delete(f"/api/v1/host-groups/{group_id}")).status_code == 204
    assert (await client.get(f"/api/v1/servers/{body['id']}")).status_code == 200


@pytest.mark.asyncio
async def test_tailnet_sync_links_imports_on_request_and_never_overwrites(client, marker):
    async with AsyncSessionLocal() as db:
        # Registered by hand with the device's tailnet IP: linked by IP.
        db.add(_row(name=f"manual-{marker}", ip_address="100.127.2.2", os_family="linux",
                    darckware_client_name="Kept", kind="workstation"))
        # A server reached by its LAN address, same name as a tailnet peer:
        # linked by name, and its address must survive every sync.
        db.add(_row(name=f"srv-{marker}", ip_address="172.15.9.9", kind="server"))
        await db.commit()

    peers = [
        _peer(f"{marker}A", f"gat-pc01-{marker}", "100.127.2.1", tags=["tag:client-gat"]),
        _peer(f"{marker}B", f"manual-host-{marker}", "100.127.2.2", os="linux"),
        _peer(f"{marker}C", f"phone-{marker}", "100.127.2.3", os="iOS"),
        _peer(f"{marker}S", f"SRV-{marker}", "100.127.2.4", os="linux"),
    ]

    async def sync(peer_list, body=None):
        with patch.object(server_routes, "fetch_tailnet_status", AsyncMock(return_value=_status(peer_list))):
            resp = await client.post("/api/v1/servers/tailnet:sync", json=body)
        assert resp.status_code == 200, resp.text
        return resp.json(), {e["node_id"]: e for e in resp.json()["entries"]}

    _, by_node = await sync(peers)
    # Not in the inventory and not asked for: reported, never created.
    assert by_node[f"{marker}A"]["outcome"] == "available"
    assert by_node[f"{marker}A"]["server_id"] is None
    assert by_node[f"{marker}A"]["suggested_client_tag"] == "gat"
    assert by_node[f"{marker}B"]["outcome"] == "linked"
    assert by_node[f"{marker}S"]["outcome"] == "linked"
    assert f"{marker}C" not in by_node  # phones are not maintenance targets

    _, by_node = await sync(peers, {"import_node_ids": [f"{marker}A"]})
    assert by_node[f"{marker}A"]["outcome"] == "created"

    async with AsyncSessionLocal() as db:
        created = (await db.execute(select(Server).where(Server.tailnet_node_id == f"{marker}A"))).scalar_one()
        assert created.kind == "workstation" and created.os_family == "windows"
        assert created.remote_user == ""  # not prepared until someone fills it in
        linked = (await db.execute(select(Server).where(Server.tailnet_node_id == f"{marker}B"))).scalar_one()
        assert linked.name == f"manual-{marker}"
        assert linked.darckware_client_name == "Kept"

    # Second pass: A renamed and re-addressed, B gone from the tailnet.
    peers2 = [_peer(f"{marker}A", f"gat-pc01-new-{marker}", "100.127.2.9"), peers[3]]
    body, by_node = await sync(peers2)
    assert by_node[f"{marker}A"]["outcome"] == "updated"
    assert str(linked.id) in body["missing_server_ids"]
    async with AsyncSessionLocal() as db:
        assert await db.get(Server, linked.id) is not None  # reported, never deleted
        assert (await db.get(Server, created.id)).ip_address == "100.127.2.9"
        srv = (await db.execute(select(Server).where(Server.tailnet_node_id == f"{marker}S"))).scalar_one()
        assert srv.ip_address == "172.15.9.9"  # a server keeps the address it is reached by

    with patch.object(server_routes, "fetch_tailnet_status", AsyncMock(return_value=_status([], available=False))):
        down = await client.post("/api/v1/servers/tailnet:sync")
    assert down.status_code == 502


@pytest.mark.asyncio
async def test_readiness_combines_tailnet_and_cached_probe(client, marker):
    async with AsyncSessionLocal() as db:
        ready = _row(name=f"ready-{marker}", tailnet_node_id=f"{marker}R", ip_address="100.127.3.1")
        offline = _row(name=f"off-{marker}", tailnet_node_id=f"{marker}O", ip_address="100.127.3.2")
        unprepared = _row(name=f"np-{marker}", tailnet_node_id=f"{marker}N", ip_address="100.127.3.3", remote_user="")
        db.add_all([ready, offline, unprepared])
        await db.commit()

    peers = [
        _peer(f"{marker}R", "r", "100.127.3.1"),
        _peer(f"{marker}O", "o", "100.127.3.2", online=False),
        _peer(f"{marker}N", "n", "100.127.3.3"),
    ]
    probe = AsyncMock(side_effect=lambda servers: {str(s.id): "active" for s in servers})
    server_routes._ssh_probe_cache.update({"at": None, "statuses": {}})
    with (
        patch.object(server_routes, "fetch_tailnet_status", AsyncMock(return_value=_status(peers))),
        patch.object(server_routes, "_probe_many_via_bridge", probe),
    ):
        resp = await client.get("/api/v1/servers/readiness")
        assert resp.status_code == 200, resp.text
        probed = {s.id for s in probe.call_args.args[0]}
        # Offline and login-less machines are not probed at all.
        assert ready.id in probed and offline.id not in probed and unprepared.id not in probed

        # Within the TTL the probe is not repeated.
        await client.get("/api/v1/servers/readiness")
        assert probe.await_count == 1

    states = {e["server_id"]: e["readiness"] for e in resp.json()["entries"]}
    assert states[str(ready.id)] == "ready"
    assert states[str(offline.id)] == "offline"
    assert states[str(unprepared.id)] == "not_prepared"
    server_routes._ssh_probe_cache.update({"at": None, "statuses": {}})

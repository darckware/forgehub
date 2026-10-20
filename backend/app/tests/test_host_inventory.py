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
from app.api.schemas.vpn import VpnNode, VpnPosture, VpnStatus
from app.db.base import AsyncSessionLocal
from app.core.security import create_access_token, hash_password
from app.db.models.profile import Profile, ProfilePermission
from app.db.models.server import HostGroup, Server
from app.db.models.user import User


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
        # The key not being accepted means "not prepared yet", not a refusal.
        (dict(tailnet_node_id="n1"), True, "not_installed", "not_prepared"),
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


@pytest.mark.parametrize(
    "kind, rustdesk_id, readiness, expected",
    [
        ("workstation", "217385777", "ready", "complete"),
        ("workstation", None, "ready", "partial"),        # SSH without RustDesk
        ("server", None, "ready", "complete"),            # a server needs only SSH
        ("workstation", "217385777", "not_prepared", "partial"),  # RustDesk without SSH
        ("server", None, "not_prepared", "not_prepared"),
        ("workstation", "217385777", "offline", "offline"),
        ("workstation", None, "unknown", "unknown"),
        ("workstation", "1", "disabled", "disabled"),
    ],
)
def test_classify_status(kind, rustdesk_id, readiness, expected):
    server = _row(kind=kind, rustdesk_id=rustdesk_id)
    assert server_routes.classify_status(server, readiness)[0] == expected


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
    colors = {e["server_id"]: e["status"] for e in resp.json()["entries"]}
    assert colors[str(ready.id)] == "complete" and colors[str(unprepared.id)] == "not_prepared"
    assert states[str(ready.id)] == "ready"
    assert states[str(offline.id)] == "offline"
    assert states[str(unprepared.id)] == "not_prepared"
    server_routes._ssh_probe_cache.update({"at": None, "statuses": {}})


_ROUTERS = [("nSUP", "srv-sup", ["172.15.0.0/16"]), ("nLAB", "lab", ["172.15.9.0/24"])]


@pytest.mark.parametrize(
    "ip, available, accept, expected",
    [
        ("100.107.175.100", True, False, ("tailscale", None, None)),
        ("172.15.2.2", True, True, ("subnet", "nSUP", "srv-sup")),
        # The most specific route wins.
        ("172.15.9.7", True, True, ("subnet", "nLAB", "lab")),
        ("172.15.2.2", True, False, ("subnet_not_accepted", "nSUP", "srv-sup")),
        # Posture unread: not claimed as usable.
        ("172.15.2.2", True, None, ("subnet_not_accepted", "nSUP", "srv-sup")),
        ("10.0.0.5", True, True, ("none", None, None)),
        ("", True, True, ("none", None, None)),
        # An unreadable tailnet is "unknown", never "none".
        ("172.15.2.2", False, True, ("unknown", None, None)),
    ],
)
def test_classify_access_path(ip, available, accept, expected):
    server = _row(ip_address=ip)
    assert server_routes.classify_access_path(
        server, tailnet_available=available, accept_routes=accept, routers=_ROUTERS
    ) == expected


@pytest.mark.asyncio
async def test_readiness_reports_access_path_and_tailscale_ip(client, marker):
    async with AsyncSessionLocal() as db:
        lan = _row(name=f"lan-{marker}", ip_address="172.15.77.1", tailnet_node_id=f"{marker}L")
        orphan = _row(name=f"orphan-{marker}", ip_address="10.66.0.1")
        db.add_all([lan, orphan])
        await db.commit()

    router = _peer(f"{marker}S", "srv-sup", "100.127.9.1", os="linux")
    router.subnet_routes = ["172.15.0.0/16"]
    status = _status([router, _peer(f"{marker}L", "lan-box", "100.127.9.2", os="linux")])
    status.server.posture = VpnPosture(
        accept_dns=False, accept_routes=True, advertise_exit_node=False,
        tailscale_ssh=False, exit_node=False, restricted=False,
    )
    server_routes._ssh_probe_cache.update({"at": None, "statuses": {}})
    with (
        patch.object(server_routes, "fetch_tailnet_status", AsyncMock(return_value=status)),
        patch.object(server_routes, "_probe_many_via_bridge", AsyncMock(return_value={})),
    ):
        resp = await client.get("/api/v1/servers/readiness")
    assert resp.status_code == 200, resp.text
    by_id = {e["server_id"]: e for e in resp.json()["entries"]}
    assert by_id[str(lan.id)]["access_path"] == "subnet"
    assert by_id[str(lan.id)]["access_via_name"] == "srv-sup"
    assert by_id[str(lan.id)]["tailscale_ipv4"] == "100.127.9.2"
    assert by_id[str(orphan.id)]["access_path"] == "none"
    server_routes._ssh_probe_cache.update({"at": None, "statuses": {}})


@pytest.mark.asyncio
async def test_readiness_is_open_to_the_servers_module():
    """Remote Access › Machines replaced the Servers page for the "servers"
    module (2026-10-17): a non-admin with servers.view reads readiness, one
    without it does not, and the tailnet sync stays admin-only."""
    tag = uuid.uuid4().hex[:12]
    async with AsyncSessionLocal() as db:
        profile = Profile(name=f"test-servers-{tag}")
        db.add(profile)
        await db.flush()
        db.add(ProfilePermission(profile_id=profile.id, module="servers", can_view=True))
        db.add(User(username=f"test-servers-{tag}", hashed_password=hash_password(tag), profile_id=profile.id))
        db.add(User(username=f"test-noperm-{tag}", hashed_password=hash_password(tag)))
        await db.commit()
        profile_id = profile.id
    app = FastAPI()
    app.include_router(server_routes.router)
    server_routes._ssh_probe_cache.update({"at": None, "statuses": {}})
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            with (
                patch.object(server_routes, "fetch_tailnet_status", AsyncMock(return_value=_status([]))),
                patch.object(server_routes, "_probe_many_via_bridge", AsyncMock(return_value={})),
            ):
                allowed = {"Authorization": f"Bearer {create_access_token(f'test-servers-{tag}')}"}
                denied = {"Authorization": f"Bearer {create_access_token(f'test-noperm-{tag}')}"}
                resp = await c.get("/api/v1/servers/readiness", headers=allowed)
                assert resp.status_code == 200, resp.text
                assert (await c.get("/api/v1/servers/readiness", headers=denied)).status_code == 403
                sync = await c.post("/api/v1/servers/tailnet:sync", json={"import_node_ids": []}, headers=allowed)
                assert sync.status_code == 403
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(User).where(User.username.in_([f"test-servers-{tag}", f"test-noperm-{tag}"])))
            await db.execute(delete(ProfilePermission).where(ProfilePermission.profile_id == profile_id))
            await db.execute(delete(Profile).where(Profile.id == profile_id))
            await db.commit()


@pytest.mark.asyncio
async def test_detect_missing_os_fills_only_blank_and_answering_machines(client, marker):
    """Only this test's rows get an answer: every other machine (real ones
    share this database) gets a bridge error and must stay untouched."""
    import httpx

    from app.db.models.governance import AuditEvent

    async with AsyncSessionLocal() as db:
        win = _row(name=f"win-{marker}", ip_address="100.127.8.1", ssh_key_path="/k")
        lin = _row(name=f"lin-{marker}", ip_address="100.127.8.2", ssh_key_path="/k")
        set_already = _row(name=f"mac-{marker}", ip_address="100.127.8.3", ssh_key_path="/k", os_family="macos")
        nokey = _row(name=f"nokey-{marker}", ip_address="100.127.8.4")
        db.add_all([win, lin, set_already, nokey])
        await db.commit()

    answers = {"100.127.8.1": "windows", "100.127.8.2": "linux"}
    asked = []

    async def fake_bridge(path, payload, timeout=20.0):
        asked.append(payload["host"])
        if payload["host"] in answers:
            return httpx.Response(200, json={"os_family": answers[payload["host"]], "detail": "x"})
        return httpx.Response(502, json={"detail": "Machine unreachable on SSH"})

    with patch.object(server_routes, "_bridge_post", fake_bridge):
        resp = await client.post("/api/v1/servers/os:detect")
    assert resp.status_code == 200, resp.text
    by_name = {r["name"]: r for r in resp.json()}
    assert by_name[f"nokey-{marker}"]["detail"] == "No ForgeHub key for this machine"
    assert f"mac-{marker}" not in by_name and "100.127.8.3" not in asked
    async with AsyncSessionLocal() as db:
        assert (await db.get(Server, win.id)).os_family == "windows"
        assert (await db.get(Server, lin.id)).os_family == "linux"
        assert (await db.get(Server, set_already.id)).os_family == "macos"
        await db.execute(delete(AuditEvent).where(AuditEvent.entity_id.in_([win.id, lin.id])))
        await db.commit()


@pytest.mark.asyncio
async def test_forget_host_key_is_audited(client, marker):
    import httpx

    from app.db.models.governance import AuditEvent

    async with AsyncSessionLocal() as db:
        row = _row(name=f"hk-{marker}", ip_address="100.127.7.1")
        db.add(row)
        await db.commit()
    sent = []

    async def fake_bridge(path, payload, timeout=20.0):
        sent.append((path, payload))
        return httpx.Response(200, json={"removed": True})

    with patch.object(server_routes, "_bridge_post", fake_bridge):
        resp = await client.post(f"/api/v1/servers/{row.id}/host-key:forget")
    assert resp.status_code == 200 and resp.json() == {"removed": True}
    assert sent == [("/v1/servers/forget-host-key", {"host": "100.127.7.1", "port": 22})]
    async with AsyncSessionLocal() as db:
        event = (await db.execute(select(AuditEvent).where(AuditEvent.entity_id == row.id))).scalar_one()
        assert event.event_type == "host_key_forgotten"
        await db.delete(event)
        await db.commit()


@pytest.mark.asyncio
async def test_history_shows_terminal_session_duration(client, marker):
    from datetime import timedelta

    from app.db.models.governance import AuditEvent

    session = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        row = _row(name=f"term-{marker}", ip_address="100.127.6.1")
        db.add(row)
        await db.flush()
        start = datetime.now(timezone.utc) - timedelta(minutes=30)
        db.add_all([
            AuditEvent(entity_type="terminal_session", entity_id=session, event_type="opened", actor="marcelo",
                       payload={"server_id": str(row.id)}, created_at=start),
            AuditEvent(entity_type="terminal_session", entity_id=session, event_type="closed", actor="marcelo",
                       payload={}, created_at=start + timedelta(minutes=12)),
        ])
        await db.commit()
    try:
        history = (await client.get(f"/api/v1/servers/{row.id}/maintenance")).json()
        assert [h["title"] for h in history if h["kind"] == "terminal"] == ["Terminal SSH (12 min)"]
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AuditEvent).where(AuditEvent.entity_id == session))
            await db.commit()

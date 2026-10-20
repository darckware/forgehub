"""Enroll station: scripts, the enrollment route (bridge + Tailscale mocked),
linking by name, password reveal and the Tailscale API key setting. Only
rows created here are touched; the API key tests use a test-only secret name."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.api.routes import server as server_routes
from app.api.routes import vpn as vpn_routes
from app.api.schemas.vpn import VpnNode, VpnStatus
from app.core.host_enrollment import EnrollmentError, enrollment_script, generate_password
from app.db.base import AsyncSessionLocal
from app.db.models.governance import AuditEvent
from app.db.models.server import Server
from app.db.models.vpn import RemoteAccessSecret

KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMQ97vnwnBBhgd4AiT2WLx7Z5qEVdq6sB3KPgSX3fd7C forgehub@x"
AUTH = "tskey-auth-kAbc123CNTRL-xyz"


def _kwargs(**over):
    base = dict(name="gat-adm-pc02", tag="tag:gatling-users", auth_key=AUTH, password=generate_password(), public_key=KEY)
    return {**base, **over}


@pytest.mark.parametrize("os_family", ["windows", "linux"])
def test_scripts_carry_everything_and_no_control_chars(os_family):
    kw = _kwargs()
    script, _ = enrollment_script(os_family, **kw)
    for value in (kw["name"], kw["tag"], AUTH, kw["password"], KEY, "darckware"):
        assert value in script
    assert not [c for c in script if ord(c) < 32 and c not in "\n\r\t"]
    if os_family == "windows":
        assert r'"$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"' in script
        assert "--unattended" in script and "S-1-5-32-544" in script
    else:
        assert "NOPASSWD" in script and "chpasswd" in script


@pytest.mark.parametrize("over", [
    {"name": "PC 01"}, {"tag": "gatling-users"}, {"auth_key": "abc'; rm"}, {"password": "a'b"}, {"public_key": "x"},
])
def test_scripts_refuse_unsafe_values(over):
    with pytest.raises(EnrollmentError):
        enrollment_script("windows", **_kwargs(**over))


def test_macos_not_yet():
    with pytest.raises(EnrollmentError):
        enrollment_script("macos", **_kwargs())


def test_generated_passwords_are_strong_and_unique():
    pws = {generate_password() for _ in range(50)}
    assert len(pws) == 50
    for pw in pws:
        assert len(pw) == 20 and any(c.isupper() for c in pw) and any(c.isdigit() for c in pw)
        assert not set(pw) & set("'\"`$\\ ")


@pytest_asyncio.fixture
async def client(admin_headers):
    app = FastAPI()
    app.include_router(server_routes.router)
    app.include_router(vpn_routes.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=admin_headers) as ac:
        yield ac


@pytest_asyncio.fixture
async def station_name():
    name = f"t-{uuid.uuid4().hex[:8]}"
    yield name
    async with AsyncSessionLocal() as db:
        ids = list((await db.execute(select(Server.id).where(Server.name == name))).scalars())
        if ids:
            await db.execute(delete(AuditEvent).where(AuditEvent.entity_id.in_(ids)))
            await db.execute(delete(Server).where(Server.id.in_(ids)))
        await db.commit()


def _resp(payload, code=200):
    return httpx.Response(code, json=payload, request=httpx.Request("POST", "http://bridge"))


@pytest.mark.asyncio
async def test_enroll_link_and_reveal(client, station_name):
    async def bridge(path, payload, timeout=20.0):
        if path == "/v1/servers/ensure-key":
            assert payload["key_name"].startswith("ws_")
            return _resp({"key_path": f"/root/agents/aegis/server-management/ssh_keys/{payload['key_name']}_key",
                          "public_key": KEY, "created": True})
        return _resp({"private_key": "PRIV", "public_key": KEY, "key_path": "x"})

    mint = AsyncMock(return_value=AUTH)
    vault: dict[str, str] = {}

    async def fake_store(name, value, description, secret_type="Password"):
        vault[name] = value
        return "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    async def fake_reveal(secret_id):
        return next(iter(vault.values()))

    with (
        patch.object(server_routes, "vault_store", fake_store),
        patch.object(server_routes, "vault_reveal", fake_reveal),
        patch.object(server_routes, "_bridge_post", AsyncMock(side_effect=bridge)),
        patch.object(server_routes, "load_api_key", AsyncMock(return_value="tskey-api-x")),
        patch.object(server_routes, "create_auth_key", mint),
    ):
        resp = await client.post("/api/v1/servers/enrollments", json={
            "name": station_name, "os_family": "windows", "tag": "tag:gatling-users",
            "darckware_client_name": "HW Clube",
        })
        assert resp.status_code == 201, resp.text
        body = resp.json()
        dup = await client.post("/api/v1/servers/enrollments", json={
            "name": station_name.upper(), "os_family": "windows", "tag": "tag:gatling-users",
        })
        assert dup.status_code == 409

    assert mint.await_args.args[1] == "tag:gatling-users"
    assert AUTH in body["script"] and body["auth_key_expires_hours"] == 24
    server_id = body["server_id"]

    async with AsyncSessionLocal() as db:
        row = await db.get(Server, uuid.UUID(server_id))
        assert row.remote_user == "darckware" and row.ip_address == "" and row.kind == "workstation"
        assert row.login_password_ref == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        password = next(iter(vault.values()))
        assert password in body["script"]
        audit = (await db.execute(select(AuditEvent).where(AuditEvent.entity_id == row.id))).scalar_one()
        assert password not in str(audit.payload) and AUTH not in str(audit.payload)

    readiness = server_routes.classify_readiness(row, tailnet_available=True, tailnet_online=None, ssh=None)
    assert readiness == ("not_prepared", "Waiting for the station to join the tailnet")

    def status(peers):
        return VpnStatus(backend_state="Running", server=VpnNode(id="self", state="online"), peers=peers,
                         checked_at=datetime.now(timezone.utc))

    with patch.object(server_routes, "fetch_tailnet_status", AsyncMock(return_value=status([]))):
        waiting = await client.post(f"/api/v1/servers/{server_id}/enrollment:check")
    assert waiting.json()["state"] == "waiting"

    peer = VpnNode(id=f"n{uuid.uuid4().hex[:10]}", name=station_name, hostname="DESKTOP-X", os="windows",
                   tailscale_ipv4="100.127.7.7", state="online", online=True)
    with patch.object(server_routes, "fetch_tailnet_status", AsyncMock(return_value=status([peer]))):
        joined = (await client.post(f"/api/v1/servers/{server_id}/enrollment:check")).json()
    assert joined == {"server_id": server_id, "state": "joined", "tailscale_ipv4": "100.127.7.7", "tailnet_name": station_name}

    listed = next(s for s in (await client.get("/api/v1/servers")).json() if s["id"] == server_id)
    assert listed["login_password_stored"] is True and password not in str(listed)

    with patch.object(server_routes, "vault_reveal", fake_reveal):
        revealed = await client.get(f"/api/v1/servers/{server_id}/login-password")
    assert revealed.json() == {"server_id": server_id, "login": "darckware", "password": password}
    async with AsyncSessionLocal() as db:
        events = (await db.execute(select(AuditEvent.event_type).where(AuditEvent.entity_id == uuid.UUID(server_id)))).scalars().all()
        assert "login_password_revealed" in events


@pytest.mark.asyncio
async def test_enroll_requires_api_key_and_valid_name(client, station_name):
    with patch.object(server_routes, "load_api_key", AsyncMock(return_value=None)):
        no_key = await client.post("/api/v1/servers/enrollments", json={
            "name": station_name, "os_family": "linux", "tag": "tag:semed-users"})
        assert no_key.status_code == 409
        bad = await client.post("/api/v1/servers/enrollments", json={
            "name": "PC da Recepção", "os_family": "linux", "tag": "tag:semed-users"})
        assert bad.status_code == 422


@pytest.mark.asyncio
async def test_tailscale_api_key_setting_never_returns_the_key(client):
    name = f"test-key-{uuid.uuid4().hex[:6]}"
    try:
        with patch.object(vpn_routes, "API_KEY_NAME", name):
            assert (await client.get("/api/v1/vpn/tailscale-api-key")).json()["configured"] is False
            assert (await client.put("/api/v1/vpn/tailscale-api-key", json={"api_key": "not-a-key"})).status_code == 422
            saved = await client.put("/api/v1/vpn/tailscale-api-key", json={"api_key": "tskey-api-kSecret123-abcd"})
            assert saved.json()["configured"] is True and saved.json()["hint"] == "abcd"
            assert "kSecret123" not in saved.text
            assert (await client.delete("/api/v1/vpn/tailscale-api-key")).json()["configured"] is False
    finally:
        async with AsyncSessionLocal() as db:
            ids = list((await db.execute(select(RemoteAccessSecret.id).where(RemoteAccessSecret.name == name))).scalars())
            await db.execute(delete(AuditEvent).where(AuditEvent.entity_type == "remote_access_secret",
                                                     AuditEvent.actor.like("test-admin-%")))
            if ids:
                await db.execute(delete(RemoteAccessSecret).where(RemoteAccessSecret.id.in_(ids)))
            await db.commit()

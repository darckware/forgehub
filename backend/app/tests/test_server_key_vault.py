"""Server key vault — the encrypted copy of an identity file kept on the row.

Covers the property that made the feature necessary (2026-08-14): the vaulted
material must survive on the row, never appear in a response, and be handed to
the host bridge verbatim on restore. The bridge itself is mocked — these tests
must not read or write real SSH keys on the host.

The backup/restore/public-key routes were retired with ForgeVault-only keys
(docs/superpowers/plans/2026-10-24-forgevault-only-ssh-keys.md), and their
tests with them; what remains covers the row-level fields still in use.
"""
import uuid
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.routes import server as server_routes
from app.core.secrets import decrypt_secret, encrypt_secret
from app.db.base import AsyncSessionLocal, Base, engine
from app.db.models.server import Server
from app.db.models.user import User

FAKE_KEY = "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEA\n-----END OPENSSH PRIVATE KEY-----\n"


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _ensure_server_table():
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn, tables=[Server.__table__], checkfirst=True
            )
        )
    yield


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _ensure_admin_user():
    """Every vault route is admin-gated (each one handles private key
    material). Same shared "test-suite" username convention as test_agent.py."""
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.username == "test-suite"))).scalar_one_or_none()
        created = user is None
        if created:
            session.add(User(
                username="test-suite", hashed_password="test-only-not-a-real-password",
                is_active=True, is_admin=True,
            ))
            await session.commit()
    yield
    if created:
        async with AsyncSessionLocal() as session:
            user = (await session.execute(select(User).where(User.username == "test-suite"))).scalar_one_or_none()
            if user:
                await session.delete(user)
                await session.commit()


@pytest_asyncio.fixture
async def client(auth_headers):
    app = FastAPI()
    app.include_router(server_routes.router)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=auth_headers) as ac:
        yield ac


@pytest_asyncio.fixture
async def server_row():
    """A throwaway inventory row; deleted afterwards regardless of outcome."""
    row = Server(
        id=uuid.uuid4(),
        name=f"test-vault-{uuid.uuid4().hex[:8]}",
        ip_address="10.255.255.1",
        remote_user="aegis",
        ssh_port=22,
        ssh_key_path="/root/.ssh/test_vault_key",
    )
    async with AsyncSessionLocal() as db:
        db.add(row)
        await db.commit()
    yield row
    async with AsyncSessionLocal() as db:
        found = await db.get(Server, row.id)
        if found:
            await db.delete(found)
            await db.commit()


def _bridge_response(status_code: int, payload: dict) -> httpx.Response:
    return httpx.Response(status_code, json=payload, request=httpx.Request("POST", "http://bridge"))


@pytest.mark.asyncio
async def test_store_pasted_key_rejects_something_that_is_not_a_key(client, server_row):
    resp = await client.put(f"/api/v1/servers/{server_row.id}/key", json={"private_key": "hunter2"})
    assert resp.status_code == 422
    async with AsyncSessionLocal() as db:
        assert (await db.get(Server, server_row.id)).private_key_encrypted is None


@pytest.mark.asyncio
async def test_passphrase_is_encrypted_at_rest_and_only_the_detail_route_returns_it(client, server_row):
    """Same contract as the agent's ForgeRouter API key: encrypted in the
    column, absent from the list and from a write's response, and handed back
    only by the admin-only single-server read -- which is what lets the form
    show the current value behind an eye toggle."""
    resp = await client.put(
        f"/api/v1/servers/{server_row.id}",
        json={"key_passphrase": "correct-horse-battery-staple"},
    )
    assert resp.status_code == 200
    assert resp.json()["key_passphrase_stored"] is True
    assert "correct-horse" not in resp.text

    listing = await client.get("/api/v1/servers")
    assert "correct-horse" not in listing.text

    detail = await client.get(f"/api/v1/servers/{server_row.id}")
    assert detail.json()["key_passphrase"] == "correct-horse-battery-staple"

    async with AsyncSessionLocal() as db:
        stored = await db.get(Server, server_row.id)
        assert stored.key_passphrase_encrypted != "correct-horse-battery-staple"
        assert decrypt_secret(stored.key_passphrase_encrypted) == "correct-horse-battery-staple"


@pytest.mark.asyncio
async def test_an_unrelated_edit_keeps_the_passphrase_but_an_empty_one_clears_it(client, server_row):
    """The form never receives the stored passphrase, so a save that does not
    mention the field must not wipe it -- while an explicitly empty value is
    how the field is cleared."""
    async with AsyncSessionLocal() as db:
        row = await db.get(Server, server_row.id)
        row.key_passphrase_encrypted = encrypt_secret("keep-me")
        await db.commit()

    kept = await client.put(f"/api/v1/servers/{server_row.id}", json={"description": "touched"})
    assert kept.json()["key_passphrase_stored"] is True

    cleared = await client.put(f"/api/v1/servers/{server_row.id}", json={"key_passphrase": ""})
    assert cleared.json()["key_passphrase_stored"] is False
    async with AsyncSessionLocal() as db:
        assert (await db.get(Server, server_row.id)).key_passphrase_encrypted is None


@pytest.mark.asyncio
async def test_toggling_access_off_parks_the_server_without_touching_the_key(client, server_row):
    """The whole point of the switch: no probe runs, and the vaulted key --
    the way back in -- is still there afterwards."""
    async with AsyncSessionLocal() as db:
        row = await db.get(Server, server_row.id)
        row.private_key_encrypted = encrypt_secret(FAKE_KEY)
        await db.commit()

    off = await client.post(f"/api/v1/servers/{server_row.id}/access:toggle")
    assert off.status_code == 200
    assert off.json()["access_enabled"] is False
    assert off.json()["private_key_stored"] is True

    # No bridge call and no paramiko probe -- patched to blow up if reached.
    with patch.object(server_routes, "_check_via_bridge", AsyncMock(side_effect=AssertionError("probed a disabled server"))):
        check = await client.post(f"/api/v1/servers/{server_row.id}/check")
    assert check.status_code == 200
    assert check.json()["status"] == "disabled"

    on = await client.post(f"/api/v1/servers/{server_row.id}/access:toggle")
    assert on.json()["access_enabled"] is True
    async with AsyncSessionLocal() as db:
        assert decrypt_secret((await db.get(Server, server_row.id)).private_key_encrypted) == FAKE_KEY


@pytest.mark.asyncio
async def test_clear_drops_the_copy(client, server_row):
    async with AsyncSessionLocal() as db:
        row = await db.get(Server, server_row.id)
        row.private_key_encrypted = encrypt_secret(FAKE_KEY)
        await db.commit()

    resp = await client.delete(f"/api/v1/servers/{server_row.id}/key")
    assert resp.status_code == 200
    assert resp.json()["private_key_stored"] is False
    async with AsyncSessionLocal() as db:
        assert (await db.get(Server, server_row.id)).private_key_encrypted is None

"""Workspace Explorer Quick access -- per-user pins/unpins, real DB.
Rows cascade away with the throwaway admins from conftest's admin_headers."""
import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.security import create_access_token, hash_password
from app.db.base import AsyncSessionLocal
from app.db.models.user import User

BASE = "/api/v1/file-explorer/quick-access"


@pytest_asyncio.fixture
async def client():
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def other_admin_headers():
    username = f"test-admin-{uuid.uuid4().hex[:12]}"
    async with AsyncSessionLocal() as db:
        db.add(User(username=username, hashed_password=hash_password(uuid.uuid4().hex), is_admin=True))
        await db.commit()
    yield {"Authorization": f"Bearer {create_access_token(username)}"}
    async with AsyncSessionLocal() as db:
        await db.execute(delete(User).where(User.username == username))
        await db.commit()


async def test_pin_hide_and_unpin(client: AsyncClient, admin_headers):
    assert (await client.get(BASE, headers=admin_headers)).json() == []

    pinned = await client.put(BASE, json={"path": "/root/project/forgehub/", "label": " ForgeHub "}, headers=admin_headers)
    assert pinned.status_code == 200, pinned.text
    # Normalized path, trimmed label.
    assert pinned.json() == {"path": "/root/project/forgehub", "label": "ForgeHub", "hidden": False}

    # Removing a built-in entry is a hidden row.
    hidden = await client.put(BASE, json={"path": "/", "hidden": True}, headers=admin_headers)
    assert hidden.json()["hidden"] is True

    # Upsert by path: pinning the same folder again doesn't duplicate it.
    await client.put(BASE, json={"path": "/root/project/forgehub"}, headers=admin_headers)
    rows = (await client.get(BASE, headers=admin_headers)).json()
    assert [(r["path"], r["hidden"]) for r in rows] == [("/root/project/forgehub", False), ("/", True)]

    # Unpin: the pin disappears; deleting the hidden row brings the built-in back.
    assert (await client.delete(BASE, params={"path": "/root/project/forgehub"}, headers=admin_headers)).status_code == 204
    assert (await client.delete(BASE, params={"path": "/"}, headers=admin_headers)).status_code == 204
    assert (await client.get(BASE, headers=admin_headers)).json() == []
    # Idempotent.
    assert (await client.delete(BASE, params={"path": "/"}, headers=admin_headers)).status_code == 204


async def test_quick_access_is_per_user(client: AsyncClient, admin_headers, other_admin_headers):
    await client.put(BASE, json={"path": "/srv/mine"}, headers=admin_headers)
    assert (await client.get(BASE, headers=other_admin_headers)).json() == []
    # Another user's unpin of the same path never touches this user's row.
    await client.delete(BASE, params={"path": "/srv/mine"}, headers=other_admin_headers)
    assert [r["path"] for r in (await client.get(BASE, headers=admin_headers)).json()] == ["/srv/mine"]


async def test_rejects_relative_paths_and_non_admins(client: AsyncClient, admin_headers):
    assert (await client.put(BASE, json={"path": "relative/dir"}, headers=admin_headers)).status_code == 400

    # A real, active, non-admin user: authenticated but not allowed (403).
    username = f"test-user-{uuid.uuid4().hex[:12]}"
    async with AsyncSessionLocal() as db:
        db.add(User(username=username, hashed_password=hash_password(uuid.uuid4().hex)))
        await db.commit()
    try:
        user_headers = {"Authorization": f"Bearer {create_access_token(username)}"}
        assert (await client.get(BASE, headers=user_headers)).status_code == 403
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(User).where(User.username == username))
            await db.commit()

    # A token whose subject doesn't exist at all (401), independent of
    # whatever other tests have created in the shared database.
    ghost = {"Authorization": f"Bearer {create_access_token(f'ghost-{uuid.uuid4().hex}')}"}
    assert (await client.get(BASE, headers=ghost)).status_code == 401

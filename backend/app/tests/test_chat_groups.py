"""Tests for ChatGroup CRUD and the Project/Group exclusivity rule on
ChatSession (see db/models/chat.py's ChatGroup/ChatSession.group_id
docstrings and api/routes/chat.py's update_chat_session)."""
import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db.base import AsyncSessionLocal, engine
from app.db.models.agent import Agent
from app.main import app

_STUB_AGENT_ID: uuid.UUID | None = None
_created_group_ids: list[uuid.UUID] = []
_created_session_ids: list[uuid.UUID] = []


@pytest_asyncio.fixture(scope="module")
async def db_schema():
    global _STUB_AGENT_ID

    async with AsyncSessionLocal() as session:
        agent = Agent(
            name=f"Chat Group Test Agent {uuid.uuid4()}",
            profile_slug=f"chat-group-test-{uuid.uuid4().hex[:8]}",
        )
        session.add(agent)
        await session.commit()
        _STUB_AGENT_ID = agent.id

    yield

    async with engine.begin() as conn:
        if _created_session_ids:
            await conn.execute(
                text("DELETE FROM company.chat_sessions WHERE id = ANY(:ids)"),
                {"ids": _created_session_ids},
            )
        if _created_group_ids:
            await conn.execute(
                text("DELETE FROM company.chat_groups WHERE id = ANY(:ids)"),
                {"ids": _created_group_ids},
            )
        await conn.execute(text("DELETE FROM company.agents WHERE id = :id"), {"id": _STUB_AGENT_ID})


@pytest_asyncio.fixture
async def client(db_schema, auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=auth_headers) as ac:
        yield ac


async def _create_group(client: AsyncClient, name: str | None = None) -> dict:
    resp = await client.post("/api/v1/chat/groups", json={"name": name or f"Group {uuid.uuid4()}"})
    assert resp.status_code == 201, resp.text
    data = resp.json()
    _created_group_ids.append(uuid.UUID(data["id"]))
    return data


async def _create_session(client: AsyncClient) -> dict:
    resp = await client.post(
        "/api/v1/chat/sessions",
        json={"agent_id": str(_STUB_AGENT_ID), "title": f"Session {uuid.uuid4()}"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    _created_session_ids.append(uuid.UUID(data["id"]))
    return data


async def test_create_list_rename_delete_group(client: AsyncClient):
    group = await _create_group(client, name="Marketing")
    assert group["name"] == "Marketing"

    list_resp = await client.get("/api/v1/chat/groups")
    assert list_resp.status_code == 200
    assert any(g["id"] == group["id"] for g in list_resp.json())

    rename_resp = await client.patch(f"/api/v1/chat/groups/{group['id']}", json={"name": "Renamed"})
    assert rename_resp.status_code == 200
    assert rename_resp.json()["name"] == "Renamed"

    delete_resp = await client.delete(f"/api/v1/chat/groups/{group['id']}")
    assert delete_resp.status_code == 204
    _created_group_ids.remove(uuid.UUID(group["id"]))

    get_resp = await client.get("/api/v1/chat/groups")
    assert all(g["id"] != group["id"] for g in get_resp.json())


async def test_assign_session_to_group(client: AsyncClient):
    group = await _create_group(client)
    session = await _create_session(client)

    resp = await client.patch(f"/api/v1/chat/sessions/{session['id']}", json={"group_id": group["id"]})
    assert resp.status_code == 200
    assert resp.json()["group_id"] == group["id"]


async def test_assigning_group_clears_project_path(client: AsyncClient, tmp_path):
    group = await _create_group(client)
    session = await _create_session(client)

    await client.patch(
        f"/api/v1/chat/sessions/{session['id']}", json={"working_directory_path": str(tmp_path)}
    )
    resp = await client.patch(f"/api/v1/chat/sessions/{session['id']}", json={"group_id": group["id"]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["group_id"] == group["id"]
    assert body["working_directory_path"] is None


async def test_assigning_project_path_clears_group(client: AsyncClient, tmp_path):
    group = await _create_group(client)
    session = await _create_session(client)

    await client.patch(f"/api/v1/chat/sessions/{session['id']}", json={"group_id": group["id"]})
    resp = await client.patch(
        f"/api/v1/chat/sessions/{session['id']}", json={"working_directory_path": str(tmp_path)}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["working_directory_path"] == str(tmp_path)
    assert body["group_id"] is None


async def test_deleting_group_returns_sessions_to_loose_list(client: AsyncClient):
    group = await _create_group(client)
    session = await _create_session(client)
    await client.patch(f"/api/v1/chat/sessions/{session['id']}", json={"group_id": group["id"]})

    delete_resp = await client.delete(f"/api/v1/chat/groups/{group['id']}")
    assert delete_resp.status_code == 204
    _created_group_ids.remove(uuid.UUID(group["id"]))

    get_resp = await client.get(f"/api/v1/chat/sessions/{session['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["group_id"] is None


async def test_assign_to_nonexistent_group_404s(client: AsyncClient):
    session = await _create_session(client)
    resp = await client.patch(
        f"/api/v1/chat/sessions/{session['id']}", json={"group_id": str(uuid.uuid4())}
    )
    assert resp.status_code == 404

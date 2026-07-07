"""Tests for the Tool domain (registry of agent-built tools).

Covers: create/get/list with agent_name resolution, per-agent name
uniqueness (409), agent existence check, status validation, filters
(agent_id / q), partial update, and delete.

DB strategy: same as the other domain tests — no isolation/rollback; each
test creates its own agent row (UUID-suffixed unique name) directly via the
session and removes it in a finally block (agent_tools rows cascade).
"""
import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('test-tools')}"}


@pytest_asyncio.fixture
async def client():
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=_auth_headers()) as ac:
        yield ac


async def _insert_agent(profile_slug: str | None = None) -> Agent:
    agent = Agent(
        id=uuid.uuid4(),
        name=f"test-tool-agent-{uuid.uuid4().hex[:8]}",
        agent_type="executor",
        status="active",
        profile_slug=profile_slug,
    )
    async with AsyncSessionLocal() as session:
        session.add(agent)
        await session.commit()
    return agent


async def _delete_agent(agent_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(delete(Agent).where(Agent.id == agent_id))
        await session.commit()


def _tool_payload(agent_id: uuid.UUID, **overrides) -> dict:
    return {
        "agent_id": str(agent_id),
        "name": f"net-scanner-{uuid.uuid4().hex[:8]}",
        "description": "Scans the local network and reports open ports",
        "file_path": "/root/.hermes/profiles/aegis/tools/net_scanner.py",
        "category": "network",
        **overrides,
    }


async def test_create_get_list_update_delete_tool(client: AsyncClient):
    agent = await _insert_agent()
    try:
        payload = _tool_payload(agent.id)
        resp = await client.post("/api/v1/tools", json=payload)
        assert resp.status_code == 201, resp.text
        created = resp.json()
        assert created["agent_name"] == agent.name
        assert created["status"] == "active"
        tool_id = created["id"]

        resp = await client.get(f"/api/v1/tools/{tool_id}")
        assert resp.status_code == 200
        assert resp.json()["file_path"] == payload["file_path"]

        resp = await client.get("/api/v1/tools", params={"agent_id": str(agent.id)})
        assert resp.status_code == 200
        assert [t["id"] for t in resp.json()] == [tool_id]

        resp = await client.get("/api/v1/tools", params={"q": payload["name"][:20]})
        assert any(t["id"] == tool_id for t in resp.json())

        resp = await client.patch(
            f"/api/v1/tools/{tool_id}", json={"status": "deprecated", "category": "monitoring"}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "deprecated"
        assert resp.json()["category"] == "monitoring"

        resp = await client.get("/api/v1/tools/categories")
        assert resp.status_code == 200
        assert "monitoring" in resp.json()

        resp = await client.delete(f"/api/v1/tools/{tool_id}")
        assert resp.status_code == 204
        resp = await client.get(f"/api/v1/tools/{tool_id}")
        assert resp.status_code == 404
    finally:
        await _delete_agent(agent.id)


async def test_scan_populates_registry(client: AsyncClient, monkeypatch):
    """Scan registers each scanned file once, resolving the responsible
    agent by profile slug and falling back to the coordinator (Athos in
    production; a test agent here) when the owner can't be determined.
    Categories come from the application-type classifier. Idempotent on
    re-scan."""
    from app.api.routes import tool as tool_routes

    owner_slug = f"test-owner-{uuid.uuid4().hex[:8]}"
    fallback_slug = f"test-fallback-{uuid.uuid4().hex[:8]}"
    owner = await _insert_agent(profile_slug=owner_slug)
    fallback = await _insert_agent(profile_slug=fallback_slug)

    entries = [
        {
            "name": "net_scanner.sh",
            "agent": owner_slug,
            "path": f"/profiles/{owner_slug}/scripts/net_scanner.sh",
            "exists": True,
            "description": "Scans the network for open ports",
        },
        {
            # Simulates a script whose owning profile the scan couldn't
            # determine (agent=None) -- exercises the fallback-to-Athos path,
            # regardless of which profile dir it physically sits under.
            "name": "orphan_report.sh",
            "agent": None,
            "path": "/profiles/some-other-profile/scripts/orphan_report.sh",
            "exists": True,
            "description": None,
        },
    ]
    monkeypatch.setattr(tool_routes, "FALLBACK_PROFILE_SLUG", fallback_slug)
    monkeypatch.setattr(tool_routes, "_scan_script_paths", lambda: entries)
    monkeypatch.setattr(tool_routes, "_load_all_cron_jobs", lambda: [])

    try:
        resp = await client.post("/api/v1/tools/scan")
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"scanned": 2, "created": 2, "skipped": 0}

        resp = await client.get("/api/v1/tools", params={"agent_id": str(owner.id)})
        [scanner] = resp.json()
        assert scanner["name"] == "net_scanner.sh"
        assert scanner["category"] == "network"

        resp = await client.get("/api/v1/tools", params={"agent_id": str(fallback.id)})
        [orphan] = resp.json()
        assert orphan["name"] == "orphan_report.sh"
        assert orphan["category"] == "reporting"
        assert "review" in orphan["description"]

        # Re-scan: nothing new, nothing duplicated.
        resp = await client.post("/api/v1/tools/scan")
        assert resp.json() == {"scanned": 2, "created": 0, "skipped": 2}
    finally:
        await _delete_agent(owner.id)
        await _delete_agent(fallback.id)


async def test_create_tool_validations(client: AsyncClient):
    agent = await _insert_agent()
    try:
        # Unknown responsible agent
        resp = await client.post("/api/v1/tools", json=_tool_payload(uuid.uuid4()))
        assert resp.status_code == 404

        # Invalid status
        resp = await client.post(
            "/api/v1/tools", json=_tool_payload(agent.id, status="bogus")
        )
        assert resp.status_code == 400

        # Duplicate name for the same agent
        payload = _tool_payload(agent.id)
        resp = await client.post("/api/v1/tools", json=payload)
        assert resp.status_code == 201, resp.text
        resp = await client.post("/api/v1/tools", json=payload)
        assert resp.status_code == 409
    finally:
        await _delete_agent(agent.id)


async def test_content_refuses_paths_outside_catalogs(client: AsyncClient):
    agent = await _insert_agent()
    try:
        resp = await client.post(
            "/api/v1/tools", json=_tool_payload(agent.id, file_path="/tmp/rogue.py")
        )
        assert resp.status_code == 201, resp.text
        tool_id = resp.json()["id"]

        resp = await client.get(f"/api/v1/tools/{tool_id}/content")
        assert resp.status_code == 400

        resp = await client.put(
            f"/api/v1/tools/{tool_id}/content", json={"content": "print('x')"}
        )
        assert resp.status_code == 400

        # delete_file=true must still remove the registry entry even though
        # the file is unreachable from the container.
        resp = await client.delete(f"/api/v1/tools/{tool_id}?delete_file=true")
        assert resp.status_code == 204
        resp = await client.get(f"/api/v1/tools/{tool_id}")
        assert resp.status_code == 404
    finally:
        await _delete_agent(agent.id)

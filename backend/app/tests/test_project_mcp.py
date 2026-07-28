"""Tests for project-scoped MCP server routes (app/api/routes/project.py's
mcp-servers section) -- Claude Code's `.mcp.json`, backed by the host-bridge
write path (`host-bridge/app.py`'s `/v1/project-mcp-servers*`).

Unlike `test_agent_mcp.py` (pure filesystem, no network), this domain's
actual file write happens through the real host-bridge over HTTP (see
db/models/project_mcp.py's docstring for why: a project's
working_directory_path isn't guaranteed reachable from the backend
container, so ForgeHub never writes it directly). These tests hit the real
running host-bridge and a real temp directory on the host filesystem --
per this repo's no-mocking test convention -- so they only pass with
`./dev.sh` (or an equivalent host-bridge) actually running and reachable at
settings.CHAT_BRIDGE_URL.
"""
import tempfile
import uuid
from datetime import date

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.routes import project as project_routes
from app.db.base import AsyncSessionLocal, Base, engine
from app.db.models.product import Product, ProductVersion
from app.db.models.project import Project
from app.db.models.project_mcp import ProjectMcpServer
from app.main import app

_ALREADY_WIRED = any(
    getattr(route, "path", "").startswith("/api/v1/projects") for route in app.router.routes
)
if not _ALREADY_WIRED:
    app.include_router(project_routes.router)

_STUB_PRODUCT_VERSION_ID: uuid.UUID | None = None
_STUB_PRODUCT_ID: uuid.UUID | None = None
_created_project_ids: list[uuid.UUID] = []


@pytest_asyncio.fixture(scope="module")
async def db_schema():
    global _STUB_PRODUCT_VERSION_ID, _STUB_PRODUCT_ID

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[Project.__table__, ProjectMcpServer.__table__],
            checkfirst=True,
        )

    async with AsyncSessionLocal() as session:
        product = Product(name=f"Project MCP Test Product {uuid.uuid4()}")
        session.add(product)
        await session.flush()
        version = ProductVersion(product_id=product.id, version="0.1.0")
        session.add(version)
        await session.commit()
        _STUB_PRODUCT_ID = product.id
        _STUB_PRODUCT_VERSION_ID = version.id

    yield

    async with engine.begin() as conn:
        if _created_project_ids:
            await conn.execute(
                text("DELETE FROM company.projects WHERE id = ANY(:ids)"),
                {"ids": _created_project_ids},
            )
        await conn.execute(
            text("DELETE FROM company.product_versions WHERE id = :id"),
            {"id": _STUB_PRODUCT_VERSION_ID},
        )
        await conn.execute(
            text("DELETE FROM company.products WHERE id = :id"), {"id": _STUB_PRODUCT_ID}
        )


@pytest_asyncio.fixture
async def client(db_schema, auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=auth_headers) as ac:
        yield ac


@pytest_asyncio.fixture
async def project(client: AsyncClient, tmp_path):
    """A real project row pointed at a real temp directory on the host --
    project_mcp_servers rows cascade-delete with it, so no separate cleanup
    is needed for those."""
    resp = await client.post(
        "/api/v1/projects",
        json={
            "name": f"MCP Project Test {uuid.uuid4()}",
            "product_version_id": str(_STUB_PRODUCT_VERSION_ID),
            "working_directory_path": str(tmp_path),
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    _created_project_ids.append(uuid.UUID(data["id"]))
    return data


async def test_upsert_writes_real_mcp_json(client: AsyncClient, project: dict, tmp_path):
    resp = await client.put(
        f"/api/v1/projects/{project['id']}/mcp-servers/my-server",
        json={
            "runtime_type": "claude",
            "transport": "stdio",
            "command": "run",
            "args": ["/root/x.py"],
            "env": {"K": "V"},
            "enabled": True,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "my-server"
    assert body["last_synced_at"] is not None
    assert body["last_sync_error"] is None

    mcp_json = (tmp_path / ".mcp.json").read_text()
    assert '"my-server"' in mcp_json
    assert '"run"' in mcp_json


async def test_list_reflects_db_rows(client: AsyncClient, project: dict):
    await client.put(
        f"/api/v1/projects/{project['id']}/mcp-servers/a",
        json={"runtime_type": "claude", "command": "run", "args": []},
    )
    resp = await client.get(f"/api/v1/projects/{project['id']}/mcp-servers")
    assert resp.status_code == 200
    names = [s["name"] for s in resp.json()]
    assert names == ["a"]


async def test_live_reflects_real_file(client: AsyncClient, project: dict):
    await client.put(
        f"/api/v1/projects/{project['id']}/mcp-servers/b",
        json={"runtime_type": "claude", "command": "run", "args": []},
    )
    resp = await client.get(f"/api/v1/projects/{project['id']}/mcp-servers/live")
    assert resp.status_code == 200
    body = resp.json()
    assert body["config_exists"] is True
    assert any(s["name"] == "b" for s in body["servers"])


async def test_delete_removes_row_and_file_entry(client: AsyncClient, project: dict, tmp_path):
    await client.put(
        f"/api/v1/projects/{project['id']}/mcp-servers/c",
        json={"runtime_type": "claude", "command": "run", "args": []},
    )
    resp = await client.delete(f"/api/v1/projects/{project['id']}/mcp-servers/c?runtime_type=claude")
    assert resp.status_code == 204

    list_resp = await client.get(f"/api/v1/projects/{project['id']}/mcp-servers")
    assert list_resp.json() == []
    assert '"c"' not in (tmp_path / ".mcp.json").read_text()


async def test_unsupported_runtime_rejected(client: AsyncClient, project: dict):
    resp = await client.put(
        f"/api/v1/projects/{project['id']}/mcp-servers/x",
        json={"runtime_type": "codex", "command": "run", "args": []},
    )
    assert resp.status_code == 400
    assert "codex" in resp.text


async def test_both_command_and_url_rejected(client: AsyncClient, project: dict):
    resp = await client.put(
        f"/api/v1/projects/{project['id']}/mcp-servers/x",
        json={"runtime_type": "claude", "command": "run", "url": "https://example/mcp"},
    )
    assert resp.status_code == 400


async def test_disabled_rejected_no_toggle(client: AsyncClient, project: dict):
    resp = await client.put(
        f"/api/v1/projects/{project['id']}/mcp-servers/x",
        json={"runtime_type": "claude", "command": "run", "enabled": False},
    )
    assert resp.status_code == 400


async def test_requires_working_directory_path(client: AsyncClient):
    resp = await client.post(
        "/api/v1/projects",
        json={
            "name": f"No Working Dir {uuid.uuid4()}",
            "product_version_id": str(_STUB_PRODUCT_VERSION_ID),
        },
    )
    assert resp.status_code == 201
    project_id = resp.json()["id"]
    _created_project_ids.append(uuid.UUID(project_id))

    put_resp = await client.put(
        f"/api/v1/projects/{project_id}/mcp-servers/x",
        json={"runtime_type": "claude", "command": "run"},
    )
    assert put_resp.status_code == 422

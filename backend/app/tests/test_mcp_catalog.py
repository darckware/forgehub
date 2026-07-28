"""Tests for the MCP catalog (app/api/routes/mcp_catalog.py).

**Deliberately does NOT exercise `apply_to_all_agents=True` end-to-end.**
`apply_global_server_to_all_agents` (core/mcp_catalog_apply.py) queries
every active `Agent` row in the shared `company_postgres` database -- which
in this environment includes the real, in-use Athos/Porthos/Atlas/etc.
agents, each with a real config file on the real host. A test that sets
`apply_to_all_agents=True` would write a throwaway test server into every
one of those real files on every test run (confirmed by hand while building
this feature -- see the manual verification note in the plan/PR). That is
not an acceptable side effect of running `pytest`, so this module only
covers: catalog CRUD (with `apply_to_all_agents=False`), explicit
single-target assign/unassign against disposable test-only agents/projects
created and torn down by each test, and the validation/error paths. The
"apply to all, including future agents" behavior itself is verified
manually against real data, not by an automated test that could otherwise
run unattended against the real roster.
"""
import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, text

from app.db.base import AsyncSessionLocal, Base, engine
from app.db.models.agent import Agent
from app.db.models.mcp_catalog import McpCatalogAssignment, McpCatalogServer
from app.db.models.product import Product, ProductVersion
from app.db.models.project import Project
from app.db.models.project_mcp import ProjectMcpServer
from app.main import app

_MY_TABLES = [McpCatalogServer.__table__, McpCatalogAssignment.__table__]

_STUB_PRODUCT_VERSION_ID: uuid.UUID | None = None
_STUB_PRODUCT_ID: uuid.UUID | None = None
_created_project_ids: list[uuid.UUID] = []


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _ensure_tables():
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_MY_TABLES, checkfirst=True))
    yield


@pytest_asyncio.fixture(scope="module")
async def db_schema():
    global _STUB_PRODUCT_VERSION_ID, _STUB_PRODUCT_ID
    async with AsyncSessionLocal() as session:
        product = Product(name=f"MCP Catalog Test Product {uuid.uuid4()}")
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
                text("DELETE FROM company.projects WHERE id = ANY(:ids)"), {"ids": _created_project_ids}
            )
        await conn.execute(
            text("DELETE FROM company.product_versions WHERE id = :id"), {"id": _STUB_PRODUCT_VERSION_ID}
        )
        await conn.execute(text("DELETE FROM company.products WHERE id = :id"), {"id": _STUB_PRODUCT_ID})


@pytest_asyncio.fixture
async def client(db_schema, auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=auth_headers) as ac:
        yield ac


@pytest_asyncio.fixture
async def cleanup_agent_ids():
    created_ids: list[uuid.UUID] = []
    yield created_ids
    if created_ids:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Agent).where(Agent.id.in_(created_ids)))
            await db.commit()


@pytest_asyncio.fixture
async def cleanup_server_ids():
    created_ids: list[uuid.UUID] = []
    yield created_ids
    if created_ids:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(McpCatalogServer).where(McpCatalogServer.id.in_(created_ids)))
            await db.commit()


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


async def _make_test_agent(client: AsyncClient, cleanup_agent_ids: list, tmp_path) -> dict:
    """A disposable agent whose config file lives entirely under tmp_path --
    never a real registered agent, so writes here can never touch a real
    config file on the host."""
    home = tmp_path / "agenthome"
    home.mkdir()
    create_resp = await client.post("/api/v1/agents", json={"name": _unique("mcp-catalog-agent")})
    assert create_resp.status_code == 201, create_resp.text
    agent = create_resp.json()
    cleanup_agent_ids.append(uuid.UUID(agent["id"]))
    patch_resp = await client.patch(
        f"/api/v1/agents/{agent['id']}",
        json={"runtime_type": "claude", "home_path": str(home)},
    )
    assert patch_resp.status_code == 200, patch_resp.text
    return patch_resp.json()


async def _make_test_project(client: AsyncClient, tmp_path) -> dict:
    resp = await client.post(
        "/api/v1/projects",
        json={
            "name": _unique("MCP Catalog Test Project"),
            "product_version_id": str(_STUB_PRODUCT_VERSION_ID),
            "working_directory_path": str(tmp_path),
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    _created_project_ids.append(uuid.UUID(data["id"]))
    return data


async def _create_server(client: AsyncClient, cleanup_server_ids: list, **overrides) -> dict:
    payload = {
        "name": _unique("catalog-server"),
        "description": "test",
        "transport": "stdio",
        "command": "echo",
        "args": ["hi"],
        "env": {"K": "V"},
        "apply_to_all_agents": False,
    }
    payload.update(overrides)
    resp = await client.post("/api/v1/mcp-catalog/servers", json=payload)
    assert resp.status_code == 201, resp.text
    server = resp.json()
    cleanup_server_ids.append(uuid.UUID(server["id"]))
    return server


async def test_create_list_update_delete_server(client: AsyncClient, cleanup_server_ids):
    server = await _create_server(client, cleanup_server_ids)
    assert server["apply_to_all_agents"] is False

    list_resp = await client.get("/api/v1/mcp-catalog/servers")
    assert list_resp.status_code == 200
    assert any(s["id"] == server["id"] for s in list_resp.json())

    update_resp = await client.put(
        f"/api/v1/mcp-catalog/servers/{server['id']}",
        json={
            "name": server["name"],
            "transport": "stdio",
            "command": "echo",
            "args": ["updated"],
            "apply_to_all_agents": False,
        },
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["args"] == ["updated"]

    delete_resp = await client.delete(f"/api/v1/mcp-catalog/servers/{server['id']}")
    assert delete_resp.status_code == 204
    cleanup_server_ids.remove(uuid.UUID(server["id"]))

    get_resp = await client.get("/api/v1/mcp-catalog/servers")
    assert not any(s["id"] == server["id"] for s in get_resp.json())


async def test_duplicate_name_rejected(client: AsyncClient, cleanup_server_ids):
    server = await _create_server(client, cleanup_server_ids)
    dup_resp = await client.post(
        "/api/v1/mcp-catalog/servers",
        json={"name": server["name"], "command": "echo", "args": []},
    )
    assert dup_resp.status_code == 409


async def test_both_command_and_url_rejected(client: AsyncClient):
    resp = await client.post(
        "/api/v1/mcp-catalog/servers",
        json={"name": _unique("bad"), "command": "echo", "url": "https://example/mcp"},
    )
    assert resp.status_code == 400


async def test_assign_to_agent_writes_real_file_and_unassign_removes_it(
    client: AsyncClient, cleanup_server_ids, cleanup_agent_ids, tmp_path
):
    server = await _create_server(client, cleanup_server_ids)
    agent = await _make_test_agent(client, cleanup_agent_ids, tmp_path)

    assign_resp = await client.post(
        f"/api/v1/mcp-catalog/servers/{server['id']}/assign",
        json={"target_type": "agent", "target_id": agent["id"]},
    )
    assert assign_resp.status_code == 201, assign_resp.text
    assignment = assign_resp.json()
    assert assignment["last_sync_error"] is None
    assert assignment["last_synced_at"] is not None

    # in_parent=True for claude: config lands beside the home dir, i.e. in
    # tmp_path itself (home_path was tmp_path/"agenthome" -- see
    # _make_test_agent).
    config_path = tmp_path / ".claude.json"
    written = config_path.read_text()
    assert server["name"] in written

    assignments_resp = await client.get(f"/api/v1/mcp-catalog/servers/{server['id']}/assignments")
    assert len(assignments_resp.json()) == 1

    unassign_resp = await client.delete(
        f"/api/v1/mcp-catalog/servers/{server['id']}/assign/{assignment['id']}"
    )
    assert unassign_resp.status_code == 204

    written_after = config_path.read_text()
    assert server["name"] not in written_after


async def test_assign_to_agent_with_no_runtime_records_sync_error(
    client: AsyncClient, cleanup_server_ids, cleanup_agent_ids
):
    server = await _create_server(client, cleanup_server_ids)
    create_resp = await client.post("/api/v1/agents", json={"name": _unique("mcp-catalog-bare-agent")})
    agent = create_resp.json()
    cleanup_agent_ids.append(uuid.UUID(agent["id"]))

    assign_resp = await client.post(
        f"/api/v1/mcp-catalog/servers/{server['id']}/assign",
        json={"target_type": "agent", "target_id": agent["id"]},
    )
    assert assign_resp.status_code == 201
    body = assign_resp.json()
    assert body["last_sync_error"] is not None
    assert body["last_synced_at"] is None


async def test_assign_to_project_writes_real_mcp_json(
    client: AsyncClient, cleanup_server_ids, tmp_path
):
    server = await _create_server(client, cleanup_server_ids)
    project = await _make_test_project(client, tmp_path)

    assign_resp = await client.post(
        f"/api/v1/mcp-catalog/servers/{server['id']}/assign",
        json={"target_type": "project", "target_id": project["id"], "runtime_type": "claude"},
    )
    assert assign_resp.status_code == 201, assign_resp.text
    assert assign_resp.json()["last_sync_error"] is None

    mcp_json = (tmp_path / ".mcp.json").read_text()
    assert server["name"] in mcp_json

    # Cleanup: the DB-side ProjectMcpServer row cascades with the project
    # (ondelete CASCADE), so nothing extra to delete here.


async def test_assign_unknown_target_type_rejected(client: AsyncClient, cleanup_server_ids):
    server = await _create_server(client, cleanup_server_ids)
    resp = await client.post(
        f"/api/v1/mcp-catalog/servers/{server['id']}/assign",
        json={"target_type": "product", "target_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 400


async def test_assign_missing_agent_404s(client: AsyncClient, cleanup_server_ids):
    server = await _create_server(client, cleanup_server_ids)
    resp = await client.post(
        f"/api/v1/mcp-catalog/servers/{server['id']}/assign",
        json={"target_type": "agent", "target_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404


async def test_assign_to_missing_server_404s(client: AsyncClient):
    resp = await client.post(
        f"/api/v1/mcp-catalog/servers/{uuid.uuid4()}/assign",
        json={"target_type": "agent", "target_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404

"""Tests for the toolversions endpoints (install and update)."""
import httpx
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('test-toolversions')}"}


@pytest_asyncio.fixture(autouse=True)
async def preserve_tool_version_rows():
    """Snapshot and restore company.tool_version_status so tests never pollute
    the real Dashboard tool versions table."""
    from sqlalchemy import delete, select

    from app.db.base import AsyncSessionLocal
    from app.db.models.toolversions import ToolVersionStatus

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(ToolVersionStatus))).scalars().all()
        snapshot = [
            {
                "id": r.id,
                "tool": r.tool,
                "installed_version": r.installed_version,
                "latest_version": r.latest_version,
                "update_available": r.update_available,
                "last_error": r.last_error,
            }
            for r in rows
        ]

    yield

    async with AsyncSessionLocal() as db:
        await db.execute(delete(ToolVersionStatus))
        for item in snapshot:
            db.add(ToolVersionStatus(**item))
        await db.commit()


@pytest_asyncio.fixture
async def client():
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=_auth_headers()) as ac:
        yield ac


async def test_install_tool_not_found(client: AsyncClient):
    resp = await client.post("/api/v1/tool-versions/non_existent_tool/install")
    assert resp.status_code == 404


async def test_install_tool_success_preserves_other_tools(client: AsyncClient, monkeypatch):
    import app.api.routes.toolversions as tv_route
    from app.db.base import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        agy_row = await tv_route._get_or_create_status_row(db, "antigravity")
        agy_row.installed_version = "1.4.2"
        agy_row.latest_version = "1.4.2"
        agy_row.update_available = False
        agy_row.last_error = None
        await db.commit()

    def bridge_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/tool-versions/install":
            return httpx.Response(200, json={"success": True, "output": "installed ok", "error": None})
        if request.url.path == "/v1/tool-versions":
            return httpx.Response(200, json={
                "pi": {
                    "installed_version": "0.85.1",
                    "latest_version": "0.85.1",
                    "update_available": False,
                    "error": None
                }
            })
        return httpx.Response(404, json={"detail": "not found"})

    real_async_client = httpx.AsyncClient

    def bridge_client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(bridge_handler)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(tv_route.httpx, "AsyncClient", bridge_client_factory)

    resp = await client.post("/api/v1/tool-versions/pi/install")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["output"] == "installed ok"
    assert data["error"] is None
    assert data["status"]["tool"] == "pi"
    assert data["status"]["installed_version"] == "0.85.1"

    list_resp = await client.get("/api/v1/tool-versions")
    assert list_resp.status_code == 200
    by_tool = {item["tool"]: item for item in list_resp.json()}
    assert by_tool["antigravity"]["installed_version"] == "1.4.2"


async def test_poll_tools_includes_antigravity_non_mutating(monkeypatch):
    import app.api.routes.toolversions as tv_route
    from app.db.base import AsyncSessionLocal

    assert "antigravity" in tv_route.POLL_TOOLS
    assert tv_route.POLL_NO_MUTATE == ("antigravity",)

    captured_params: dict[str, str] = {}

    def bridge_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/tool-versions":
            captured_params.update(dict(request.url.params))
            return httpx.Response(
                200,
                json={
                    tool: {
                        "installed_version": "1.4.2" if tool == "antigravity" else "1.0.0",
                        "latest_version": "1.4.2" if tool == "antigravity" else "1.0.0",
                        "update_available": False,
                        "error": None,
                    }
                    for tool in tv_route.POLL_TOOLS
                },
            )
        return httpx.Response(404, json={"detail": "not found"})

    real_async_client = httpx.AsyncClient

    def bridge_client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(bridge_handler)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(tv_route.httpx, "AsyncClient", bridge_client_factory)

    async with AsyncSessionLocal() as db:
        rows = await tv_route.refresh_all_tool_versions(
            db, tools=tv_route.POLL_TOOLS, no_mutate=tv_route.POLL_NO_MUTATE
        )
    by_tool = {r.tool: r for r in rows}
    assert "antigravity" in captured_params.get("tools", "").split(",")
    assert captured_params.get("no_mutate") == "antigravity"
    assert by_tool["antigravity"].installed_version == "1.4.2"


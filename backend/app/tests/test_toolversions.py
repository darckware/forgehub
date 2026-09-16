"""Tests for the toolversions endpoints (install and update)."""
import httpx
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('test-toolversions')}"}


@pytest_asyncio.fixture
async def client():
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=_auth_headers()) as ac:
        yield ac


async def test_install_tool_not_found(client: AsyncClient):
    resp = await client.post("/api/v1/tool-versions/non_existent_tool/install")
    assert resp.status_code == 404


async def test_install_tool_success(client: AsyncClient, monkeypatch):
    import app.api.routes.toolversions as tv_route

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

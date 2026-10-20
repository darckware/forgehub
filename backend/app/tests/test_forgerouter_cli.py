"""Tests for ForgeRouter Global CLI status and toggle endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient
import httpx

from app.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.asyncio
async def test_forgerouter_cli_status_and_toggle(monkeypatch):
    status_state = {"claude": False, "codex": False, "antigravity": False}

    async def fake_request(client_self, method, url, **kwargs):
        url_str = str(url)
        if "/v1/forgerouter/cli-status" in url_str:
            return httpx.Response(200, json=status_state)
        elif "/v1/forgerouter/cli-toggle" in url_str:
            json_body = kwargs.get("json", {})
            tool = json_body.get("tool")
            enabled = json_body.get("enabled", False)
            if tool in status_state:
                status_state[tool] = enabled
            return httpx.Response(
                200,
                json={
                    "tool": tool,
                    "enabled": enabled,
                    "config_path": f"/root/.{tool}/config",
                    "status": dict(status_state),
                },
            )
        return httpx.Response(404, text="Not Found")

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # GET status initial
        resp = await ac.get("/api/v1/forgerouter/cli-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data == {"claude": False, "codex": False, "antigravity": False}

        # PUT toggle codex enable
        resp = await ac.put(
            "/api/v1/forgerouter/cli-toggle",
            json={"tool": "codex", "enabled": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tool"] == "codex"
        assert data["enabled"] is True
        assert data["status"]["codex"] is True

        # GET status after toggle
        resp = await ac.get("/api/v1/forgerouter/cli-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["codex"] is True

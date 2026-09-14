"""Tests for the auth domain: login, and /auth/me's session-refresh
contract (previously returned access_token="" -- a no-op that made the
frontend's activity-based sliding session impossible; see
useSessionKeepAlive on the frontend)."""
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.security import decode_access_token


@pytest_asyncio.fixture
async def client():
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_login_then_me_reissues_a_fresh_access_token(client: AsyncClient, monkeypatch):
    async def accepted_captcha(token):
        return token == "synthetic-captcha"

    monkeypatch.setattr("app.api.routes.auth.verify_recaptcha", accepted_captcha)
    resp = await client.post(
        "/api/v1/auth/token",
        data={"username": settings.DEV_USER_USERNAME, "password": settings.DEV_USER_PASSWORD,
              "recaptcha_token": "synthetic-captcha"},
    )
    assert resp.status_code == 200, resp.text
    original_token = resp.json()["access_token"]

    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {original_token}"})
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["access_token"], "must not be blank -- this is the sliding-session refresh"
    payload = decode_access_token(body["access_token"])
    assert payload is not None
    assert payload["sub"] == settings.DEV_USER_USERNAME


async def test_me_requires_a_valid_token(client: AsyncClient):
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401

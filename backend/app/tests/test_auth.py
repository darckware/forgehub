"""Tests for the auth domain: login, and /auth/me's session-refresh
contract (previously returned access_token="" -- a no-op that made the
frontend's activity-based sliding session impossible; see
useSessionKeepAlive on the frontend)."""
import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.security import decode_access_token, hash_password
from app.db.base import AsyncSessionLocal
from app.db.models.user import User


@pytest_asyncio.fixture
async def client():
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def login_user():
    """A throwaway active user with a known password. The test used to log
    in as .env's DEV_USER_USERNAME, which only works while that seeded row
    is active (or absent): once the real 'admin' account was deactivated,
    login correctly refused it and this test 401'd for a reason unrelated
    to what it checks."""
    username = f"test-login-{uuid.uuid4().hex[:12]}"
    password = uuid.uuid4().hex
    async with AsyncSessionLocal() as db:
        db.add(User(username=username, hashed_password=hash_password(password)))
        await db.commit()
    yield username, password
    async with AsyncSessionLocal() as db:
        await db.execute(delete(User).where(User.username == username))
        await db.commit()


async def test_login_then_me_reissues_a_fresh_access_token(client: AsyncClient, monkeypatch, login_user):
    async def accepted_captcha(token):
        return token == "synthetic-captcha"

    username, password = login_user
    monkeypatch.setattr("app.api.routes.auth.verify_recaptcha", accepted_captcha)
    resp = await client.post(
        "/api/v1/auth/token",
        data={"username": username, "password": password, "recaptcha_token": "synthetic-captcha"},
    )
    assert resp.status_code == 200, resp.text
    original_token = resp.json()["access_token"]

    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {original_token}"})
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["access_token"], "must not be blank -- this is the sliding-session refresh"
    payload = decode_access_token(body["access_token"])
    assert payload is not None
    assert payload["sub"] == username


async def test_me_requires_a_valid_token(client: AsyncClient):
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401

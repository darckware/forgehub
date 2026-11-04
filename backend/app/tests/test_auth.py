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
        from app.db.models.governance import AuditEvent
        await db.execute(delete(AuditEvent).where(AuditEvent.entity_type == "user_access", AuditEvent.actor == username))
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


async def test_login_session_can_be_revoked(client, monkeypatch, login_user):
    async def accepted_captcha(token):
        return True

    monkeypatch.setattr("app.api.routes.auth.verify_recaptcha", accepted_captcha)
    username, password = login_user
    response = await client.post("/api/v1/auth/token", data={"username": username, "password": password})
    assert response.status_code == 200
    token = response.json()["access_token"]
    user_id = response.json()["user"]["id"]
    headers = {"Authorization": f"Bearer {token}"}
    refreshed = await client.get("/api/v1/auth/me", headers=headers)
    assert refreshed.status_code == 200
    refreshed_headers = {"Authorization": f"Bearer {refreshed.json()['access_token']}"}
    response = await client.get(f"/api/v1/users/{user_id}/sessions", headers=headers)
    assert response.status_code == 200
    sessions = response.json()
    assert len(sessions) == 1
    assert sessions[0]["is_current"] is True
    response = await client.delete(f"/api/v1/users/{user_id}/sessions/{sessions[0]['id']}", headers=headers)
    assert response.status_code in (200, 204)
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401
    assert (await client.get("/api/v1/auth/me", headers=refreshed_headers)).status_code == 401


async def test_sessions_are_private_and_all_can_be_revoked(client, monkeypatch, login_user):
    from app.core.security import create_access_token

    async def accepted_captcha(token):
        return True

    monkeypatch.setattr("app.api.routes.auth.verify_recaptcha", accepted_captcha)
    username, password = login_user
    first = (await client.post("/api/v1/auth/token", data={"username": username, "password": password})).json()
    second = (await client.post("/api/v1/auth/token", data={"username": username, "password": password})).json()
    user_id = first["user"]["id"]
    first_headers = {"Authorization": f"Bearer {first['access_token']}"}
    second_headers = {"Authorization": f"Bearer {second['access_token']}"}
    assert (await client.get(f"/api/v1/users/{uuid.uuid4()}/sessions", headers=first_headers)).status_code == 403
    assert (await client.delete(f"/api/v1/users/{uuid.uuid4()}/sessions", headers=first_headers)).status_code == 403
    assert (await client.delete(f"/api/v1/users/{user_id}/sessions", headers=first_headers)).status_code == 204
    assert (await client.get("/api/v1/auth/me", headers=second_headers)).status_code == 401
    legacy_headers = {"Authorization": f"Bearer {create_access_token(username)}"}
    assert (await client.get("/api/v1/auth/me", headers=legacy_headers)).status_code == 200


async def test_session_limit_and_remember_me(client, monkeypatch, login_user):
    from app.core.config import settings
    from app.db.models.user_session import UserSession
    from sqlalchemy import select

    async def accepted_captcha(token):
        return True

    monkeypatch.setattr("app.api.routes.auth.verify_recaptcha", accepted_captcha)
    monkeypatch.setattr(settings, "SESSION_MAX_CONCURRENT", 1)
    monkeypatch.setattr(settings, "SESSION_REMEMBER_DAYS", 14)
    username, password = login_user
    first = (await client.post("/api/v1/auth/token", data={"username": username, "password": password})).json()
    second = (await client.post("/api/v1/auth/token", data={"username": username, "password": password, "remember_me": "true"})).json()
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {first['access_token']}"})).status_code == 401
    token = second["access_token"]
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})).status_code == 200
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(UserSession).where(UserSession.user_id == uuid.UUID(second["user"]["id"])))).scalars().all()
        assert sum(row.is_active for row in rows) == 1
        active = next(row for row in rows if row.is_active)
        assert active.remember_me
        assert (active.expires_at - active.created_at).days >= 13


async def test_login_audit_does_not_record_secrets(client, monkeypatch, login_user, admin_headers):
    from sqlalchemy import select
    from app.db.models.governance import AuditEvent

    async def accepted_captcha(token):
        return True

    monkeypatch.setattr("app.api.routes.auth.verify_recaptcha", accepted_captcha)
    username, password = login_user
    try:
        await client.post("/api/v1/auth/token", data={"username": username, "password": "wrong-password"}, headers={"User-Agent": "audit-test"})
        response = await client.post("/api/v1/auth/token", data={"username": username, "password": password}, headers={"User-Agent": "audit-test"})
        token = response.json()["access_token"]
        user_headers = {"Authorization": f"Bearer {token}"}
        assert (await client.get("/api/v1/users/audit/events", headers=user_headers)).status_code == 403
        audit = await client.get("/api/v1/users/audit/events", params={"actor": username, "event": "login_refused"}, headers=admin_headers)
        assert audit.status_code == 200 and all(row["event"] == "login_refused" for row in audit.json())
        assert audit.json()
        await client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}", "User-Agent": "audit-test"})
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(select(AuditEvent).where(AuditEvent.entity_type == "user_access", AuditEvent.actor == username))).scalars().all()
            assert {row.event_type for row in rows} >= {"login_accepted", "login_refused", "logout"}
            assert all(row.payload["user_agent"] == "audit-test" for row in rows)
            assert password not in str([row.payload for row in rows])
            assert token not in str([row.payload for row in rows])
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AuditEvent).where(AuditEvent.entity_type == "user_access", AuditEvent.actor == username))
            await db.commit()

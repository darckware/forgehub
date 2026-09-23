"""Unit and integration tests for TOTP 2FA."""
import pyotp
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.core.totp import (
    generate_recovery_codes,
    generate_totp_secret,
    hash_recovery_code,
    verify_recovery_code,
    verify_totp_code,
)
from app.db.base import AsyncSessionLocal
from app.db.models.user import User


@pytest_asyncio.fixture
async def client():
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def auth_headers():
    token = create_access_token(subject=settings.DEV_USER_USERNAME)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_totp_helpers():
    secret = generate_totp_secret()
    assert secret and len(secret) == 32
    totp = pyotp.TOTP(secret)
    code = totp.now()
    assert verify_totp_code(secret, code) is True
    assert verify_totp_code(secret, "000000") is False

    codes = generate_recovery_codes(4)
    assert len(codes) == 4
    for c in codes:
        assert len(c) == 8
        h = hash_recovery_code(c)
        assert verify_recovery_code(c, h) is True
        assert verify_recovery_code("WRONGCOD", h) is False


@pytest.mark.asyncio
async def test_totp_setup_and_flow(client: AsyncClient, monkeypatch):
    test_username = "test_totp_user"
    test_password = "SecretPassword123!"

    # Ensure clean slate
    async with AsyncSessionLocal() as db:
        await db.execute(delete(User).where(User.username == test_username))
        user = User(
            username=test_username,
            hashed_password=hash_password(test_password),
            full_name="TOTP Tester",
            is_active=True,
            is_admin=False,
            totp_enabled=False,
        )
        db.add(user)
        await db.commit()

    try:
        user_token = create_access_token(subject=test_username)
        user_headers = {"Authorization": f"Bearer {user_token}"}

        # 1. Setup
        resp = await client.post("/api/v1/auth/totp/setup", headers=user_headers)
        assert resp.status_code == 200, resp.text
        setup_data = resp.json()
        assert "secret" in setup_data
        assert "qr_code_data_url" in setup_data
        assert len(setup_data["recovery_codes"]) == 8

        secret = setup_data["secret"]
        totp = pyotp.TOTP(secret)
        valid_code = totp.now()

        # 2. Enable with invalid code
        resp = await client.post(
            "/api/v1/auth/totp/enable",
            headers=user_headers,
            json={"secret": secret, "code": "000000"},
        )
        assert resp.status_code == 400

        # 3. Enable with valid code and passing recovery_codes
        resp = await client.post(
            "/api/v1/auth/totp/enable",
            headers=user_headers,
            json={"secret": secret, "code": valid_code, "recovery_codes": setup_data["recovery_codes"]},
        )
        assert resp.status_code == 200
        assert resp.json() == {"enabled": True}

        # Verify DB state
        async with AsyncSessionLocal() as db:
            refreshed = (await db.execute(select(User).where(User.username == test_username))).scalar_one()
            assert refreshed.totp_enabled is True
            assert refreshed.totp_secret == secret

        # 4. Login requires TOTP
        async def mock_captcha(token):
            return True

        monkeypatch.setattr("app.api.routes.auth.verify_recaptcha", mock_captcha)
        resp = await client.post(
            "/api/v1/auth/token",
            data={"username": test_username, "password": test_password},
        )
        assert resp.status_code == 200
        login_res = resp.json()
        assert login_res["requires_totp"] is True
        pending_token = login_res["totp_pending_token"]
        assert pending_token is not None

        # 5. Verify step with invalid code
        resp = await client.post(
            "/api/v1/auth/totp/verify",
            json={"totp_pending_token": pending_token, "code": "000000"},
        )
        assert resp.status_code == 401

        # 6. Verify step with recovery code (with formatting/spaces)
        recovery_code = setup_data["recovery_codes"][0]
        formatted_recovery = f"  {recovery_code[:4]}-{recovery_code[4:]}  "
        resp = await client.post(
            "/api/v1/auth/totp/verify",
            json={"totp_pending_token": pending_token, "code": formatted_recovery},
        )
        assert resp.status_code == 200
        final_token = resp.json()["access_token"]
        assert final_token

        # 7. Disable TOTP
        resp = await client.post(
            "/api/v1/auth/totp/disable",
            headers={"Authorization": f"Bearer {final_token}"},
            json={"password": test_password, "code": totp.now()},
        )
        assert resp.status_code == 200
        assert resp.json() == {"enabled": False}

        # Verify DB after disable
        async with AsyncSessionLocal() as db:
            refreshed = (await db.execute(select(User).where(User.username == test_username))).scalar_one()
            assert refreshed.totp_enabled is False
            assert refreshed.totp_secret is None

    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(User).where(User.username == test_username))
            await db.commit()

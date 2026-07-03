"""Shared fixtures for the API test suite.

main.py's RequireAuthMiddleware guards every /api/v1/* route with a bearer
token (it validates the JWT itself, not a user row), so every test client
must send one. Domain test files keep their own `client` fixture (some add
extra setup) and take `auth_headers` from here to build it.
"""
import pytest

from app.core.security import create_access_token


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('test-suite')}"}

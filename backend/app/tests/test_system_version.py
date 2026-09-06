"""Deployment identity exposed by the authenticated system API."""

import pytest_asyncio
import pytest
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def client():
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_system_version_reports_the_running_build(
    client: AsyncClient,
    auth_headers: dict[str, str],
    monkeypatch,
):
    monkeypatch.setenv("FORGEHUB_VERSION", "1.4.2")
    monkeypatch.setenv("FORGEHUB_GIT_SHA", "abc1234")
    monkeypatch.setenv("FORGEHUB_BUILD_DATE", "2026-09-06T15:00:00Z")

    response = await client.get("/api/v1/system/version", headers=auth_headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["app_version"] == "1.4.2"
    assert body["git_sha"] == "abc1234"
    assert body["git_commit_url"] == (
        "https://github.com/marcelodarckferreira/forgehub/commit/abc1234"
    )
    assert body["build_date"] == "2026-09-06T15:00:00Z"
    assert body["postgres_version"].startswith("PostgreSQL ")
    assert body["latest_migration_bundled"].endswith(".py")
    assert body["github_repo_url"] == (
        "https://github.com/marcelodarckferreira/forgehub"
    )


async def test_system_version_survives_postgres_introspection_failure(monkeypatch):
    from app.api.routes import system_info

    async def unavailable_postgres() -> str:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(system_info, "_get_postgres_version", unavailable_postgres)

    try:
        body = await system_info.system_version()
    except RuntimeError:
        pytest.fail("system version must remain available when PostgreSQL is down")

    assert body["postgres_version"] is None


def test_latest_bundled_migration_follows_the_alembic_graph(tmp_path, monkeypatch):
    from app.api.routes import system_info

    versions = tmp_path / "alembic" / "versions"
    versions.mkdir(parents=True)
    (versions / "z_base.py").write_text(
        'revision = "aaa"\ndown_revision = None\n',
        encoding="utf-8",
    )
    (versions / "a_actual_head.py").write_text(
        'revision = "zzz"\ndown_revision = "aaa"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(system_info, "_BACKEND_ROOT", tmp_path)

    assert system_info._latest_bundled_migration() == "a_actual_head.py"

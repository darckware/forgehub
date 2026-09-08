"""Nexo build-catalog routes with the host bridge replaced by a fixed fake."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core import nexo_builds
from app.core.config import settings
from app.core.deps import get_current_admin
from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.nexo_installation import NexoAgentBuild
from app.main import app


BUILD_TIMEOUT_SHA = "1234567890abcdef1234567890abcdef12345678"
TEST_SHAS = {character * 40 for character in "abcdef"} | {BUILD_TIMEOUT_SHA}


class FakeBridge:
    def __init__(self, artifact_root: Path) -> None:
        self.artifact_root = artifact_root
        self.git_sha = "a" * 40
        self.agent_version = "v1.2.3"
        self.build_calls: list[str] = []
        self._artifact_paths: dict[str, str] = {}
        self._artifact_bytes: dict[str, bytes] = {}
        self._returned_path: str | None = None
        self._reported_sha256: str | None = None
        self._failure: Exception | None = None
        self._build_failure: Exception | None = None

    def source(self, git_sha: str, agent_version: str) -> None:
        self.git_sha = git_sha
        self.agent_version = agent_version

    def build(self, os_kind: str, artifact_path: Path, content: bytes) -> None:
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_bytes(content)
        self._artifact_paths[os_kind] = artifact_path.relative_to(
            self.artifact_root
        ).as_posix()
        self._artifact_bytes[os_kind] = content

    def return_path(self, path: str) -> None:
        self._returned_path = path

    def report_sha256(self, sha256: str | None) -> None:
        self._reported_sha256 = sha256

    def fail(self, exc: Exception) -> None:
        self._failure = exc

    def fail_build(self, exc: Exception) -> None:
        self._build_failure = exc

    def handle(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Bridge-Token"] == settings.CHAT_BRIDGE_TOKEN
        if self._failure is not None:
            raise self._failure
        if request.method == "GET" and request.url.path == "/v1/nexo/source":
            return httpx.Response(
                200,
                json={"git_sha": self.git_sha, "agent_version": self.agent_version},
            )
        if request.method == "POST" and request.url.path.startswith("/v1/nexo/build/"):
            if self._build_failure is not None:
                raise self._build_failure
            os_kind = request.url.path.rsplit("/", 1)[-1]
            self.build_calls.append(os_kind)
            content = self._artifact_bytes.get(os_kind, os_kind.encode())
            artifact_path = self._artifact_paths.get(
                os_kind,
                f"{self.git_sha}/{os_kind}/nexo-remote-agent"
                + (".exe" if os_kind == "windows" else ""),
            )
            local_path = self.artifact_root / artifact_path
            if self._returned_path is None and not local_path.exists():
                local_path.parent.mkdir(parents=True, exist_ok=True)
                local_path.write_bytes(content)
            return httpx.Response(
                200,
                json={
                    "git_sha": self.git_sha,
                    "agent_version": self.agent_version,
                    "os_kind": os_kind,
                    "artifact_path": self._returned_path or artifact_path,
                    "artifact_size": len(content),
                    "sha256": self._reported_sha256
                    or hashlib.sha256(content).hexdigest(),
                    "log_excerpt": f"built {os_kind}",
                },
            )
        return httpx.Response(404, json={"detail": "not found"})


@pytest.fixture
def artifact_root(tmp_path: Path) -> Path:
    root = tmp_path / "artifacts"
    sentinel = object()
    original = settings.__dict__.get("NEXO_ARTIFACT_ROOT", sentinel)
    settings.__dict__["NEXO_ARTIFACT_ROOT"] = root
    yield root
    if original is sentinel:
        settings.__dict__.pop("NEXO_ARTIFACT_ROOT", None)
    else:
        settings.__dict__["NEXO_ARTIFACT_ROOT"] = original


@pytest.fixture
def fake_bridge(artifact_root: Path, monkeypatch: pytest.MonkeyPatch) -> FakeBridge:
    bridge = FakeBridge(artifact_root)

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(bridge.handle)
        return AsyncClient(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    return bridge


@pytest.fixture
def admin_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('nexo-build-admin')}"}


@pytest_asyncio.fixture
async def client():
    app.dependency_overrides[get_current_admin] = lambda: object()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http:
        yield http
    app.dependency_overrides.pop(get_current_admin, None)


@pytest_asyncio.fixture(autouse=True)
async def clean_build_rows():
    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(NexoAgentBuild).where(NexoAgentBuild.git_sha.in_(TEST_SHAS))
        )
        await db.commit()
    yield
    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(NexoAgentBuild).where(NexoAgentBuild.git_sha.in_(TEST_SHAS))
        )
        await db.commit()


@pytest.mark.asyncio
async def test_build_refresh_reuses_ready_sha_platform(
    client: AsyncClient,
    admin_headers: dict[str, str],
    fake_bridge: FakeBridge,
    artifact_root: Path,
) -> None:
    fake_bridge.source("a" * 40, "v1.2.3")
    fake_bridge.build(
        "linux",
        artifact_root / ("a" * 40) / "linux/nexo-remote-agent",
        b"linux",
    )

    first = await client.post("/api/v1/nexo-agent-builds", headers=admin_headers)
    second = await client.post("/api/v1/nexo-agent-builds", headers=admin_headers)

    assert first.status_code == second.status_code == 202
    assert fake_bridge.build_calls == ["linux", "windows"]
    async with AsyncSessionLocal() as db:
        rows = list(
            (
                await db.execute(
                    select(NexoAgentBuild)
                    .where(NexoAgentBuild.git_sha == "a" * 40)
                    .order_by(NexoAgentBuild.os_kind)
                )
            ).scalars()
        )
        assert [row.status for row in rows] == ["ready", "ready"]
        assert [row.artifact_path for row in rows] == [
            f"{'a' * 40}/linux/nexo-remote-agent",
            f"{'a' * 40}/windows/nexo-remote-agent.exe",
        ]


@pytest.mark.asyncio
async def test_build_refuses_artifact_outside_root(
    client: AsyncClient,
    admin_headers: dict[str, str],
    fake_bridge: FakeBridge,
) -> None:
    fake_bridge.source("b" * 40, "v1.2.3")
    fake_bridge.return_path("../../etc/passwd")

    response = await client.post("/api/v1/nexo-agent-builds", headers=admin_headers)

    assert response.status_code == 502

    async with AsyncSessionLocal() as db:
        failed = (
            await db.execute(
                select(NexoAgentBuild).where(
                    NexoAgentBuild.git_sha == "b" * 40,
                    NexoAgentBuild.os_kind == "linux",
                )
            )
        ).scalar_one()
        assert failed.status == "failed"
        assert failed.artifact_path is None
        assert failed.build_log_excerpt
        assert len(failed.build_log_excerpt) <= 2_000


@pytest.mark.asyncio
async def test_build_rechecks_checksum_before_marking_ready(
    client: AsyncClient,
    admin_headers: dict[str, str],
    fake_bridge: FakeBridge,
) -> None:
    fake_bridge.source("c" * 40, "v1.2.3")
    fake_bridge.report_sha256("0" * 64)

    response = await client.post("/api/v1/nexo-agent-builds", headers=admin_headers)

    assert response.status_code == 502
    async with AsyncSessionLocal() as db:
        failed = (
            await db.execute(
                select(NexoAgentBuild).where(
                    NexoAgentBuild.git_sha == "c" * 40,
                    NexoAgentBuild.os_kind == "linux",
                )
            )
        ).scalar_one()
        assert failed.status == "failed"
        assert failed.sha256 is None


@pytest.mark.asyncio
async def test_catalog_never_returns_storage_paths(
    client: AsyncClient,
    admin_headers: dict[str, str],
    fake_bridge: FakeBridge,
) -> None:
    fake_bridge.source("d" * 40, "v2.0.0")
    refresh = await client.post("/api/v1/nexo-agent-builds", headers=admin_headers)
    assert refresh.status_code == 202

    response = await client.get("/api/v1/nexo-agent-builds", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["source"] == {"git_sha": "d" * 40, "agent_version": "v2.0.0"}
    builds = [
        build for build in response.json()["builds"] if build["git_sha"] == "d" * 40
    ]
    assert {build["os_kind"] for build in builds} == {"linux", "windows"}
    assert all("artifact_path" not in build for build in builds)


@pytest.mark.asyncio
async def test_source_timeout_returns_safe_gateway_timeout(
    client: AsyncClient,
    admin_headers: dict[str, str],
    fake_bridge: FakeBridge,
) -> None:
    fake_bridge.fail(httpx.ReadTimeout("secret host detail"))

    response = await client.post("/api/v1/nexo-agent-builds", headers=admin_headers)

    assert response.status_code == 504, response.text
    assert response.json() == {"detail": "Nexo build bridge timed out"}


@pytest.mark.asyncio
async def test_failed_build_can_be_retried(
    client: AsyncClient,
    admin_headers: dict[str, str],
    fake_bridge: FakeBridge,
) -> None:
    fake_bridge.source("e" * 40, "v3.0.0")
    fake_bridge.report_sha256("0" * 64)
    first = await client.post("/api/v1/nexo-agent-builds", headers=admin_headers)
    assert first.status_code == 502

    fake_bridge.report_sha256(None)
    second = await client.post("/api/v1/nexo-agent-builds", headers=admin_headers)

    assert second.status_code == 202
    assert fake_bridge.build_calls == ["linux", "linux", "windows"]
    assert [build["status"] for build in second.json()] == ["ready", "ready"]


@pytest.mark.asyncio
async def test_build_timeout_is_persisted_as_a_safe_bounded_failure(
    client: AsyncClient,
    admin_headers: dict[str, str],
    fake_bridge: FakeBridge,
) -> None:
    fake_bridge.source(BUILD_TIMEOUT_SHA, "v3.1.0")
    fake_bridge.fail_build(httpx.ReadTimeout("credential-like private diagnostic"))

    response = await client.post("/api/v1/nexo-agent-builds", headers=admin_headers)

    assert response.status_code == 504, response.text
    assert response.json() == {"detail": "Nexo build bridge timed out"}
    async with AsyncSessionLocal() as db:
        failed = (
            await db.execute(
                select(NexoAgentBuild).where(
                    NexoAgentBuild.git_sha == BUILD_TIMEOUT_SHA,
                    NexoAgentBuild.os_kind == "linux",
                )
            )
        ).scalar_one()
        assert failed.status == "failed"
        assert failed.build_log_excerpt == "Nexo build bridge timed out"


@pytest.mark.asyncio
async def test_concurrent_refresh_does_not_launch_duplicate_builds(
    client: AsyncClient,
    admin_headers: dict[str, str],
    fake_bridge: FakeBridge,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_bridge.source("f" * 40, "v4.0.0")
    linux_started = asyncio.Event()
    release_linux = asyncio.Event()
    build_calls: list[str] = []

    async def delayed_build(os_kind: str) -> nexo_builds.VerifiedNexoBuild:
        build_calls.append(os_kind)
        if os_kind == "linux":
            linux_started.set()
            await release_linux.wait()
        content = os_kind.encode()
        return nexo_builds.VerifiedNexoBuild(
            git_sha="f" * 40,
            agent_version="v4.0.0",
            os_kind=os_kind,
            artifact_path=f"{'f' * 40}/{os_kind}/agent",
            artifact_size=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            log_excerpt="",
        )

    monkeypatch.setattr(nexo_builds, "build_platform", delayed_build)
    first_task = asyncio.create_task(
        client.post("/api/v1/nexo-agent-builds", headers=admin_headers)
    )
    await asyncio.wait_for(linux_started.wait(), timeout=2)

    second = await asyncio.wait_for(
        client.post("/api/v1/nexo-agent-builds", headers=admin_headers),
        timeout=2,
    )
    release_linux.set()
    first = await asyncio.wait_for(first_task, timeout=2)

    assert first.status_code == second.status_code == 202
    assert build_calls == ["linux", "windows"]

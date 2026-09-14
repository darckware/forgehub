"""Synthetic Nexo build-to-report flow without external infrastructure."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import httpx
import pytest
import yaml
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.api.routes.workstation import hash_device_token
from app.core.config import settings
from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.client import Client, Workstation
from app.db.models.nexo_installation import (
    NexoAgentBuild,
    WorkstationInstallation,
    WorkstationInstallationEvent,
)
from app.db.models.user import User
from app.main import app


def _report(agent_version: str) -> dict:
    return {
        "collected_at": "2026-09-10T00:00:00Z",
        "system": {
            "cpu_percent": 10.0,
            "mem_percent": 20.0,
            "disk_usage": [{"path": "/", "used_percent": 30.0}],
        },
        "listening_ports": [],
        "services": [],
        "unauthorized_software": [],
        "backup": {
            "path": "/backup",
            "newest_file": "/backup/current.tar",
            "newest_mtime": "2026-09-10T00:00:00Z",
            "stale": False,
        },
        "collection_errors": [],
        "hostname": "synthetic-linux-online",
        "os": "linux",
        "agent_version": agent_version,
        "schema_version": 1,
    }


@pytest.mark.asyncio
async def test_synthetic_build_package_and_authenticated_report_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffix = uuid.uuid4().hex
    git_sha = suffix + "deadbeef"
    agent_version = f"v-e2e-{suffix[:8]}"
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    artifact_bytes = {
        "linux": b"synthetic-integrated-linux-agent\n",
        "windows": b"MZ-synthetic-integrated-windows-agent\n",
    }
    original_root = settings.NEXO_ARTIFACT_ROOT
    original_url = settings.NEXO_INGESTION_URL
    settings.NEXO_ARTIFACT_ROOT = artifact_root
    settings.NEXO_INGESTION_URL = (
        "https://forgehub.example.test/api/v1/agent-reports"
    )

    def bridge_handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Bridge-Token"] == settings.CHAT_BRIDGE_TOKEN
        if request.method == "GET" and request.url.path == "/v1/nexo/source":
            return httpx.Response(
                200,
                json={"git_sha": git_sha, "agent_version": agent_version},
            )
        os_kind = request.url.path.rsplit("/", 1)[-1]
        if (
            request.method == "POST"
            and request.url.path == f"/v1/nexo/build/{os_kind}"
            and os_kind in artifact_bytes
        ):
            filename = (
                "nexo-remote-agent.exe"
                if os_kind == "windows"
                else "nexo-remote-agent"
            )
            artifact_key = f"{git_sha}/{os_kind}/{filename}"
            artifact = artifact_root / artifact_key
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_bytes(artifact_bytes[os_kind])
            return httpx.Response(
                200,
                json={
                    "git_sha": git_sha,
                    "agent_version": agent_version,
                    "os_kind": os_kind,
                    "artifact_path": artifact_key,
                    "artifact_size": len(artifact_bytes[os_kind]),
                    "sha256": hashlib.sha256(artifact_bytes[os_kind]).hexdigest(),
                    "log_excerpt": f"built synthetic {os_kind}",
                },
            )
        return httpx.Response(404, json={"detail": "not found"})

    real_async_client = httpx.AsyncClient

    def bridge_client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(bridge_handler)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", bridge_client_factory)

    user_ids: list[uuid.UUID] = []
    workstation_ids: list[uuid.UUID] = []
    client_id: uuid.UUID | None = None
    try:
        async with AsyncSessionLocal() as db:
            admin = User(
                username=f"nexo-e2e-admin-{suffix}",
                hashed_password="synthetic-not-a-password-hash",
                is_admin=True,
            )
            customer = Client(name=f"Nexo integrated customer {suffix}")
            db.add_all([admin, customer])
            await db.flush()
            user_ids.append(admin.id)
            client_id = customer.id
            workstations = {}
            for os_kind in ("linux", "windows"):
                workstation = Workstation(
                    client_id=customer.id,
                    hostname=f"e2e-{os_kind}-{suffix[:8]}",
                    os_kind=os_kind,
                    device_token_hash=hash_device_token(
                        f"nxw_preexisting_{suffix}_{os_kind}"
                    ),
                    device_token_issued_at=datetime.now(timezone.utc),
                )
                db.add(workstation)
                await db.flush()
                workstation_ids.append(workstation.id)
                workstations[os_kind] = workstation
            await db.commit()
            headers = {
                "Authorization": f"Bearer {create_access_token(admin.username)}"
            }

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as api:
            built = await api.post("/api/v1/nexo-agent-builds", headers=headers)
            assert built.status_code == 202, built.text
            builds = {row["os_kind"]: row for row in built.json()}
            assert set(builds) == {"linux", "windows"}
            assert all(row["status"] == "ready" for row in builds.values())

            package_tokens = {}
            for os_kind in ("linux", "windows"):
                response = await api.post(
                    f"/api/v1/workstations/{workstations[os_kind].id}/installation-package",
                    params={"build_id": builds[os_kind]["id"]},
                    headers=headers,
                )
                assert response.status_code == 200, response.text
                with ZipFile(BytesIO(response.content)) as archive:
                    binary_name = (
                        "nexo-remote-agent.exe"
                        if os_kind == "windows"
                        else "nexo-remote-agent"
                    )
                    manifest = json.loads(archive.read("manifest.json"))
                    config = yaml.safe_load(archive.read("agent.yaml"))
                    assert archive.read(binary_name) == artifact_bytes[os_kind]
                    assert hashlib.sha256(archive.read(binary_name)).hexdigest() == (
                        manifest["binary_sha256"]
                    )
                    assert manifest["binary_sha256"] == builds[os_kind]["sha256"]
                    package_tokens[os_kind] = config["device_token"]

            reported = await api.post(
                "/api/v1/agent-reports",
                headers={"X-Device-Token": package_tokens["linux"]},
                json=_report(agent_version),
            )
            assert reported.status_code == 202, reported.text

        async with AsyncSessionLocal() as db:
            installations = list(
                (
                    await db.execute(
                        select(WorkstationInstallation).where(
                            WorkstationInstallation.workstation_id.in_(workstation_ids)
                        )
                    )
                ).scalars()
            )
            by_workstation = {row.workstation_id: row for row in installations}
            assert by_workstation[workstations["linux"].id].status == "online"
            assert by_workstation[workstations["linux"].id].online_at is not None
            assert by_workstation[workstations["windows"].id].status == "downloaded"
            linux_events = list(
                (
                    await db.execute(
                        select(WorkstationInstallationEvent.event_type)
                        .where(
                            WorkstationInstallationEvent.installation_id
                            == by_workstation[workstations["linux"].id].id
                        )
                        .order_by(WorkstationInstallationEvent.created_at)
                    )
                ).scalars()
            )
            assert linux_events == ["package_generated", "downloaded", "first_report"]
    finally:
        settings.NEXO_ARTIFACT_ROOT = original_root
        settings.NEXO_INGESTION_URL = original_url
        async with AsyncSessionLocal() as db:
            if workstation_ids:
                installation_ids = select(WorkstationInstallation.id).where(
                    WorkstationInstallation.workstation_id.in_(workstation_ids)
                )
                await db.execute(
                    delete(WorkstationInstallationEvent).where(
                        WorkstationInstallationEvent.installation_id.in_(installation_ids)
                    )
                )
                await db.execute(
                    delete(WorkstationInstallation).where(
                        WorkstationInstallation.workstation_id.in_(workstation_ids)
                    )
                )
                await db.execute(
                    delete(Workstation).where(Workstation.id.in_(workstation_ids))
                )
            if client_id is not None:
                await db.execute(delete(Client).where(Client.id == client_id))
            await db.execute(
                delete(NexoAgentBuild).where(NexoAgentBuild.git_sha == git_sha)
            )
            if user_ids:
                await db.execute(delete(User).where(User.id.in_(user_ids)))
            await db.commit()

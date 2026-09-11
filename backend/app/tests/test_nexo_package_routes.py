"""Secure, one-time Nexo workstation package delivery contracts."""

from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
import pytest_asyncio
import yaml
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from starlette.requests import ClientDisconnect

from app.api.routes import nexo_installation
from app.api.routes.workstation import hash_device_token
from app.core import nexo_packages
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


@pytest_asyncio.fixture
async def package_context(tmp_path: Path):
    suffix = uuid.uuid4().hex
    root = tmp_path / "artifacts"
    root.mkdir()
    original_root = settings.NEXO_ARTIFACT_ROOT
    original_url = settings.NEXO_INGESTION_URL
    settings.NEXO_ARTIFACT_ROOT = root
    settings.NEXO_INGESTION_URL = "https://forgehub.example.test/api/v1/agent-reports"

    async with AsyncSessionLocal() as db:
        admin = User(
            username=f"nexo-package-admin-{suffix}",
            hashed_password="synthetic-not-a-password-hash",
            is_admin=True,
        )
        limited = User(
            username=f"nexo-package-user-{suffix}",
            hashed_password="synthetic-not-a-password-hash",
            is_admin=False,
        )
        customer = Client(name=f"Nexo package customer {suffix}")
        db.add_all([admin, limited, customer])
        await db.flush()

        workstations: dict[str, Workstation] = {}
        builds: dict[str, NexoAgentBuild] = {}
        for os_kind, artifact_name, content in (
            ("linux", "nexo-remote-agent", b"synthetic-linux-agent\n"),
            ("windows", "nexo-remote-agent.exe", b"MZ-synthetic-windows-agent\n"),
        ):
            relative = f"{suffix}/{os_kind}/{artifact_name}"
            artifact = root / relative
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_bytes(content)
            workstation = Workstation(
                client_id=customer.id,
                hostname=f"test-{os_kind}",
                os_kind=os_kind,
                device_token_hash=hash_device_token(f"old-{suffix}-{os_kind}"),
                device_token_issued_at=datetime.now(timezone.utc),
            )
            build = NexoAgentBuild(
                git_sha=("a" if os_kind == "linux" else "b") * 8 + suffix,
                agent_version="v9.8.7-test",
                os_kind=os_kind,
                status="ready",
                artifact_path=relative,
                artifact_size=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
            )
            db.add_all([workstation, build])
            workstations[os_kind] = workstation
            builds[os_kind] = build
        await db.commit()

        context = {
            "admin_headers": {
                "Authorization": f"Bearer {create_access_token(admin.username)}"
            },
            "limited_headers": {
                "Authorization": f"Bearer {create_access_token(limited.username)}"
            },
            "admin_id": admin.id,
            "customer_id": customer.id,
            "user_ids": (admin.id, limited.id),
            "workstations": workstations,
            "builds": builds,
            "artifact_root": root,
        }

    try:
        yield context
    finally:
        settings.NEXO_ARTIFACT_ROOT = original_root
        settings.NEXO_INGESTION_URL = original_url
        async with AsyncSessionLocal() as db:
            await db.execute(
                delete(WorkstationInstallationEvent).where(
                    WorkstationInstallationEvent.installation_id.in_(
                        select(WorkstationInstallation.id).where(
                            WorkstationInstallation.workstation_id.in_(
                                [row.id for row in workstations.values()]
                            )
                        )
                    )
                )
            )
            await db.execute(
                delete(WorkstationInstallation).where(
                    WorkstationInstallation.workstation_id.in_(
                        [row.id for row in workstations.values()]
                    )
                )
            )
            await db.execute(
                delete(Workstation).where(Workstation.client_id == context["customer_id"])
            )
            await db.execute(delete(Client).where(Client.id == context["customer_id"]))
            await db.execute(
                delete(NexoAgentBuild).where(
                    NexoAgentBuild.id.in_([row.id for row in builds.values()])
                )
            )
            await db.execute(delete(User).where(User.id.in_(context["user_ids"])))
            await db.commit()


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http:
        yield http


def package_path(context: dict, os_kind: str) -> str:
    workstation = context["workstations"][os_kind]
    build = context["builds"][os_kind]
    return (
        f"/api/v1/workstations/{workstation.id}/installation-package"
        f"?build_id={build.id}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("os_kind", "expected_entries", "binary_name", "script_name"),
    [
        (
            "linux",
            {
                "nexo-remote-agent",
                "agent.yaml",
                "install.sh",
                "manifest.json",
                "README.txt",
            },
            "nexo-remote-agent",
            "install.sh",
        ),
        (
            "windows",
            {
                "nexo-remote-agent.exe",
                "agent.yaml",
                "install.ps1",
                "manifest.json",
                "README.txt",
            },
            "nexo-remote-agent.exe",
            "install.ps1",
        ),
    ],
)
async def test_package_contains_only_fixed_platform_entries_and_safe_modes(
    client: AsyncClient,
    package_context: dict,
    os_kind: str,
    expected_entries: set[str],
    binary_name: str,
    script_name: str,
) -> None:
    response = await client.post(
        package_path(package_context, os_kind),
        headers=package_context["admin_headers"],
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-disposition"].startswith("attachment; filename=")
    with ZipFile(BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == expected_entries
        config = yaml.safe_load(archive.read("agent.yaml"))
        assert config == {
            "endpoint_url": "https://forgehub.example.test/api/v1/agent-reports",
            "device_token": config["device_token"],
            "report_interval": "5m",
            "critical_services": ["sshd", "nginx"]
            if os_kind == "linux"
            else [],
            "unauthorized_software": ["AnyDesk", "HopToDesk", "TeamViewer"],
            "backup_paths": ["/backup"] if os_kind == "linux" else ["C:\\Backup"],
            "backup_max_age": "24h",
            "disk_paths": ["/", "/backup"]
            if os_kind == "linux"
            else ["C:\\"],
        }
        assert config["device_token"].startswith("nxw_")

        manifest = json.loads(archive.read("manifest.json"))
        assert "device_token" not in manifest
        assert manifest["workstation_id"] == str(
            package_context["workstations"][os_kind].id
        )
        assert manifest["binary_sha256"] == package_context["builds"][os_kind].sha256
        assert hashlib.sha256(archive.read(binary_name)).hexdigest() == manifest[
            "binary_sha256"
        ]

        modes = {
            name: (archive.getinfo(name).external_attr >> 16) & 0o777
            for name in archive.namelist()
        }
        assert modes[binary_name] == 0o755
        assert modes[script_name] == 0o755
        assert modes["agent.yaml"] == 0o600
        assert modes["manifest.json"] == modes["README.txt"] == 0o644


@pytest.mark.asyncio
async def test_package_requires_an_administrator(
    client: AsyncClient, package_context: dict
) -> None:
    response = await client.post(
        package_path(package_context, "linux"),
        headers=package_context["limited_headers"],
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_package_rejects_os_mismatch(
    client: AsyncClient, package_context: dict
) -> None:
    workstation = package_context["workstations"]["linux"]
    build = package_context["builds"]["windows"]

    response = await client.post(
        f"/api/v1/workstations/{workstation.id}/installation-package?build_id={build.id}",
        headers=package_context["admin_headers"],
    )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_package_rejects_non_ready_build(
    client: AsyncClient, package_context: dict
) -> None:
    build_id = package_context["builds"]["linux"].id
    async with AsyncSessionLocal() as db:
        build = await db.get(NexoAgentBuild, build_id)
        build.status = "failed"
        await db.commit()

    response = await client.post(
        package_path(package_context, "linux"),
        headers=package_context["admin_headers"],
    )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_materialization_failure_without_usable_generation_records_error(
    client: AsyncClient, package_context: dict
) -> None:
    workstation_id = package_context["workstations"]["linux"].id
    old_hash = package_context["workstations"]["linux"].device_token_hash
    artifact = (
        package_context["artifact_root"]
        / package_context["builds"]["linux"].artifact_path
    )
    artifact.write_bytes(b"corrupted-after-build")

    response = await client.post(
        package_path(package_context, "linux"),
        headers=package_context["admin_headers"],
    )

    assert response.status_code == 409
    async with AsyncSessionLocal() as db:
        workstation = await db.get(Workstation, workstation_id)
        installation = (
            await db.execute(
                select(WorkstationInstallation).where(
                    WorkstationInstallation.workstation_id == workstation_id
                )
            )
        ).scalar_one_or_none()
        assert workstation.device_token_hash == old_hash
        assert installation is not None
        assert installation.build_id == package_context["builds"]["linux"].id
        assert installation.status == "error"
        assert installation.downloaded_at is None
        assert installation.online_at is None
        assert installation.last_error == "Nexo package could not be generated"
        events = list(
            (
                await db.execute(
                    select(WorkstationInstallationEvent).where(
                        WorkstationInstallationEvent.installation_id
                        == installation.id
                    )
                )
            ).scalars()
        )
        assert len(events) == 1
        assert events[0].event_type == "error"
        assert events[0].from_status is None
        assert events[0].to_status == "error"
        assert events[0].detail == "Nexo package could not be generated"
        assert events[0].actor_user_id == package_context["admin_id"]


@pytest.mark.asyncio
async def test_materialization_failure_preserves_existing_usable_generation(
    client: AsyncClient,
    package_context: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = package_path(package_context, "linux")
    delivered = await client.post(path, headers=package_context["admin_headers"])
    assert delivered.status_code == 200

    workstation_id = package_context["workstations"]["linux"].id
    async with AsyncSessionLocal() as db:
        workstation = await db.get(Workstation, workstation_id)
        installation = (
            await db.execute(
                select(WorkstationInstallation).where(
                    WorkstationInstallation.workstation_id == workstation_id
                )
            )
        ).scalar_one()
        original_token_hash = workstation.device_token_hash
        original_build_id = installation.build_id
        original_generated_at = installation.package_generated_at
        original_downloaded_at = installation.downloaded_at

    leaked_token = "nxw_must-not-be-persisted-or-returned"
    leaked_path = "/srv/private/nexo/packages/workstation.zip"

    def fail_materialization(*args, **kwargs):
        raise nexo_packages.NexoPackageError(
            f"failed for {leaked_token} at {leaked_path}"
        )

    monkeypatch.setattr(nexo_packages, "materialize_package", fail_materialization)
    failed = await client.post(path, headers=package_context["admin_headers"])

    assert failed.status_code == 409
    assert failed.json() == {"detail": "Nexo package could not be generated"}
    async with AsyncSessionLocal() as db:
        workstation = await db.get(Workstation, workstation_id)
        installation = (
            await db.execute(
                select(WorkstationInstallation).where(
                    WorkstationInstallation.workstation_id == workstation_id
                )
            )
        ).scalar_one()
        events = list(
            (
                await db.execute(
                    select(WorkstationInstallationEvent)
                    .where(
                        WorkstationInstallationEvent.installation_id
                        == installation.id
                    )
                    .order_by(WorkstationInstallationEvent.created_at)
                )
            ).scalars()
        )
        assert workstation.device_token_hash == original_token_hash
        assert installation.build_id == original_build_id
        assert installation.status == "downloaded"
        assert installation.package_generated_at == original_generated_at
        assert installation.downloaded_at == original_downloaded_at
        assert installation.last_error == "Nexo package could not be generated"
        assert [event.event_type for event in events] == [
            "package_generated",
            "downloaded",
            "error",
        ]
        error_event = events[-1]
        assert error_event.from_status == error_event.to_status == "downloaded"
        assert error_event.detail == "Nexo package could not be generated"
        assert error_event.actor_user_id == package_context["admin_id"]
        persisted = " ".join(
            filter(None, [installation.last_error, error_event.detail])
        )
        assert leaked_token not in persisted
        assert leaked_path not in persisted


@pytest.mark.asyncio
async def test_second_package_invalidates_first_token_and_records_each_delivery(
    client: AsyncClient, package_context: dict
) -> None:
    path = package_path(package_context, "linux")
    first = await client.post(path, headers=package_context["admin_headers"])
    second = await client.post(path, headers=package_context["admin_headers"])

    with ZipFile(BytesIO(first.content)) as archive:
        first_token = yaml.safe_load(archive.read("agent.yaml"))["device_token"]
    with ZipFile(BytesIO(second.content)) as archive:
        second_token = yaml.safe_load(archive.read("agent.yaml"))["device_token"]
    assert first_token != second_token

    workstation_id = package_context["workstations"]["linux"].id
    async with AsyncSessionLocal() as db:
        workstation = await db.get(Workstation, workstation_id)
        installation = (
            await db.execute(
                select(WorkstationInstallation).where(
                    WorkstationInstallation.workstation_id == workstation_id
                )
            )
        ).scalar_one()
        events = list(
            (
                await db.execute(
                    select(WorkstationInstallationEvent)
                    .where(
                        WorkstationInstallationEvent.installation_id
                        == installation.id
                    )
                    .order_by(WorkstationInstallationEvent.created_at)
                )
            ).scalars()
        )
        assert workstation.device_token_hash == hash_device_token(second_token)
        assert workstation.device_token_hash != hash_device_token(first_token)
        assert workstation.device_token_revoked_at is None
        assert installation.status == "downloaded"
        assert installation.downloaded_at is not None
        assert [event.event_type for event in events] == [
            "package_generated",
            "downloaded",
            "package_generated",
            "downloaded",
        ]
        assert all(event.actor_user_id == package_context["admin_id"] for event in events)


@pytest.mark.asyncio
async def test_concurrent_package_requests_serialize_token_rotations(
    client: AsyncClient, package_context: dict
) -> None:
    path = package_path(package_context, "linux")

    responses = await asyncio.gather(
        client.post(path, headers=package_context["admin_headers"]),
        client.post(path, headers=package_context["admin_headers"]),
    )

    assert [response.status_code for response in responses] == [200, 200]
    tokens = []
    for response in responses:
        with ZipFile(BytesIO(response.content)) as archive:
            tokens.append(yaml.safe_load(archive.read("agent.yaml"))["device_token"])
    assert tokens[0] != tokens[1]

    workstation_id = package_context["workstations"]["linux"].id
    async with AsyncSessionLocal() as db:
        workstation = await db.get(Workstation, workstation_id)
        installations = list(
            (
                await db.execute(
                    select(WorkstationInstallation).where(
                        WorkstationInstallation.workstation_id == workstation_id
                    )
                )
            ).scalars()
        )
        events = list(
            (
                await db.execute(
                    select(WorkstationInstallationEvent).where(
                        WorkstationInstallationEvent.installation_id
                        == installations[0].id
                    )
                )
            ).scalars()
        )
        assert len(installations) == 1
        assert workstation.device_token_hash in {
            hash_device_token(token) for token in tokens
        }
        assert [event.event_type for event in events].count("package_generated") == 2
        assert [event.event_type for event in events].count("downloaded") >= 1


@pytest.mark.asyncio
async def test_package_requires_a_valid_https_ingestion_url(
    client: AsyncClient, package_context: dict
) -> None:
    workstation_id = package_context["workstations"]["linux"].id
    old_hash = package_context["workstations"]["linux"].device_token_hash
    settings.NEXO_INGESTION_URL = "http://forgehub.example.test/api/v1/agent-reports"

    response = await client.post(
        package_path(package_context, "linux"),
        headers=package_context["admin_headers"],
    )

    assert response.status_code == 409
    async with AsyncSessionLocal() as db:
        workstation = await db.get(Workstation, workstation_id)
        assert workstation.device_token_hash == old_hash


@pytest.mark.asyncio
async def test_asgi_response_start_failure_removes_temporary_content(
    package_context: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workstation = package_context["workstations"]["linux"]
    build = package_context["builds"]["linux"]
    created_directories: list[tempfile.TemporaryDirectory[str]] = []
    real_temporary_directory = tempfile.TemporaryDirectory

    def tracked_temporary_directory(*args, **kwargs):
        directory = real_temporary_directory(*args, **kwargs)
        created_directories.append(directory)
        return directory

    monkeypatch.setattr(
        nexo_installation.tempfile,
        "TemporaryDirectory",
        tracked_temporary_directory,
    )
    async with AsyncSessionLocal() as db:
        admin = await db.get(User, package_context["admin_id"])
        response = await nexo_installation.generate_workstation_installation_package(
            workstation.id,
            build.id,
            db,
            admin,
        )
    assert len(created_directories) == 1
    temporary_path = Path(created_directories[0].name)
    assert temporary_path.exists()

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def failing_send(message):
        assert message["type"] == "http.response.start"
        raise OSError("synthetic response-start failure")

    with pytest.raises(ClientDisconnect):
        await response(
            {"type": "http", "asgi": {"spec_version": "2.4"}},
            receive,
            failing_send,
        )

    assert not temporary_path.exists()
    async with AsyncSessionLocal() as db:
        installation = (
            await db.execute(
                select(WorkstationInstallation).where(
                    WorkstationInstallation.workstation_id == workstation.id
                )
            )
        ).scalar_one()
        event_types = list(
            (
                await db.execute(
                    select(WorkstationInstallationEvent.event_type).where(
                        WorkstationInstallationEvent.installation_id
                        == installation.id
                    )
                )
            ).scalars()
        )
        assert installation.status == "package_ready"
        assert installation.downloaded_at is None
        assert event_types == ["package_generated"]


@pytest.mark.asyncio
async def test_asgi_send_failure_keeps_package_ready_and_removes_temporary_content(
    package_context: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workstation = package_context["workstations"]["linux"]
    build = package_context["builds"]["linux"]
    created_paths: list[Path] = []
    real_temporary_directory = tempfile.TemporaryDirectory

    def tracked_temporary_directory(*args, **kwargs):
        directory = real_temporary_directory(*args, **kwargs)
        created_paths.append(Path(directory.name))
        return directory

    monkeypatch.setattr(
        nexo_installation.tempfile,
        "TemporaryDirectory",
        tracked_temporary_directory,
    )
    async with AsyncSessionLocal() as db:
        admin = await db.get(User, package_context["admin_id"])
        response = await nexo_installation.generate_workstation_installation_package(
            workstation.id,
            build.id,
            db,
            admin,
        )
    assert len(created_paths) == 1
    assert created_paths[0].exists()

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def failing_send(message):
        if message["type"] == "http.response.body":
            raise OSError("synthetic disconnected client")

    with pytest.raises(ClientDisconnect):
        await response(
            {"type": "http", "asgi": {"spec_version": "2.4"}},
            receive,
            failing_send,
        )

    assert not created_paths[0].exists()
    async with AsyncSessionLocal() as db:
        installation = (
            await db.execute(
                select(WorkstationInstallation).where(
                    WorkstationInstallation.workstation_id == workstation.id
                )
            )
        ).scalar_one()
        event_types = list(
            (
                await db.execute(
                    select(WorkstationInstallationEvent.event_type).where(
                        WorkstationInstallationEvent.installation_id
                        == installation.id
                    )
                )
            ).scalars()
        )
        assert installation.status == "package_ready"
        assert installation.downloaded_at is None
        assert event_types == ["package_generated"]


@pytest.mark.asyncio
async def test_locked_revalidation_refreshes_stale_identity_map_state(
    package_context: dict,
) -> None:
    workstation_id = package_context["workstations"]["linux"].id
    build_id = package_context["builds"]["linux"].id
    revoked_at = datetime.now(timezone.utc)
    response = None
    async with AsyncSessionLocal() as request_db:
        stale_workstation = await request_db.get(Workstation, workstation_id)
        stale_build = await request_db.get(NexoAgentBuild, build_id)
        assert stale_workstation.device_token_revoked_at is None
        assert stale_build.status == "ready"

        async with AsyncSessionLocal() as concurrent_db:
            current_workstation = await concurrent_db.get(Workstation, workstation_id)
            current_build = await concurrent_db.get(NexoAgentBuild, build_id)
            current_workstation.device_token_revoked_at = revoked_at
            current_build.status = "failed"
            await concurrent_db.commit()

        admin = await request_db.get(User, package_context["admin_id"])
        try:
            with pytest.raises(HTTPException) as exc_info:
                response = await nexo_installation.generate_workstation_installation_package(
                    workstation_id,
                    build_id,
                    request_db,
                    admin,
                )
            assert exc_info.value.status_code == 409
        finally:
            if response is not None:
                await response.body_iterator.aclose()

    async with AsyncSessionLocal() as db:
        workstation = await db.get(Workstation, workstation_id)
        build = await db.get(NexoAgentBuild, build_id)
        installation = (
            await db.execute(
                select(WorkstationInstallation).where(
                    WorkstationInstallation.workstation_id == workstation_id
                )
            )
        ).scalar_one_or_none()
        assert workstation.device_token_revoked_at == revoked_at
        assert build.status == "failed"
        assert installation is None


def test_materialization_uses_the_exact_bytes_that_passed_integrity_check(
    package_context: dict,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workstation = package_context["workstations"]["linux"]
    build = package_context["builds"]["linux"]
    artifact = package_context["artifact_root"] / build.artifact_path
    expected_binary = artifact.read_bytes()
    replacement = b"different-bytes-after-validated-read"
    real_read = nexo_packages._read_artifact_bytes

    def read_then_replace(path: Path) -> bytes:
        content = real_read(path)
        path.write_bytes(replacement)
        return content

    monkeypatch.setattr(nexo_packages, "_read_artifact_bytes", read_then_replace)
    metadata = nexo_packages.materialize_package(
        workstation,
        build,
        "nxw_synthetic-token-long-enough-for-test",
        tmp_path / "package-output",
    )

    with ZipFile(metadata.path) as archive:
        packaged_binary = archive.read("nexo-remote-agent")
        manifest = json.loads(archive.read("manifest.json"))
    assert packaged_binary == expected_binary
    assert packaged_binary != replacement
    assert hashlib.sha256(packaged_binary).hexdigest() == manifest["binary_sha256"]


@pytest.mark.asyncio
async def test_windows_installer_stops_before_copy_and_checks_native_failures(
    client: AsyncClient,
    package_context: dict,
) -> None:
    response = await client.post(
        package_path(package_context, "windows"),
        headers=package_context["admin_headers"],
    )
    assert response.status_code == 200
    with ZipFile(BytesIO(response.content)) as archive:
        script = archive.read("install.ps1").decode()

    assert script.index("& $Nssm stop $ServiceName") < script.index("Copy-Item")
    assert "WaitForStatus('Stopped'" in script
    assert '"*S-1-5-18:F"' in script
    assert '"*S-1-5-32-544:F"' in script
    assert "SYSTEM:F" not in script
    assert "Administrators:F" not in script
    native_commands = [
        line.strip()
        for line in script.splitlines()
        if line.strip().startswith("& ")
    ]
    assert len(native_commands) == 7
    assert script.count("Assert-NativeSuccess") == len(native_commands) + 1

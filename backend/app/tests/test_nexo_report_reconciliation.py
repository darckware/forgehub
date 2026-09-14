"""Agent-report reconciliation for the current Nexo installation generation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.api.routes.workstation import hash_device_token
from app.db.base import AsyncSessionLocal
from app.db.models.client import Client, Workstation
from app.db.models.nexo_installation import (
    NexoAgentBuild,
    WorkstationInstallation,
    WorkstationInstallationEvent,
)
from app.main import app


EXPECTED_VERSION = "v9.8.7-test"


@dataclass(frozen=True)
class CurrentPackage:
    client_id: uuid.UUID
    workstation_id: uuid.UUID
    build_id: uuid.UUID
    installation_id: uuid.UUID
    token: str
    old_token: str
    version: str


def report(*, agent_version: str) -> dict:
    return {
        "collected_at": "2026-09-08T00:00:00Z",
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
            "newest_mtime": "2026-09-08T00:00:00Z",
            "stale": False,
        },
        "collection_errors": [],
        "hostname": "nexo-report-reconciliation",
        "os": "linux",
        "agent_version": agent_version,
        "schema_version": 1,
    }


async def _delete_package_rows(package: CurrentPackage) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(WorkstationInstallationEvent).where(
                WorkstationInstallationEvent.installation_id
                == package.installation_id
            )
        )
        await db.execute(
            delete(WorkstationInstallation).where(
                WorkstationInstallation.id == package.installation_id
            )
        )
        await db.execute(
            delete(Workstation).where(
                Workstation.id == package.workstation_id
            )
        )
        await db.execute(delete(Client).where(Client.id == package.client_id))
        await db.execute(
            delete(NexoAgentBuild).where(NexoAgentBuild.id == package.build_id)
        )
        await db.commit()


@pytest_asyncio.fixture
async def current_package():
    token = f"nxw_current_{uuid.uuid4().hex}"
    old_token = f"nxw_previous_{uuid.uuid4().hex}"
    package_generated_at = datetime.now(timezone.utc) - timedelta(minutes=2)
    downloaded_at = package_generated_at + timedelta(seconds=30)

    async with AsyncSessionLocal() as db:
        customer = Client(name=f"Nexo report reconciliation {uuid.uuid4()}")
        db.add(customer)
        await db.flush()
        workstation = Workstation(
            client_id=customer.id,
            hostname="before-report",
            os_kind="linux",
            device_token_hash=hash_device_token(token),
            device_token_issued_at=package_generated_at,
        )
        build = NexoAgentBuild(
            git_sha=f"{uuid.uuid4().hex}deadbeef",
            agent_version=EXPECTED_VERSION,
            os_kind="linux",
            status="ready",
        )
        db.add_all([workstation, build])
        await db.flush()
        installation = WorkstationInstallation(
            workstation_id=workstation.id,
            build_id=build.id,
            status="downloaded",
            package_generated_at=package_generated_at,
            downloaded_at=downloaded_at,
        )
        db.add(installation)
        await db.flush()
        db.add_all(
            [
                WorkstationInstallationEvent(
                    installation_id=installation.id,
                    event_type="package_generated",
                    from_status=None,
                    to_status="package_ready",
                    created_at=package_generated_at,
                ),
                WorkstationInstallationEvent(
                    installation_id=installation.id,
                    event_type="downloaded",
                    from_status="package_ready",
                    to_status="downloaded",
                    created_at=downloaded_at,
                ),
            ]
        )
        await db.commit()
        package = CurrentPackage(
            client_id=customer.id,
            workstation_id=workstation.id,
            build_id=build.id,
            installation_id=installation.id,
            token=token,
            old_token=old_token,
            version=build.agent_version,
        )

    try:
        yield package
    finally:
        await _delete_package_rows(package)


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http:
        yield http


async def load_installation(workstation_id: uuid.UUID) -> WorkstationInstallation:
    async with AsyncSessionLocal() as db:
        return (
            await db.execute(
                select(WorkstationInstallation).where(
                    WorkstationInstallation.workstation_id == workstation_id
                )
            )
        ).scalar_one()


async def event_rows(
    installation_id: uuid.UUID,
) -> list[WorkstationInstallationEvent]:
    async with AsyncSessionLocal() as db:
        return list(
            (
                await db.execute(
                    select(WorkstationInstallationEvent)
                    .where(
                        WorkstationInstallationEvent.installation_id
                        == installation_id
                    )
                    .order_by(WorkstationInstallationEvent.created_at)
                )
            ).scalars()
        )


@pytest.mark.asyncio
async def test_first_matching_report_marks_installation_online(
    client: AsyncClient, current_package: CurrentPackage
):
    response = await client.post(
        "/api/v1/agent-reports",
        headers={"X-Device-Token": current_package.token},
        json=report(agent_version=current_package.version),
    )

    assert response.status_code == 202, response.text
    installation = await load_installation(current_package.workstation_id)
    assert installation.status == "online"
    assert installation.online_at is not None
    assert [event.event_type for event in await event_rows(installation.id)] == [
        "package_generated",
        "downloaded",
        "first_report",
    ]


@pytest.mark.asyncio
async def test_repeated_matching_report_preserves_first_online_time_and_event(
    client: AsyncClient, current_package: CurrentPackage
):
    first = await client.post(
        "/api/v1/agent-reports",
        headers={"X-Device-Token": current_package.token},
        json=report(agent_version=current_package.version),
    )
    assert first.status_code == 202, first.text
    first_online_at = (
        await load_installation(current_package.workstation_id)
    ).online_at

    second = await client.post(
        "/api/v1/agent-reports",
        headers={"X-Device-Token": current_package.token},
        json=report(agent_version=current_package.version),
    )

    assert second.status_code == 202, second.text
    installation = await load_installation(current_package.workstation_id)
    assert installation.online_at == first_online_at
    events = await event_rows(installation.id)
    assert [event.event_type for event in events].count("first_report") == 1


@pytest.mark.asyncio
async def test_first_mismatching_report_marks_installation_outdated(
    client: AsyncClient, current_package: CurrentPackage
):
    response = await client.post(
        "/api/v1/agent-reports",
        headers={"X-Device-Token": current_package.token},
        json=report(agent_version="v1.0.0"),
    )

    assert response.status_code == 202, response.text
    installation = await load_installation(current_package.workstation_id)
    assert installation.status == "outdated"
    assert installation.online_at is not None
    events = await event_rows(installation.id)
    assert [event.event_type for event in events] == [
        "package_generated",
        "downloaded",
        "first_report",
        "version_mismatch",
    ]
    assert events[-1].detail == (
        f"expected agent version {current_package.version}, reported v1.0.0"
    )


@pytest.mark.asyncio
async def test_same_mismatch_is_not_duplicated_but_changed_detail_is_recorded(
    client: AsyncClient, current_package: CurrentPackage
):
    for agent_version in ("v1.0.0", "v1.0.0", "v2.0.0"):
        response = await client.post(
            "/api/v1/agent-reports",
            headers={"X-Device-Token": current_package.token},
            json=report(agent_version=agent_version),
        )
        assert response.status_code == 202, response.text

    mismatch_events = [
        event
        for event in await event_rows(current_package.installation_id)
        if event.event_type == "version_mismatch"
    ]
    assert [event.detail for event in mismatch_events] == [
        f"expected agent version {current_package.version}, reported v1.0.0",
        f"expected agent version {current_package.version}, reported v2.0.0",
    ]


@pytest.mark.asyncio
async def test_report_older_than_current_package_does_not_reconcile(
    client: AsyncClient, current_package: CurrentPackage
):
    future_generation = datetime.now(timezone.utc) + timedelta(minutes=5)
    async with AsyncSessionLocal() as db:
        installation = await db.get(
            WorkstationInstallation, current_package.installation_id
        )
        installation.package_generated_at = future_generation
        await db.commit()

    response = await client.post(
        "/api/v1/agent-reports",
        headers={"X-Device-Token": current_package.token},
        json=report(agent_version=current_package.version),
    )

    assert response.status_code == 202, response.text
    installation = await load_installation(current_package.workstation_id)
    assert installation.status == "downloaded"
    assert installation.online_at is None
    assert [event.event_type for event in await event_rows(installation.id)] == [
        "package_generated",
        "downloaded",
    ]


@pytest.mark.asyncio
async def test_report_without_installation_remains_compatible(
    client: AsyncClient, current_package: CurrentPackage
):
    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(WorkstationInstallationEvent).where(
                WorkstationInstallationEvent.installation_id
                == current_package.installation_id
            )
        )
        await db.execute(
            delete(WorkstationInstallation).where(
                WorkstationInstallation.id == current_package.installation_id
            )
        )
        await db.commit()

    response = await client.post(
        "/api/v1/agent-reports",
        headers={"X-Device-Token": current_package.token},
        json=report(agent_version=current_package.version),
    )

    assert response.status_code == 202, response.text
    async with AsyncSessionLocal() as db:
        workstation = await db.get(Workstation, current_package.workstation_id)
        assert workstation.last_report_at is not None
        assert workstation.last_seen_agent_version == current_package.version


@pytest.mark.asyncio
async def test_previous_rotated_token_is_rejected_before_reconciliation(
    client: AsyncClient, current_package: CurrentPackage
):
    response = await client.post(
        "/api/v1/agent-reports",
        headers={"X-Device-Token": current_package.old_token},
        json=report(agent_version=current_package.version),
    )

    assert response.status_code == 401
    installation = await load_installation(current_package.workstation_id)
    assert installation.status == "downloaded"
    assert installation.online_at is None
    async with AsyncSessionLocal() as db:
        workstation = await db.get(Workstation, current_package.workstation_id)
        assert workstation.last_report_at is None
        assert workstation.last_seen_agent_version is None

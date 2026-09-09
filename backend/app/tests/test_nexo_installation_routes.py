"""Administrator installation status projections and event history."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.api.routes.workstation import hash_device_token
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
async def installation_context():
    suffix = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        admin = User(
            username=f"nexo-installation-admin-{suffix}",
            hashed_password="synthetic-not-a-password-hash",
            is_admin=True,
        )
        limited = User(
            username=f"nexo-installation-user-{suffix}",
            hashed_password="synthetic-not-a-password-hash",
            is_admin=False,
        )
        first_client = Client(name=f"A Nexo installation customer {suffix}")
        second_client = Client(name=f"Z Nexo installation customer {suffix}")
        db.add_all([admin, limited, first_client, second_client])
        await db.flush()

        first_workstation = Workstation(
            client_id=first_client.id,
            hostname="alpha-host",
            os_kind="linux",
            device_token_hash=hash_device_token(f"linux-{suffix}"),
            device_token_issued_at=now - timedelta(hours=2),
            last_report_at=now,
            last_seen_agent_version="v2.0.0",
        )
        second_workstation = Workstation(
            client_id=second_client.id,
            hostname="zulu-host",
            os_kind="windows",
            device_token_hash=hash_device_token(f"windows-{suffix}"),
            device_token_issued_at=now - timedelta(hours=3),
            last_report_at=None,
            last_seen_agent_version=None,
        )
        first_build = NexoAgentBuild(
            git_sha="a" * 8 + suffix,
            agent_version="v2.0.0",
            os_kind="linux",
            status="ready",
            artifact_path=f"{suffix}/linux/nexo-remote-agent",
            artifact_size=321,
            sha256="a" * 64,
        )
        second_build = NexoAgentBuild(
            git_sha="b" * 8 + suffix,
            agent_version="v3.0.0",
            os_kind="windows",
            status="ready",
            artifact_path=f"{suffix}/windows/nexo-remote-agent.exe",
            artifact_size=654,
            sha256="b" * 64,
        )
        db.add_all(
            [first_workstation, second_workstation, first_build, second_build]
        )
        await db.flush()

        first_installation = WorkstationInstallation(
            workstation_id=first_workstation.id,
            build_id=first_build.id,
            status="online",
            package_generated_at=now - timedelta(hours=1),
            downloaded_at=now - timedelta(minutes=55),
            online_at=now - timedelta(minutes=50),
        )
        second_installation = WorkstationInstallation(
            workstation_id=second_workstation.id,
            build_id=second_build.id,
            status="package_ready",
            package_generated_at=now - timedelta(minutes=30),
        )
        # Add in reverse display order so the endpoint must apply its ordering.
        db.add_all([second_installation, first_installation])
        await db.flush()

        event_time = now - timedelta(minutes=56)
        event_ids = sorted((uuid.uuid4(), uuid.uuid4()))
        db.add_all(
            [
                WorkstationInstallationEvent(
                    id=event_ids[1],
                    installation_id=first_installation.id,
                    event_type="downloaded",
                    from_status="package_ready",
                    to_status="downloaded",
                    actor_user_id=admin.id,
                    created_at=event_time,
                ),
                WorkstationInstallationEvent(
                    id=event_ids[0],
                    installation_id=first_installation.id,
                    event_type="package_generated",
                    from_status=None,
                    to_status="package_ready",
                    actor_user_id=admin.id,
                    created_at=event_time,
                ),
            ]
        )
        await db.commit()

    context = {
        "admin_headers": {
            "Authorization": f"Bearer {create_access_token(admin.username)}"
        },
        "limited_headers": {
            "Authorization": f"Bearer {create_access_token(limited.username)}"
        },
        "user_ids": [admin.id, limited.id],
        "client_ids": [first_client.id, second_client.id],
        "workstation_ids": [first_workstation.id, second_workstation.id],
        "build_ids": [first_build.id, second_build.id],
        "installation_ids": [first_installation.id, second_installation.id],
        "event_ids": event_ids,
        "first": {
            "installation_id": first_installation.id,
            "client_id": first_client.id,
            "client_name": first_client.name,
            "workstation_id": first_workstation.id,
            "build_id": first_build.id,
            "hostname": first_workstation.hostname,
            "package_generated_at": first_installation.package_generated_at,
            "downloaded_at": first_installation.downloaded_at,
            "online_at": first_installation.online_at,
            "last_report_at": first_workstation.last_report_at,
        },
        "second": {"installation_id": second_installation.id},
    }

    try:
        yield context
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(
                delete(WorkstationInstallationEvent).where(
                    WorkstationInstallationEvent.installation_id.in_(
                        context["installation_ids"]
                    )
                )
            )
            await db.execute(
                delete(WorkstationInstallation).where(
                    WorkstationInstallation.id.in_(context["installation_ids"])
                )
            )
            await db.execute(
                delete(Workstation).where(
                    Workstation.id.in_(context["workstation_ids"])
                )
            )
            await db.execute(delete(Client).where(Client.id.in_(context["client_ids"])))
            await db.execute(
                delete(NexoAgentBuild).where(
                    NexoAgentBuild.id.in_(context["build_ids"])
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


@pytest.mark.asyncio
async def test_list_installations_filters_and_projects_safe_status(
    client: AsyncClient, installation_context: dict
) -> None:
    context = installation_context
    response = await client.get(
        "/api/v1/nexo-installations",
        params={"status": "online", "client_id": str(context["first"]["client_id"])},
        headers=context["admin_headers"],
    )

    assert response.status_code == 200, response.text
    assert len(response.json()) == 1
    row = response.json()[0]
    assert set(row) == {
        "id",
        "workstation_id",
        "client_id",
        "build_id",
        "client_name",
        "workstation_hostname",
        "os_kind",
        "status",
        "expected_version",
        "detected_version",
        "package_generated_at",
        "downloaded_at",
        "online_at",
        "last_report_at",
        "last_error",
        "created_at",
        "updated_at",
    }
    assert row["id"] == str(context["first"]["installation_id"])
    assert row["workstation_id"] == str(context["first"]["workstation_id"])
    assert row["client_id"] == str(context["first"]["client_id"])
    assert row["build_id"] == str(context["first"]["build_id"])
    assert row["client_name"] == context["first"]["client_name"]
    assert row["workstation_hostname"] == context["first"]["hostname"]
    assert row["os_kind"] == "linux"
    assert row["status"] == "online"
    assert row["expected_version"] == "v2.0.0"
    assert row["detected_version"] == "v2.0.0"
    for field in (
        "package_generated_at",
        "downloaded_at",
        "online_at",
        "last_report_at",
    ):
        assert datetime.fromisoformat(row[field]) == context["first"][field]
    assert row["last_error"] is None
    assert {
        "artifact_path",
        "device_token_hash",
        "raw_token",
    }.isdisjoint(row)


@pytest.mark.asyncio
async def test_list_installations_filters_os_and_workstation_and_orders_names(
    client: AsyncClient, installation_context: dict
) -> None:
    context = installation_context
    unfiltered = await client.get(
        "/api/v1/nexo-installations", headers=context["admin_headers"]
    )
    windows = await client.get(
        "/api/v1/nexo-installations",
        params={
            "os_kind": "windows",
            "workstation_id": str(context["workstation_ids"][1]),
        },
        headers=context["admin_headers"],
    )

    assert unfiltered.status_code == windows.status_code == 200
    assert [row["id"] for row in unfiltered.json()] == [
        str(context["installation_ids"][0]),
        str(context["installation_ids"][1]),
    ]
    assert [row["id"] for row in windows.json()] == [
        str(context["installation_ids"][1])
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("parameter", "value"),
    [("os_kind", "macos"), ("status", "installed")],
)
async def test_list_installations_rejects_unsupported_filter_values(
    client: AsyncClient,
    installation_context: dict,
    parameter: str,
    value: str,
) -> None:
    response = await client.get(
        "/api/v1/nexo-installations",
        params={parameter: value},
        headers=installation_context["admin_headers"],
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_detail_returns_oldest_to_newest_events_with_stable_ties(
    client: AsyncClient, installation_context: dict
) -> None:
    response = await client.get(
        f"/api/v1/nexo-installations/{installation_context['first']['installation_id']}",
        headers=installation_context["admin_headers"],
    )

    assert response.status_code == 200, response.text
    assert [event["event_type"] for event in response.json()["events"]] == [
        "package_generated",
        "downloaded",
    ]
    assert [event["id"] for event in response.json()["events"]] == [
        str(installation_context["event_ids"][0]),
        str(installation_context["event_ids"][1]),
    ]


@pytest.mark.asyncio
async def test_installation_queries_require_an_administrator(
    client: AsyncClient, installation_context: dict
) -> None:
    list_response = await client.get(
        "/api/v1/nexo-installations",
        headers=installation_context["limited_headers"],
    )
    detail_response = await client.get(
        f"/api/v1/nexo-installations/{installation_context['first']['installation_id']}",
        headers=installation_context["limited_headers"],
    )

    assert list_response.status_code == detail_response.status_code == 403


@pytest.mark.asyncio
async def test_installation_detail_returns_404_for_unknown_id(
    client: AsyncClient, installation_context: dict
) -> None:
    response = await client.get(
        f"/api/v1/nexo-installations/{uuid.uuid4()}",
        headers=installation_context["admin_headers"],
    )

    assert response.status_code == 404

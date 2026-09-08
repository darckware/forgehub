"""Persistence guarantees for Nexo build and installation history."""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.db.base import AsyncSessionLocal
from app.db.models.client import Client, Workstation
from app.db.models.nexo_installation import (
    NexoAgentBuild,
    WorkstationInstallation,
    WorkstationInstallationEvent,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def ready_build(db, *, os_kind: str) -> NexoAgentBuild:
    build = NexoAgentBuild(
        git_sha=f"{uuid.uuid4().hex}deadbeef",
        agent_version="1.2.3",
        os_kind=os_kind,
        status="ready",
    )
    db.add(build)
    await db.flush()
    return build


async def workstation_for(db) -> tuple[Client, Workstation]:
    client = Client(name=f"Nexo installation test {uuid.uuid4()}")
    db.add(client)
    await db.flush()
    workstation = Workstation(
        client_id=client.id,
        os_kind="linux",
        device_token_hash=uuid.uuid4().hex,
        device_token_issued_at=utcnow(),
    )
    db.add(workstation)
    await db.flush()
    return client, workstation


async def events_for(db, installation_id: uuid.UUID) -> list[WorkstationInstallationEvent]:
    return list((await db.execute(
        select(WorkstationInstallationEvent)
        .where(WorkstationInstallationEvent.installation_id == installation_id)
        .order_by(WorkstationInstallationEvent.created_at)
    )).scalars())


async def cleanup(client_id: uuid.UUID, build_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Client).where(Client.id == client_id))
        await db.commit()
        await db.execute(delete(NexoAgentBuild).where(NexoAgentBuild.id == build_id))
        await db.commit()


@pytest.mark.asyncio
async def test_one_current_installation_per_workstation():
    """Removing the unique workstation constraint would permit two current states."""
    async with AsyncSessionLocal() as db:
        _, workstation = await workstation_for(db)
        build = await ready_build(db, os_kind=workstation.os_kind)
        db.add_all([
            WorkstationInstallation(
                workstation_id=workstation.id,
                build_id=build.id,
                status="package_ready",
                package_generated_at=utcnow(),
            ),
            WorkstationInstallation(
                workstation_id=workstation.id,
                build_id=build.id,
                status="package_ready",
                package_generated_at=utcnow(),
            ),
        ])
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()


@pytest.mark.asyncio
async def test_installation_event_preserves_generation_history():
    """Removing event persistence would lose the auditable package generation."""
    async with AsyncSessionLocal() as db:
        client, workstation = await workstation_for(db)
        build = await ready_build(db, os_kind=workstation.os_kind)
        installation = WorkstationInstallation(
            workstation_id=workstation.id,
            build_id=build.id,
            status="package_ready",
            package_generated_at=utcnow(),
        )
        db.add(installation)
        await db.commit()
        client_id, build_id = client.id, build.id

        try:
            db.add(WorkstationInstallationEvent(
                installation_id=installation.id,
                event_type="package_generated",
                from_status=None,
                to_status="package_ready",
                detail="linux build abc1234",
            ))
            await db.commit()

            events = await events_for(db, installation.id)
            assert [event.event_type for event in events] == ["package_generated"]
            assert events[0].from_status is None
            assert events[0].to_status == "package_ready"
        finally:
            await cleanup(client_id, build_id)

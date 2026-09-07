"""Persistence guarantees for auditable workstation peer grants."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from app.db.base import AsyncSessionLocal
from app.db.models.client import Client, Workstation, WorkstationPeerGrant


async def _client_and_pair(db):
    client = Client(name=f"Test Client {uuid.uuid4()}")
    db.add(client)
    await db.flush()
    workstations = [
        Workstation(
            client_id=client.id,
            os_kind="linux",
            device_token_hash=uuid.uuid4().hex,
            device_token_issued_at=datetime.now(timezone.utc),
        )
        for _ in range(2)
    ]
    db.add_all(workstations)
    await db.flush()
    return client, workstations[0], workstations[1]


async def _cleanup_client(client_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Client).where(Client.id == client_id))
        await db.commit()


@pytest.mark.asyncio
async def test_create_and_revoke_peer_grant():
    async with AsyncSessionLocal() as db:
        client, ws_a, ws_b = await _client_and_pair(db)
        client_id = client.id
        grant = WorkstationPeerGrant(
            workstation_a_id=ws_a.id,
            workstation_b_id=ws_b.id,
            granted_at=datetime.now(timezone.utc),
        )
        db.add(grant)
        await db.commit()

        grant.revoked_at = datetime.now(timezone.utc)
        await db.commit()
        assert grant.revoked_at is not None

    await _cleanup_client(client_id)


@pytest.mark.asyncio
async def test_duplicate_active_pair_is_rejected():
    async with AsyncSessionLocal() as db:
        client, ws_a, ws_b = await _client_and_pair(db)
        client_id = client.id
        db.add(
            WorkstationPeerGrant(
                workstation_a_id=ws_a.id,
                workstation_b_id=ws_b.id,
                granted_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()
        db.add(
            WorkstationPeerGrant(
                workstation_a_id=ws_a.id,
                workstation_b_id=ws_b.id,
                granted_at=datetime.now(timezone.utc),
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()

    await _cleanup_client(client_id)


@pytest.mark.asyncio
async def test_revoked_pair_can_be_granted_again_without_losing_history():
    async with AsyncSessionLocal() as db:
        client, ws_a, ws_b = await _client_and_pair(db)
        client_id = client.id
        first = WorkstationPeerGrant(
            workstation_a_id=ws_a.id,
            workstation_b_id=ws_b.id,
            granted_at=datetime.now(timezone.utc),
            revoked_at=datetime.now(timezone.utc),
        )
        second = WorkstationPeerGrant(
            workstation_a_id=ws_a.id,
            workstation_b_id=ws_b.id,
            granted_at=datetime.now(timezone.utc),
        )
        db.add_all([first, second])
        await db.commit()
        assert first.id != second.id

    await _cleanup_client(client_id)

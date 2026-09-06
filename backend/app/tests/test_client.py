"""Client/Workstation/Irregularity model smoke test -- confirms the tables
exist with the expected columns and constraints, against the real DB."""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.db.base import AsyncSessionLocal
from app.db.models.client import Client, Irregularity, Workstation


@pytest.mark.asyncio
async def test_create_client_workstation_irregularity():
    async with AsyncSessionLocal() as db:
        client = Client(name=f"Test Client {uuid.uuid4()}", headscale_tag=f"tag:cliente-{uuid.uuid4().hex[:8]}")
        db.add(client)
        await db.flush()

        workstation = Workstation(
            client_id=client.id,
            os_kind="linux",
            device_token_hash=uuid.uuid4().hex,
            device_token_issued_at=datetime.now(timezone.utc),
        )
        db.add(workstation)
        await db.flush()

        irregularity = Irregularity(
            workstation_id=workstation.id,
            rule_key="disk_space_low",
            severity="warning",
            detail="disk / at 92%",
            detected_at=datetime.now(timezone.utc),
        )
        db.add(irregularity)
        await db.commit()

        try:
            fetched = (await db.execute(
                select(Irregularity).where(Irregularity.id == irregularity.id)
            )).scalar_one()
            assert fetched.status == "open"
            assert fetched.rule_key == "disk_space_low"
        finally:
            await db.delete(irregularity)
            await db.delete(workstation)
            await db.delete(client)
            await db.commit()


@pytest.mark.asyncio
async def test_irregularity_rejects_invalid_rule_key():
    from sqlalchemy.exc import IntegrityError

    async with AsyncSessionLocal() as db:
        client = Client(name=f"Test Client {uuid.uuid4()}")
        db.add(client)
        await db.flush()
        workstation = Workstation(
            client_id=client.id,
            os_kind="linux",
            device_token_hash=uuid.uuid4().hex,
            device_token_issued_at=datetime.now(timezone.utc),
        )
        db.add(workstation)
        await db.flush()

        db.add(Irregularity(
            workstation_id=workstation.id,
            rule_key="not_a_real_rule",
            severity="warning",
            detail="x",
            detected_at=datetime.now(timezone.utc),
        ))
        with pytest.raises(IntegrityError):
            await db.commit()

        # The failing commit poisons the whole Postgres transaction, so
        # rollback() undoes not just the bad Irregularity insert but also
        # the client/workstation inserts flushed earlier in this same
        # transaction -- nothing is left in the DB to clean up, and the
        # now-transient client/workstation instances can no longer be
        # deleted via the session (they have no persisted identity).
        await db.rollback()

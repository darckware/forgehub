"""Staleness sweep tests -- real DB, no mocking."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.workstation_staleness import run_workstation_staleness_sweep
from app.db.base import AsyncSessionLocal
from app.db.models.client import Client, Irregularity, Workstation


@pytest.mark.asyncio
async def test_stale_workstation_raises_one_irregularity_and_dedupes():
    async with AsyncSessionLocal() as db:
        client = Client(name=f"Test Client {uuid.uuid4()}")
        db.add(client)
        await db.flush()
        workstation = Workstation(
            client_id=client.id,
            os_kind="linux",
            device_token_hash=uuid.uuid4().hex,
            device_token_issued_at=datetime.now(timezone.utc),
            last_report_at=datetime.now(timezone.utc) - timedelta(minutes=30),
        )
        db.add(workstation)
        await db.commit()
        workstation_id, client_id_ = workstation.id, client.id

    try:
        async with AsyncSessionLocal() as db:
            raised = await run_workstation_staleness_sweep(db)
            assert raised >= 1

        async with AsyncSessionLocal() as db:
            raised_again = await run_workstation_staleness_sweep(db)
            # already-open irregularity for this workstation -- no duplicate
            rows = (await db.execute(
                select(Irregularity).where(
                    Irregularity.workstation_id == workstation_id,
                    Irregularity.rule_key == "agent_unreachable",
                )
            )).scalars().all()
            assert len(rows) == 1
    finally:
        async with AsyncSessionLocal() as db:
            client = await db.get(Client, client_id_)
            await db.delete(client)
            await db.commit()


@pytest.mark.asyncio
async def test_fresh_workstation_raises_nothing():
    async with AsyncSessionLocal() as db:
        client = Client(name=f"Test Client {uuid.uuid4()}")
        db.add(client)
        await db.flush()
        workstation = Workstation(
            client_id=client.id,
            os_kind="linux",
            device_token_hash=uuid.uuid4().hex,
            device_token_issued_at=datetime.now(timezone.utc),
            last_report_at=datetime.now(timezone.utc),
        )
        db.add(workstation)
        await db.commit()
        client_id = client.id

    try:
        async with AsyncSessionLocal() as db:
            rows_before = (await db.execute(select(Irregularity))).scalars().all()
            await run_workstation_staleness_sweep(db)
            rows_after = (await db.execute(select(Irregularity))).scalars().all()
            assert len(rows_after) == len(rows_before)
    finally:
        async with AsyncSessionLocal() as db:
            client = await db.get(Client, client_id)
            await db.delete(client)
            await db.commit()

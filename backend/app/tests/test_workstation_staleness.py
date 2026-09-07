"""Staleness sweep tests -- real DB, no mocking."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select

from app.core.workstation_staleness import run_workstation_staleness_sweep
from app.db.base import AsyncSessionLocal
from app.db.models.client import Client, Irregularity, Workstation
from app.db.models.notification import Notification


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

    irregularity_ids = []
    try:
        async with AsyncSessionLocal() as db:
            raised = await run_workstation_staleness_sweep(db)
            assert raised >= 1

        async with AsyncSessionLocal() as db:
            await run_workstation_staleness_sweep(db)
            # already-open irregularity for this workstation -- no duplicate
            rows = (await db.execute(
                select(Irregularity).where(
                    Irregularity.workstation_id == workstation_id,
                    Irregularity.rule_key == "agent_unreachable",
                )
            )).scalars().all()
            assert len(rows) == 1
            # Capture irregularity IDs for notification cleanup
            irregularity_ids = [row.id for row in rows]
    finally:
        async with AsyncSessionLocal() as db:
            # Clean up Notifications created by the sweep (event_key=f"irregularity:{id}")
            for irregularity_id in irregularity_ids:
                await db.execute(
                    delete(Notification).where(
                        Notification.event_key == f"irregularity:{irregularity_id}"
                    )
                )
            # Clean up the client (cascades to workstation and irregularities)
            client = await db.get(Client, client_id_)
            await db.delete(client)
            await db.commit()


@pytest.mark.asyncio
async def test_never_reported_workstation_with_old_token_is_flagged_as_stale():
    async with AsyncSessionLocal() as db:
        client = Client(name=f"Test Client {uuid.uuid4()}")
        db.add(client)
        await db.flush()
        workstation = Workstation(
            client_id=client.id,
            os_kind="linux",
            device_token_hash=uuid.uuid4().hex,
            # never reported: last_report_at stays None. Fall back to
            # device_token_issued_at as the staleness reference -- old enough
            # to clear STALENESS_THRESHOLD.
            device_token_issued_at=datetime.now(timezone.utc) - timedelta(minutes=30),
            last_report_at=None,
        )
        db.add(workstation)
        await db.commit()
        workstation_id, client_id_ = workstation.id, client.id

    irregularity_ids = []
    try:
        async with AsyncSessionLocal() as db:
            raised = await run_workstation_staleness_sweep(db)
            assert raised >= 1

        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(Irregularity).where(
                    Irregularity.workstation_id == workstation_id,
                    Irregularity.rule_key == "agent_unreachable",
                )
            )).scalars().all()
            assert len(rows) == 1
            assert "no report ever received" in rows[0].detail
            irregularity_ids = [row.id for row in rows]
    finally:
        async with AsyncSessionLocal() as db:
            for irregularity_id in irregularity_ids:
                await db.execute(
                    delete(Notification).where(
                        Notification.event_key == f"irregularity:{irregularity_id}"
                    )
                )
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

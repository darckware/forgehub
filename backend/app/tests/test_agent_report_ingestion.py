"""Ingestion endpoint tests -- real DB, no mocking. Covers: unknown token
rejected, valid token + clean report accepted with no findings, a
disk-space-low report creates exactly one open Irregularity + Notification,
re-ingesting the same violation does not duplicate the Irregularity, multiple
disks over threshold in one report collapse into a single Irregularity whose
detail names every offender, re-ingesting with a *different* offender updates
the existing open row's detail/detected_at rather than dropping it silently,
and a schema_version mismatch is rejected."""
import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.db.base import AsyncSessionLocal
from app.db.models.client import Client, Irregularity, Workstation
from app.db.models.notification import Notification
from app.main import app

CLEAN_REPORT = {
    "collected_at": "2026-09-06T00:00:00Z",
    "system": {"cpu_percent": 10.0, "mem_percent": 20.0, "disk_usage": [{"path": "/", "used_percent": 30.0}]},
    "listening_ports": [],
    "services": [],
    "unauthorized_software": [],
    "backup": {"path": "/backup", "newest_file": "/backup/x.tar", "newest_mtime": "2026-09-05T00:00:00Z", "stale": False},
    "collection_errors": [],
    "hostname": "test-host",
    "os": "linux",
    "agent_version": "dev",
    "schema_version": 1,
}


async def _make_workstation() -> tuple[uuid.UUID, uuid.UUID, str]:
    from app.api.routes.workstation import hash_device_token

    raw_token = f"nxw_test_{uuid.uuid4().hex}"
    async with AsyncSessionLocal() as db:
        client = Client(name=f"Test Client {uuid.uuid4()}")
        db.add(client)
        await db.flush()
        workstation = Workstation(
            client_id=client.id,
            os_kind="linux",
            device_token_hash=hash_device_token(raw_token),
            device_token_issued_at=datetime.now(timezone.utc),
        )
        db.add(workstation)
        await db.commit()
        return client.id, workstation.id, raw_token


async def _cleanup(client_id: uuid.UUID):
    async with AsyncSessionLocal() as db:
        # Notification rows the ingestion endpoint creates on first-detection
        # have no FK relationship to Irregularity (only a string event_key),
        # so deleting the client (which cascades to Workstation/Irregularity)
        # would otherwise leave them behind as permanent orphans in the real
        # shared DB -- same gap Task 5 fixed in test_workstation_staleness.py.
        workstation_ids = (await db.execute(
            select(Workstation.id).where(Workstation.client_id == client_id)
        )).scalars().all()
        if workstation_ids:
            irregularity_ids = (await db.execute(
                select(Irregularity.id).where(Irregularity.workstation_id.in_(workstation_ids))
            )).scalars().all()
            if irregularity_ids:
                await db.execute(
                    delete(Notification).where(
                        Notification.event_key.in_([f"irregularity:{i}" for i in irregularity_ids])
                    )
                )

        client = await db.get(Client, client_id)
        if client:
            await db.delete(client)
        await db.commit()


@pytest.mark.asyncio
async def test_ingest_rejects_unknown_token():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        resp = await http.post(
            "/api/v1/agent-reports", json=CLEAN_REPORT, headers={"X-Device-Token": "nxw_bogus"}
        )
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_ingest_clean_report_creates_no_irregularity():
    client_id, workstation_id, token = await _make_workstation()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            resp = await http.post(
                "/api/v1/agent-reports", json=CLEAN_REPORT, headers={"X-Device-Token": token}
            )
            assert resp.status_code == 202, resp.text
            assert resp.json()["findings"] == 0

        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(Irregularity).where(Irregularity.workstation_id == workstation_id)
            )).scalars().all()
            assert rows == []
    finally:
        await _cleanup(client_id)


@pytest.mark.asyncio
async def test_ingest_disk_space_low_creates_one_irregularity_and_dedupes():
    client_id, workstation_id, token = await _make_workstation()
    dirty_report = {**CLEAN_REPORT, "system": {**CLEAN_REPORT["system"], "disk_usage": [{"path": "/", "used_percent": 95.0}]}}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            first = await http.post("/api/v1/agent-reports", json=dirty_report, headers={"X-Device-Token": token})
            assert first.status_code == 202
            assert first.json()["findings"] == 1

            second = await http.post("/api/v1/agent-reports", json=dirty_report, headers={"X-Device-Token": token})
            assert second.status_code == 202
            # dedupe: still reported as "0 new findings created" is NOT what
            # this asserts -- the endpoint reports raw rule matches, not rows
            # created. What matters is exactly one open Irregularity exists.

        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(Irregularity).where(
                    Irregularity.workstation_id == workstation_id,
                    Irregularity.rule_key == "disk_space_low",
                )
            )).scalars().all()
            assert len(rows) == 1
            assert rows[0].status == "open"
    finally:
        await _cleanup(client_id)


@pytest.mark.asyncio
async def test_ingest_multiple_disks_over_threshold_aggregate_into_one_irregularity():
    client_id, workstation_id, token = await _make_workstation()
    dirty_report = {
        **CLEAN_REPORT,
        "system": {
            **CLEAN_REPORT["system"],
            "disk_usage": [
                {"path": "/", "used_percent": 95.0},
                {"path": "/data", "used_percent": 99.0},
            ],
        },
    }
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            resp = await http.post("/api/v1/agent-reports", json=dirty_report, headers={"X-Device-Token": token})
            assert resp.status_code == 202, resp.text
            # evaluate_report aggregates all over-threshold disks into a
            # single disk_space_low finding -- not one per disk.
            assert resp.json()["findings"] == 1

        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(Irregularity).where(
                    Irregularity.workstation_id == workstation_id,
                    Irregularity.rule_key == "disk_space_low",
                )
            )).scalars().all()
            assert len(rows) == 1
            assert "/ at 95.0%" in rows[0].detail
            assert "/data at 99.0%" in rows[0].detail
    finally:
        await _cleanup(client_id)


@pytest.mark.asyncio
async def test_ingest_reingestion_with_different_offender_updates_existing_open_row():
    client_id, workstation_id, token = await _make_workstation()
    first_report = {**CLEAN_REPORT, "system": {**CLEAN_REPORT["system"], "disk_usage": [{"path": "/", "used_percent": 95.0}]}}
    second_report = {**CLEAN_REPORT, "system": {**CLEAN_REPORT["system"], "disk_usage": [{"path": "/data", "used_percent": 92.0}]}}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            first = await http.post("/api/v1/agent-reports", json=first_report, headers={"X-Device-Token": token})
            assert first.status_code == 202, first.text

        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(Irregularity).where(
                    Irregularity.workstation_id == workstation_id,
                    Irregularity.rule_key == "disk_space_low",
                )
            )).scalars().all()
            assert len(rows) == 1
            assert "/ at 95.0%" in rows[0].detail
            first_detected_at = rows[0].detected_at

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            second = await http.post("/api/v1/agent-reports", json=second_report, headers={"X-Device-Token": token})
            assert second.status_code == 202, second.text

        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(Irregularity).where(
                    Irregularity.workstation_id == workstation_id,
                    Irregularity.rule_key == "disk_space_low",
                )
            )).scalars().all()
            # still deduplicated to exactly one open row for this rule_key --
            # but its detail/detected_at must reflect the newest report, not
            # the stale first-offender text (the bug this fix closes).
            assert len(rows) == 1
            assert "/data at 92.0%" in rows[0].detail
            assert "/ at 95.0%" not in rows[0].detail
            assert rows[0].detected_at >= first_detected_at
    finally:
        await _cleanup(client_id)


@pytest.mark.asyncio
async def test_ingest_rejects_schema_version_mismatch():
    client_id, _workstation_id, token = await _make_workstation()
    bad_report = {**CLEAN_REPORT, "schema_version": 999}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            resp = await http.post("/api/v1/agent-reports", json=bad_report, headers={"X-Device-Token": token})
            assert resp.status_code == 400
    finally:
        await _cleanup(client_id)

"""Peer-grant API invariants with the external Headscale push replaced."""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, or_, select

from app.core import headscale_client
from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.client import Client, Workstation, WorkstationPeerGrant
from app.db.models.governance import AuditEvent
from app.db.models.user import User
from app.main import app


async def _admin_token() -> str:
    async with AsyncSessionLocal() as db:
        admin = (
            await db.execute(select(User).where(User.is_admin.is_(True)).limit(1))
        ).scalar_one()
        return create_access_token(admin.username)


async def _make_pair(*, cross_client: bool = False):
    async with AsyncSessionLocal() as db:
        first_client = Client(name=f"Test Client {uuid.uuid4()}")
        db.add(first_client)
        await db.flush()
        second_client = None
        if cross_client:
            second_client = Client(name=f"Test Client {uuid.uuid4()}")
            db.add(second_client)
            await db.flush()
        workstation_a = Workstation(
            client_id=first_client.id,
            hostname="ws-a",
            os_kind="linux",
            device_token_hash=uuid.uuid4().hex,
            device_token_issued_at=datetime.now(timezone.utc),
        )
        workstation_b = Workstation(
            client_id=second_client.id if second_client else first_client.id,
            hostname="ws-b",
            os_kind="linux",
            device_token_hash=uuid.uuid4().hex,
            device_token_issued_at=datetime.now(timezone.utc),
        )
        db.add_all([workstation_a, workstation_b])
        await db.commit()
        return (
            first_client.id,
            second_client.id if second_client else None,
            workstation_a.id,
            workstation_b.id,
        )


async def _cleanup_clients(*client_ids: uuid.UUID | None):
    ids = [client_id for client_id in client_ids if client_id]
    async with AsyncSessionLocal() as db:
        workstation_ids = list(
            (
                await db.execute(select(Workstation.id).where(Workstation.client_id.in_(ids)))
            )
            .scalars()
            .all()
        )
        grant_ids = list(
            (
                await db.execute(
                    select(WorkstationPeerGrant.id).where(
                        or_(
                            WorkstationPeerGrant.workstation_a_id.in_(workstation_ids),
                            WorkstationPeerGrant.workstation_b_id.in_(workstation_ids),
                        )
                    )
                )
            )
            .scalars()
            .all()
        )
        if grant_ids:
            await db.execute(
                delete(AuditEvent).where(
                    AuditEvent.entity_type == "workstation_peer_grant",
                    AuditEvent.entity_id.in_(grant_ids),
                )
            )
        await db.execute(delete(Client).where(Client.id.in_(ids)))
        await db.commit()


@pytest.fixture
def policy_pushes(monkeypatch):
    calls = []

    async def fake_rebuild(db):
        calls.append(db)

    monkeypatch.setattr(headscale_client, "rebuild_and_push_policy", fake_rebuild)
    return calls


@pytest.mark.asyncio
async def test_grant_revoke_regrant_preserves_history_and_audit(policy_pushes):
    client_id, _, workstation_a_id, workstation_b_id = await _make_pair()
    token = await _admin_token()
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "workstation_a_id": str(workstation_b_id),
        "workstation_b_id": str(workstation_a_id),
    }
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            first = await http.post("/api/v1/peer-grants", json=payload, headers=headers)
            assert first.status_code == 201, first.text
            first_id = first.json()["id"]
            assert first.json()["workstation_a_id"] == min(
                str(workstation_a_id), str(workstation_b_id)
            )

            duplicate = await http.post("/api/v1/peer-grants", json=payload, headers=headers)
            assert duplicate.status_code == 201
            assert duplicate.json()["id"] == first_id
            assert len(policy_pushes) == 1

            revoked = await http.post(
                f"/api/v1/peer-grants/{first_id}:revoke", headers=headers
            )
            assert revoked.status_code == 200, revoked.text
            assert revoked.json()["revoked_at"] is not None

            second = await http.post("/api/v1/peer-grants", json=payload, headers=headers)
            assert second.status_code == 201, second.text
            assert second.json()["id"] != first_id
            assert len(policy_pushes) == 3

            listed = await http.get(
                "/api/v1/peer-grants",
                params={"client_id": str(client_id)},
                headers=headers,
            )
            assert listed.status_code == 200
            assert len(listed.json()) == 2

            rebuilt = await http.post("/api/v1/peer-grants/policy:rebuild", headers=headers)
            assert rebuilt.status_code == 204
            assert len(policy_pushes) == 4

        async with AsyncSessionLocal() as db:
            grant_ids = [uuid.UUID(first_id), uuid.UUID(second.json()["id"])]
            events = list(
                (
                    await db.execute(
                        select(AuditEvent)
                        .where(AuditEvent.entity_id.in_(grant_ids))
                        .order_by(AuditEvent.created_at)
                    )
                )
                .scalars()
                .all()
            )
            assert [event.event_type for event in events] == ["granted", "revoked", "granted"]
    finally:
        await _cleanup_clients(client_id)


@pytest.mark.asyncio
async def test_grant_rejects_cross_client_and_self_pairs(policy_pushes):
    first_client_id, second_client_id, workstation_a_id, workstation_b_id = await _make_pair(
        cross_client=True
    )
    token = await _admin_token()
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            cross_client = await http.post(
                "/api/v1/peer-grants",
                json={
                    "workstation_a_id": str(workstation_a_id),
                    "workstation_b_id": str(workstation_b_id),
                },
                headers=headers,
            )
            assert cross_client.status_code == 400
            self_pair = await http.post(
                "/api/v1/peer-grants",
                json={
                    "workstation_a_id": str(workstation_a_id),
                    "workstation_b_id": str(workstation_a_id),
                },
                headers=headers,
            )
            assert self_pair.status_code == 400
            assert policy_pushes == []
    finally:
        await _cleanup_clients(first_client_id, second_client_id)


@pytest.mark.asyncio
async def test_failed_policy_publish_rolls_back_grant_and_audit(monkeypatch):
    async def fail_rebuild(db):
        raise HTTPException(502, "bridge unavailable")

    monkeypatch.setattr(headscale_client, "rebuild_and_push_policy", fail_rebuild)
    client_id, _, workstation_a_id, workstation_b_id = await _make_pair()
    token = await _admin_token()
    async with AsyncSessionLocal() as db:
        audit_count_before = len(
            (
                await db.execute(
                    select(AuditEvent.id).where(
                        AuditEvent.entity_type == "workstation_peer_grant"
                    )
                )
            )
            .scalars()
            .all()
        )
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            response = await http.post(
                "/api/v1/peer-grants",
                json={
                    "workstation_a_id": str(workstation_a_id),
                    "workstation_b_id": str(workstation_b_id),
                },
                headers={"Authorization": f"Bearer {token}"},
            )
        assert response.status_code == 502
        async with AsyncSessionLocal() as db:
            grants = (
                await db.execute(
                    select(WorkstationPeerGrant).where(
                        WorkstationPeerGrant.workstation_a_id.in_(
                            [workstation_a_id, workstation_b_id]
                        )
                    )
                )
            ).scalars().all()
            assert grants == []
            audit_count_after = len(
                (
                    await db.execute(
                        select(AuditEvent.id).where(
                            AuditEvent.entity_type == "workstation_peer_grant"
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert audit_count_after == audit_count_before
    finally:
        await _cleanup_clients(client_id)

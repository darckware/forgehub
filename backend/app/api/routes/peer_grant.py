"""Auditable, reversible same-client workstation communication grants."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.peer_grant import PeerGrantCreate, PeerGrantOut
from app.core import headscale_client
from app.core.deps import get_current_admin
from app.db.base import get_db
from app.db.models.client import Workstation, WorkstationPeerGrant
from app.db.models.governance import AuditEvent
from app.db.models.user import User

router = APIRouter(prefix="/api/v1/peer-grants", tags=["peer-grants"])


def _canonical_pair(a: uuid.UUID, b: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    return (a, b) if str(a) < str(b) else (b, a)


@router.get("", response_model=list[PeerGrantOut])
async def list_peer_grants(client_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    workstation_ids = list(
        (
            await db.execute(select(Workstation.id).where(Workstation.client_id == client_id))
        )
        .scalars()
        .all()
    )
    if not workstation_ids:
        return []
    grants = await db.execute(
        select(WorkstationPeerGrant)
        .where(
            or_(
                WorkstationPeerGrant.workstation_a_id.in_(workstation_ids),
                WorkstationPeerGrant.workstation_b_id.in_(workstation_ids),
            )
        )
        .order_by(WorkstationPeerGrant.granted_at.desc())
    )
    return grants.scalars().all()


@router.post("/policy:rebuild", status_code=204)
async def rebuild_policy(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    await headscale_client.rebuild_and_push_policy(db)
    return Response(status_code=204)


@router.post("", response_model=PeerGrantOut, status_code=201)
async def create_peer_grant(
    payload: PeerGrantCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    workstation_a = await db.get(Workstation, payload.workstation_a_id)
    workstation_b = await db.get(Workstation, payload.workstation_b_id)
    if workstation_a is None or workstation_b is None:
        raise HTTPException(404, "Workstation not found")
    if workstation_a.id == workstation_b.id:
        raise HTTPException(400, "Cannot grant a workstation peer access to itself")
    if workstation_a.client_id != workstation_b.client_id:
        raise HTTPException(400, "Both workstations must belong to the same Client")

    a_id, b_id = _canonical_pair(workstation_a.id, workstation_b.id)
    existing = (
        await db.execute(
            select(WorkstationPeerGrant).where(
                WorkstationPeerGrant.workstation_a_id == a_id,
                WorkstationPeerGrant.workstation_b_id == b_id,
                WorkstationPeerGrant.revoked_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    grant = WorkstationPeerGrant(
        workstation_a_id=a_id,
        workstation_b_id=b_id,
        granted_by_user_id=admin.id,
        granted_at=datetime.now(timezone.utc),
    )
    db.add(grant)
    await db.flush()
    db.add(
        AuditEvent(
            entity_type="workstation_peer_grant",
            entity_id=grant.id,
            event_type="granted",
            actor=admin.username,
            payload={"workstation_a_id": str(a_id), "workstation_b_id": str(b_id)},
        )
    )
    await db.flush()
    try:
        await headscale_client.rebuild_and_push_policy(db)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await db.refresh(grant)
    return grant


@router.post("/{grant_id}:revoke", response_model=PeerGrantOut)
async def revoke_peer_grant(
    grant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    grant = await db.get(WorkstationPeerGrant, grant_id)
    if grant is None:
        raise HTTPException(404, "Peer grant not found")
    if grant.revoked_at is not None:
        return grant

    grant.revoked_at = datetime.now(timezone.utc)
    db.add(
        AuditEvent(
            entity_type="workstation_peer_grant",
            entity_id=grant.id,
            event_type="revoked",
            actor=admin.username,
            payload={
                "workstation_a_id": str(grant.workstation_a_id),
                "workstation_b_id": str(grant.workstation_b_id),
            },
        )
    )
    await db.flush()
    try:
        await headscale_client.rebuild_and_push_policy(db)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await db.refresh(grant)
    return grant

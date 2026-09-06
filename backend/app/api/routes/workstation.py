"""Workstation domain -- Nexo-monitored devices, one per Client.

Endpoints:
  GET    /api/v1/workstations                 -- list all (optionally ?client_id=)
  POST   /api/v1/workstations                 -- create + issue device token (shown once)
  GET    /api/v1/workstations/{id}             -- get one
  DELETE /api/v1/workstations/{id}             -- delete
  POST   /api/v1/workstations/{id}/token:reissue -- revoke old token, issue a new one (shown once)
  POST   /api/v1/workstations/{id}/token:revoke  -- revoke without issuing a replacement
"""
import hashlib
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.client import (
    WorkstationCreate,
    WorkstationOut,
    WorkstationTokenIssued,
)
from app.core.deps import get_current_admin
from app.db.base import get_db
from app.db.models.client import Client, Workstation
from app.db.models.user import User

router = APIRouter(prefix="/api/v1/workstations", tags=["workstations"])


def _generate_device_token() -> str:
    # "nxw_" prefix (Nexo Workstation) mirrors this codebase's existing
    # "agt_" convention for agent service credentials -- lets the auth
    # layer in a future task tell token kinds apart on sight if ever needed.
    return f"nxw_{secrets.token_urlsafe(32)}"


def hash_device_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


@router.get("", response_model=list[WorkstationOut])
async def list_workstations(
    client_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Workstation)
    if client_id is not None:
        query = query.where(Workstation.client_id == client_id)
    result = await db.execute(query.order_by(Workstation.created_at))
    return result.scalars().all()


@router.post("", response_model=WorkstationTokenIssued, status_code=201)
async def create_workstation(
    payload: WorkstationCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    if not await db.get(Client, payload.client_id):
        raise HTTPException(404, "Client not found")

    raw_token = _generate_device_token()
    workstation = Workstation(
        client_id=payload.client_id,
        os_kind=payload.os_kind,
        device_token_hash=hash_device_token(raw_token),
        device_token_issued_at=datetime.now(timezone.utc),
    )
    db.add(workstation)
    await db.commit()
    await db.refresh(workstation)
    return WorkstationTokenIssued(workstation=workstation, device_token=raw_token)


@router.get("/{workstation_id}", response_model=WorkstationOut)
async def get_workstation(workstation_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    workstation = await db.get(Workstation, workstation_id)
    if not workstation:
        raise HTTPException(404, "Workstation not found")
    return workstation


@router.delete("/{workstation_id}", status_code=204)
async def delete_workstation(
    workstation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    workstation = await db.get(Workstation, workstation_id)
    if not workstation:
        raise HTTPException(404, "Workstation not found")
    await db.delete(workstation)
    await db.commit()


@router.post("/{workstation_id}/token:reissue", response_model=WorkstationTokenIssued)
async def reissue_workstation_token(
    workstation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    workstation = await db.get(Workstation, workstation_id)
    if not workstation:
        raise HTTPException(404, "Workstation not found")

    raw_token = _generate_device_token()
    workstation.device_token_hash = hash_device_token(raw_token)
    workstation.device_token_issued_at = datetime.now(timezone.utc)
    workstation.device_token_revoked_at = None
    await db.commit()
    await db.refresh(workstation)
    return WorkstationTokenIssued(workstation=workstation, device_token=raw_token)


@router.post("/{workstation_id}/token:revoke", response_model=WorkstationOut)
async def revoke_workstation_token(
    workstation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    workstation = await db.get(Workstation, workstation_id)
    if not workstation:
        raise HTTPException(404, "Workstation not found")
    workstation.device_token_revoked_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(workstation)
    return workstation

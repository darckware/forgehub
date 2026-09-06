"""Irregularities screen backend.

Endpoints:
  GET   /api/v1/irregularities                    -- list, filterable
  PATCH /api/v1/irregularities/{id}                -- change status (ack/resolve)
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.client import IrregularityOut, IrregularityResolve
from app.core.deps import get_current_user
from app.db.base import get_db
from app.db.models.client import IRREGULARITY_STATUSES, Irregularity
from app.db.models.user import User

router = APIRouter(prefix="/api/v1/irregularities", tags=["irregularities"])


@router.get("", response_model=list[IrregularityOut])
async def list_irregularities(
    status_filter: str | None = None,
    severity: str | None = None,
    workstation_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Irregularity)
    if status_filter is not None:
        query = query.where(Irregularity.status == status_filter)
    if severity is not None:
        query = query.where(Irregularity.severity == severity)
    if workstation_id is not None:
        query = query.where(Irregularity.workstation_id == workstation_id)
    result = await db.execute(query.order_by(Irregularity.detected_at.desc()))
    return result.scalars().all()


@router.patch("/{irregularity_id}", response_model=IrregularityOut)
async def update_irregularity_status(
    irregularity_id: uuid.UUID,
    payload: IrregularityResolve,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.status not in IRREGULARITY_STATUSES:
        raise HTTPException(400, f"status must be one of {IRREGULARITY_STATUSES}")

    irregularity = await db.get(Irregularity, irregularity_id)
    if not irregularity:
        raise HTTPException(404, "Irregularity not found")

    irregularity.status = payload.status
    if payload.status == "resolved":
        irregularity.resolved_at = datetime.now(timezone.utc)
        irregularity.resolved_by_user_id = current_user.id
    await db.commit()
    await db.refresh(irregularity)
    return irregularity

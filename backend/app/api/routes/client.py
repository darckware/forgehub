"""Client domain -- companies Marcelo supports with Nexo-monitored workstations.

Endpoints:
  GET    /api/v1/clients       -- list all
  POST   /api/v1/clients       -- create
  GET    /api/v1/clients/{id}  -- get one
  PUT    /api/v1/clients/{id}  -- update
  DELETE /api/v1/clients/{id}  -- delete

Creating, renaming, or deleting a client republishes the full Headscale
policy. Database work stays uncommitted until publication succeeds so an
operational bridge failure cannot leave a client change falsely accepted.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.client import ClientCreate, ClientOut, ClientUpdate
from app.core import headscale_client
from app.core.deps import get_current_admin
from app.db.base import get_db
from app.db.models.client import SUPPORT_PLANS, Client
from app.db.models.client_report import ClientReport
from app.db.models.user import User

router = APIRouter(prefix="/api/v1/clients", tags=["clients"])


@router.get("", response_model=list[ClientOut])
async def list_clients(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Client).order_by(Client.name))
    return result.scalars().all()


@router.post("", response_model=ClientOut, status_code=201)
async def create_client(
    payload: ClientCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    if payload.support_plan is not None and payload.support_plan not in SUPPORT_PLANS:
        raise HTTPException(400, f"support_plan must be one of {SUPPORT_PLANS}")

    client = Client(
        **payload.model_dump(),
        headscale_tag=f"tag:cliente-{headscale_client.slugify_client_name(payload.name)}",
    )
    db.add(client)
    await db.flush()
    try:
        await headscale_client.rebuild_and_push_policy(db)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await db.refresh(client)
    return client


@router.get("/{client_id}", response_model=ClientOut)
async def get_client(client_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    client = await db.get(Client, client_id)
    if not client:
        raise HTTPException(404, "Client not found")
    return client


@router.put("/{client_id}", response_model=ClientOut)
async def update_client(
    client_id: uuid.UUID,
    payload: ClientUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    client = await db.get(Client, client_id)
    if not client:
        raise HTTPException(404, "Client not found")

    updates = payload.model_dump(exclude_unset=True)
    if "support_plan" in updates and updates["support_plan"] is not None and updates["support_plan"] not in SUPPORT_PLANS:
        raise HTTPException(400, f"support_plan must be one of {SUPPORT_PLANS}")
    if "name" in updates and updates["name"] is None:
        raise HTTPException(400, "name cannot be null")

    for field, value in updates.items():
        setattr(client, field, value)
    policy_changed = "name" in updates
    if policy_changed:
        client.headscale_tag = f"tag:cliente-{headscale_client.slugify_client_name(client.name)}"
    await db.flush()
    try:
        if policy_changed:
            await headscale_client.rebuild_and_push_policy(db)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await db.refresh(client)
    return client


@router.delete("/{client_id}", status_code=204)
async def delete_client(
    client_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    client = await db.get(Client, client_id)
    if not client:
        raise HTTPException(404, "Client not found")
    if (await db.execute(select(ClientReport.id).where(ClientReport.client_id == client_id).limit(1))).scalar_one_or_none() is not None:
        raise HTTPException(409, "Client has retained reports")
    await db.delete(client)
    await db.flush()
    try:
        await headscale_client.rebuild_and_push_policy(db)
        await db.commit()
    except Exception:
        await db.rollback()
        raise

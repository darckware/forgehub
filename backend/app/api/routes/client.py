"""Client domain -- companies Marcelo supports with Nexo-monitored workstations.

Endpoints:
  GET    /api/v1/clients       -- list all
  POST   /api/v1/clients       -- create
  GET    /api/v1/clients/{id}  -- get one
  PUT    /api/v1/clients/{id}  -- update
  DELETE /api/v1/clients/{id}  -- delete

Headscale tag provisioning (spec section 5) is deliberately NOT part of this
task -- headscale_tag stays nullable and unset here; a later plan wires
POST here to also call the Headscale ACL adapter.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.client import ClientCreate, ClientOut, ClientUpdate
from app.core.deps import get_current_admin
from app.db.base import get_db
from app.db.models.client import Client
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
    client = Client(**payload.model_dump())
    db.add(client)
    await db.commit()
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
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(client, field, value)
    await db.commit()
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
    await db.delete(client)
    await db.commit()

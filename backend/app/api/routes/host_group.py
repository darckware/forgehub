"""Host groups – named sets of machines (servers/workstations), usually per
Darckware client, so a command or maintenance can target a whole set
(Remote Access phase 2, docs/architecture/REMOTE_MAINTENANCE_PLAN.md).

Endpoints:
  GET    /api/v1/host-groups        – list (optional ?darckware_client_id=)
  POST   /api/v1/host-groups        – create, optionally with members
  PUT    /api/v1/host-groups/{id}   – edit; `server_ids` replaces the members
  DELETE /api/v1/host-groups/{id}   – delete the group (machines stay)
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.server import HostGroupCreate, HostGroupOut, HostGroupUpdate
from app.db.base import get_db
from app.db.models.server import HostGroup, HostGroupMember, Server

router = APIRouter(prefix="/api/v1/host-groups", tags=["servers"])


async def _members(db: AsyncSession, group_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[uuid.UUID]]:
    if not group_ids:
        return {}
    rows = await db.execute(
        select(HostGroupMember.group_id, HostGroupMember.server_id).where(
            HostGroupMember.group_id.in_(group_ids)
        )
    )
    out: dict[uuid.UUID, list[uuid.UUID]] = {}
    for group_id, server_id in rows.all():
        out.setdefault(group_id, []).append(server_id)
    return out


async def _out(db: AsyncSession, group: HostGroup) -> HostGroupOut:
    out = HostGroupOut.model_validate(group)
    out.server_ids = (await _members(db, [group.id])).get(group.id, [])
    return out


async def _set_members(db: AsyncSession, group_id: uuid.UUID, server_ids: list[uuid.UUID]) -> None:
    wanted = set(server_ids)
    if wanted:
        found = set((await db.execute(select(Server.id).where(Server.id.in_(wanted)))).scalars())
        if missing := wanted - found:
            raise HTTPException(status_code=422, detail=f"Unknown machine(s): {sorted(map(str, missing))}")
    await db.execute(delete(HostGroupMember).where(HostGroupMember.group_id == group_id))
    for server_id in wanted:
        db.add(HostGroupMember(group_id=group_id, server_id=server_id))


async def _commit(db: AsyncSession) -> None:
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A group with this name already exists for this client") from None


@router.get("", response_model=list[HostGroupOut])
async def list_host_groups(
    darckware_client_id: uuid.UUID | None = None, db: AsyncSession = Depends(get_db)
):
    query = select(HostGroup).order_by(HostGroup.darckware_client_name, HostGroup.name)
    if darckware_client_id is not None:
        query = query.where(HostGroup.darckware_client_id == darckware_client_id)
    groups = list((await db.execute(query)).scalars().all())
    members = await _members(db, [g.id for g in groups])
    out = []
    for group in groups:
        item = HostGroupOut.model_validate(group)
        item.server_ids = members.get(group.id, [])
        out.append(item)
    return out


@router.post("", response_model=HostGroupOut, status_code=status.HTTP_201_CREATED)
async def create_host_group(payload: HostGroupCreate, db: AsyncSession = Depends(get_db)):
    fields = payload.model_dump()
    server_ids = fields.pop("server_ids")
    group = HostGroup(**fields)
    db.add(group)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A group with this name already exists for this client") from None
    await _set_members(db, group.id, server_ids)
    await _commit(db)
    await db.refresh(group)
    return await _out(db, group)


@router.put("/{group_id}", response_model=HostGroupOut)
async def update_host_group(
    group_id: uuid.UUID, payload: HostGroupUpdate, db: AsyncSession = Depends(get_db)
):
    group = await db.get(HostGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    fields = payload.model_dump(exclude_unset=True)
    server_ids = fields.pop("server_ids", None)
    for field, value in fields.items():
        setattr(group, field, value)
    if server_ids is not None:
        await _set_members(db, group.id, server_ids)
    await _commit(db)
    await db.refresh(group)
    return await _out(db, group)


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_host_group(group_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    group = await db.get(HostGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    await db.delete(group)
    await db.commit()

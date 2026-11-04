"""CRUD for the service-line catalog."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.service_line import ServiceLineCreate, ServiceLineOut, ServiceLineUpdate
from app.core.deps import get_current_admin, get_current_user
from app.db.base import get_db
from app.db.models.service_line import ServiceLine
from app.db.models.project import Project

router = APIRouter(prefix="/api/v1/service-lines", tags=["service-lines"])


async def _get(db: AsyncSession, line_id: uuid.UUID) -> ServiceLine:
    line = await db.get(ServiceLine, line_id)
    if line is None:
        raise HTTPException(404, "Service line not found")
    return line


@router.get("", response_model=list[ServiceLineOut], dependencies=[Depends(get_current_user)])
async def list_lines(db: AsyncSession = Depends(get_db)):
    return list((await db.scalars(select(ServiceLine).order_by(ServiceLine.name))).all())


@router.get("/{line_id}", response_model=ServiceLineOut, dependencies=[Depends(get_current_user)])
async def get_line(line_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await _get(db, line_id)


async def _commit(db: AsyncSession):
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Service line conflicts with an existing row") from None


@router.post("", response_model=ServiceLineOut, status_code=201, dependencies=[Depends(get_current_admin)])
async def create_line(payload: ServiceLineCreate, db: AsyncSession = Depends(get_db)):
    line = ServiceLine(**payload.model_dump())
    db.add(line)
    await _commit(db)
    await db.refresh(line)
    return line


@router.patch("/{line_id}", response_model=ServiceLineOut, dependencies=[Depends(get_current_admin)])
async def update_line(line_id: uuid.UUID, payload: ServiceLineUpdate, db: AsyncSession = Depends(get_db)):
    line = await _get(db, line_id)
    data = payload.model_dump(exclude_unset=True)
    for field in ("slug", "name", "stages", "required_documents", "evidence_types", "default_agents", "client_visible", "is_active"):
        if field in data and data[field] is None:
            raise HTTPException(422, f"{field} cannot be null")
    for field, value in data.items():
        setattr(line, field, value)
    await _commit(db)
    await db.refresh(line)
    return line


@router.delete("/{line_id}", status_code=204, dependencies=[Depends(get_current_admin)])
async def deactivate_line(line_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    line = await _get(db, line_id)
    if await db.scalar(select(Project.id).where(Project.service_line_id == line_id).limit(1)) is not None:
        raise HTTPException(409, "Service line has projects")
    line.is_active = False
    await _commit(db)
    return Response(status_code=204)

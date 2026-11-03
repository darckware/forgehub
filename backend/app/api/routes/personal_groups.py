"""Registry of real monitored WhatsApp groups; private to the owner and Maia."""
from fastapi import APIRouter, Depends, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.personal import personal_actor
from app.api.schemas.personal_contacts import GroupCaptureCreate, SuggestionOut, WhatsAppGroupOut, WhatsAppGroupRegister
from app.core import personal_captures as capture
from app.db.base import get_db
from app.db.models.personal import PersonalCaptureSuggestion, PersonalWhatsAppGroup
from app.mcp import personal_group_sources as sources

router = APIRouter(prefix='/api/v1/personal', tags=['personal'])


@router.get('/groups', response_model=list[WhatsAppGroupOut])
async def list_groups(actor: str = Depends(personal_actor), db: AsyncSession = Depends(get_db)):
    monitored = capture.source_call(sources.monitored_ids)
    groups = list((await db.execute(select(PersonalWhatsAppGroup).where(PersonalWhatsAppGroup.whatsapp_id.in_(monitored)).order_by(PersonalWhatsAppGroup.name))).scalars())
    counts = (await db.execute(select(PersonalCaptureSuggestion.group_id, PersonalCaptureSuggestion.status, func.count()).where(PersonalCaptureSuggestion.group_id.in_([g.id for g in groups])).group_by(PersonalCaptureSuggestion.group_id, PersonalCaptureSuggestion.status))).all() if groups else []
    totals = {(group_id, state): count for group_id, state, count in counts}
    return [WhatsAppGroupOut.model_validate(g).model_copy(update={'pending_suggestions': totals.get((g.id, 'pending'), 0), 'accepted_suggestions': totals.get((g.id, 'accepted'), 0)}) for g in groups]


@router.post('/groups', response_model=WhatsAppGroupOut, status_code=status.HTTP_201_CREATED)
async def register_group(payload: WhatsAppGroupRegister, actor: str = Depends(personal_actor), db: AsyncSession = Depends(get_db)):
    group = await capture.ensure_group(db, payload.whatsapp_id, actor)
    await db.commit()
    await db.refresh(group)
    return WhatsAppGroupOut.model_validate(group)


@router.post('/groups:sync', response_model=list[WhatsAppGroupOut])
async def sync_groups(actor: str = Depends(personal_actor), db: AsyncSession = Depends(get_db)):
    for whatsapp_id in sorted(capture.source_call(sources.monitored_ids)):
        await capture.ensure_group(db, whatsapp_id, actor)
    await db.commit()
    return await list_groups(actor=actor, db=db)


@router.post('/groups/captures', response_model=SuggestionOut, status_code=status.HTTP_201_CREATED)
async def capture_from_group(payload: GroupCaptureCreate, actor: str = Depends(personal_actor), db: AsyncSession = Depends(get_db)):
    return await capture.capture_group(db, payload, actor)

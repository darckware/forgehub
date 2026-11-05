"""Registry of real monitored WhatsApp groups; private to the owner and Maia."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.personal import personal_actor
from app.api.schemas.personal_contacts import GroupCaptureCreate, SuggestionOut, WhatsAppGroupOut, WhatsAppGroupRegister
from app.core import personal_captures as capture
from app.core.config import settings
from app.core.dispatch_signal import wake_scheduled_dispatch
from app.core.instructor_group import GROUP_CHANNEL, HOURLY_LIMIT, capture_body
from app.db.base import get_db
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand
from app.db.models.personal import PersonalCaptureSuggestion, PersonalWhatsAppGroup
from app.mcp import personal_group_sources as sources

router = APIRouter(prefix='/api/v1/personal', tags=['personal'])


class InstructorRequestIn(BaseModel):
    group_id: str = Field(min_length=1, max_length=100)
    author: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=4000)


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


@router.post('/groups/instructor-requests', status_code=status.HTTP_201_CREATED)
async def capture_instructor_request(payload: InstructorRequestIn, actor: str = Depends(personal_actor),
                                     db: AsyncSession = Depends(get_db)):
    """A message of the instructors' group that called the Maia: it becomes a task, never a conversation."""
    group = settings.MAIA_INSTRUCTOR_GROUP_ID
    if not group:
        raise HTTPException(503, 'Instructor group is not configured')
    if payload.group_id != group:
        raise HTTPException(403, 'This group is not served')
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    recent = await db.scalar(select(func.count()).select_from(AgentDemand).where(
        AgentDemand.channel == GROUP_CHANNEL, AgentDemand.requires_approval.is_(False), AgentDemand.created_at >= since))
    if recent >= HOURLY_LIMIT:
        raise HTTPException(429, 'Too many requests from the group in the last hour')
    maia = await db.scalar(select(Agent).where(Agent.profile_slug == 'maia'))
    if maia is None or not settings.MOODLE_APPROVAL_WORKING_PATH:
        raise HTTPException(503, 'Maia is not available')
    demand = AgentDemand(from_agent='maia', from_agent_id=maia.id, target_agent_id=maia.id,
                         subject=f'Grupo CI Instrutor: pedido de {payload.author}'[:255], body='Captura do grupo.',
                         origin_type='task', status='new', fixed_agent=True, channel=GROUP_CHANNEL, channel_ref=group,
                         requires_response=False, working_path=settings.MOODLE_APPROVAL_WORKING_PATH,
                         scheduled_at=datetime.now(timezone.utc))
    db.add(demand)
    await db.flush()
    await db.refresh(demand)
    demand.body = capture_body(demand.number, payload.author, payload.text)
    await db.commit()
    wake_scheduled_dispatch()
    return {'number': demand.number}


"""Register authorized personal demands directly, preserving the verified source."""
import asyncio

from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert

from app.api.schemas.personal import PersonalDemandOrigin, PersonalDemandOut
from app.core import personal_captures as capture
from app.db.models.personal import PersonalCaptureSuggestion, PersonalContact, PersonalContactMessage, PersonalDemand
from app.mcp import personal_group_sources as sources


async def create_direct_demand(db, payload, actor):
    source = payload.origin
    if source.kind == 'group':
        record = await asyncio.to_thread(capture.source_call, sources.observed_message, source.group_whatsapp_id, source.message_ref)
        group = await capture.ensure_group(db, source.group_whatsapp_id, actor)
        origin = PersonalDemandOrigin(kind='group', group_id=group.id, group_name=group.name,
            author=str(record.get('autor') or record.get('autor_id') or '')[:255],
            author_id=str(record.get('autor_id') or '')[:160] or None,
            message_ref=source.message_ref, captured_at=capture.source_time(record.get('ts')))
        key = capture.demand_source_key('group', source.group_whatsapp_id, source.message_ref, source.item_key)
    else:
        contact = (await db.execute(select(PersonalContact).where(PersonalContact.id == source.contact_id).with_for_update())).scalar_one_or_none()
        if contact is None:
            raise HTTPException(404, 'Contato de origem não encontrado')
        message = await db.get(PersonalContactMessage, source.message_id) if source.message_id else None
        if source.message_id and (message is None or message.contact_id != contact.id):
            raise HTTPException(422, 'Mensagem não pertence ao contato de origem')
        origin = PersonalDemandOrigin(kind='contact', contact_id=contact.id, contact_name=contact.name,
            author=(message.author if message else None) or contact.name or '',
            message_id=message.id if message else None, captured_at=message.at if message else None)
        key = capture.demand_source_key('contact', contact.id,
            capture.contact_demand_reference(source.message_id, payload.title, payload.notes), source.item_key)
    # Previously accepted captures already created real demands. Reuse those too.
    identity = PersonalCaptureSuggestion.capture_key == key
    if source.kind == 'contact' and source.message_id and source.item_key == 'principal':
        identity = or_(identity, and_(PersonalCaptureSuggestion.contact_id == source.contact_id,
            PersonalCaptureSuggestion.message_id == source.message_id, PersonalCaptureSuggestion.capture_key.is_(None),
            PersonalCaptureSuggestion.title == payload.title, PersonalCaptureSuggestion.details == (payload.notes or '').strip()))
    previous_id = (await db.execute(select(PersonalCaptureSuggestion.created_item_id).where(
        identity, PersonalCaptureSuggestion.status == 'accepted',
        PersonalCaptureSuggestion.kind == 'demand').order_by(PersonalCaptureSuggestion.created_at).limit(1))).scalar_one_or_none()
    if previous_id:
        previous = await db.get(PersonalDemand, previous_id)
        if previous is not None:
            previous.origin = origin.model_dump(mode='json')
            previous.origin_key = key
            await db.commit()
            await db.refresh(previous)
            return PersonalDemandOut.model_validate(previous)
    values = dict(title=payload.title, notes=payload.notes, type_id=payload.type_id,
                  created_by=actor, origin=origin.model_dump(mode='json'), origin_key=key)
    new_id = (await db.execute(insert(PersonalDemand).values(**values).on_conflict_do_nothing(
        constraint='uq_personal_demand_origin_key').returning(PersonalDemand.id))).scalar_one_or_none()
    demand = (await db.execute(select(PersonalDemand).where(PersonalDemand.origin_key == key))).scalar_one()
    if new_id:
        capture.audit(db, 'personal_demand', demand.id, 'created', actor, {
            'origin_kind': source.kind, 'group_id': str(origin.group_id) if origin.group_id else None,
            'contact_id': str(origin.contact_id) if origin.contact_id else None,
            'message_ref': source.message_ref, 'message_id': str(source.message_id) if source.message_id else None,
            'registration': 'direct'})
    await db.commit()
    await db.refresh(demand)
    return PersonalDemandOut.model_validate(demand)

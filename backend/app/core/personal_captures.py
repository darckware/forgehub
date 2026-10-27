"""Monitored group registry and source-aware personal capture, with append-only audit."""
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.personal_contacts import SuggestionOut
from app.db.models.governance import AuditEvent
from app.db.models.personal import PersonalCaptureSuggestion, PersonalWhatsAppGroup
from app.mcp import personal_group_sources as sources

GROUPS_ROOT = Path('/host-root/root/.hermes/profiles/maia/whatsapp/grupos') if Path('/host-root').is_dir() else Path('/root/.hermes/profiles/maia/whatsapp/grupos')


def source_call(fn, *args):
    try:
        return fn(GROUPS_ROOT, *args)
    except sources.GroupSourceError as exc:
        message = str(exc)
        code = 503 if 'indisponível' in message or 'inválida' in message else 422
        raise HTTPException(code, message) from exc


def source_time(value):
    try:
        return datetime.fromtimestamp(float(value), timezone.utc) if value is not None else None
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def audit(db, entity_type, entity_id, event_type, actor, payload):
    db.add(AuditEvent(entity_type=entity_type, entity_id=entity_id, event_type=event_type, actor=actor, payload=payload))


async def ensure_group(db: AsyncSession, whatsapp_id: str, actor: str):
    source = source_call(sources.monitored_group, whatsapp_id)
    values = dict(whatsapp_id=whatsapp_id, name=source['name'], last_seen_at=source_time(source['last_seen_ts']), created_by=actor)
    created_id = (await db.execute(insert(PersonalWhatsAppGroup).values(**values).on_conflict_do_nothing(index_elements=['whatsapp_id']).returning(PersonalWhatsAppGroup.id))).scalar_one_or_none()
    group = (await db.execute(select(PersonalWhatsAppGroup).where(PersonalWhatsAppGroup.whatsapp_id == whatsapp_id).with_for_update())).scalar_one()
    if created_id:
        audit(db, 'personal_whatsapp_group', group.id, 'registered', actor, {'source': 'monitored_whatsapp_inventory'})
    elif group.name != values['name'] or group.last_seen_at != values['last_seen_at']:
        group.name = values['name']
        group.last_seen_at = values['last_seen_at']
    return group


def suggestion_out(suggestion, contact=None, group=None):
    result = SuggestionOut.model_validate(suggestion)
    if contact:
        result.contact_name, result.contact_phone = contact.name, contact.phone
    if group:
        result.group_name, result.group_whatsapp_id = group.name, group.whatsapp_id
    return result


async def capture_group(db: AsyncSession, payload, actor: str):
    record = source_call(sources.observed_message, payload.whatsapp_id, payload.message_ref)
    group = await ensure_group(db, payload.whatsapp_id, actor)
    capture_key = hashlib.sha256('\x00'.join([payload.whatsapp_id, payload.message_ref, payload.kind, payload.item_key]).encode()).hexdigest()
    values = dict(group_id=group.id, contact_id=None, message_id=None, kind=payload.kind, title=payload.title, details=payload.details,
                  status='pending', capture_key=capture_key, source_message_ref=payload.message_ref,
                  source_author=str(record.get('autor') or '')[:255] or None,
                  source_author_id=str(record.get('autor_id') or '')[:160] or None, source_at=source_time(record.get('ts')))
    new_id = (await db.execute(insert(PersonalCaptureSuggestion).values(**values).on_conflict_do_nothing(index_elements=['capture_key']).returning(PersonalCaptureSuggestion.id))).scalar_one_or_none()
    suggestion = (await db.execute(select(PersonalCaptureSuggestion).where(PersonalCaptureSuggestion.capture_key == capture_key))).scalar_one()
    if suggestion.status == 'pending' and (suggestion.title != payload.title or suggestion.details != payload.details):
        raise HTTPException(409, 'Esta mensagem/item já tem uma sugestão com conteúdo diferente; reutilize o UUID existente ou identifique outro item da mesma mensagem.')
    if new_id:
        audit(db, 'personal_capture_suggestion', suggestion.id, 'captured', actor, {'group_id': str(group.id), 'message_ref': payload.message_ref, 'kind': payload.kind})
    await db.commit()
    await db.refresh(suggestion)
    return suggestion_out(suggestion, group=group)

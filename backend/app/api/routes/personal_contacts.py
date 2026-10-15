"""Personal contacts: the people on Marcelo's personal WhatsApp, their history with the context of each
message, the demands/tasks/notes the Maia proposes from it, and her WhatsApp service rules
(2026-10-14). Same access rule as the rest of the Pessoal domain (``personal_actor``: the admin user or
the Maia); deleting a contact is Marcelo's only.

Writers: the ForgeHub screen (Pessoal → Contatos / Maia), the Maia's ``pessoal`` MCP tools (Telegram),
and her WhatsApp plugin (``/whatsapp/*`` -- record each message, read the context before answering).
Rules carried over from the file-based module are in core/personal_contacts.py.
"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.personal import _owner_only, personal_actor
from app.api.schemas.personal_contacts import (
    AssistantSettingsOut,
    AssistantSettingsUpdate,
    AssistantStateOut,
    CategoryIn,
    ContactOut,
    ContactUpsert,
    ContactUpsertMany,
    MessageIn,
    MessageOut,
    OpenTask,
    PausedChat,
    PhoneIn,
    SuggestionAccept,
    SuggestionOut,
    TextIn,
    WhatsappContextOut,
    WhatsappMessageIn,
)
from app.core import personal_contacts as rules
from app.core.config import settings
from app.db.base import get_db
from app.db.models.personal import (
    PersonalAssistantSettings,
    PersonalCaptureSuggestion,
    PersonalContact,
    PersonalContactCategory,
    PersonalContactMessage,
    PersonalDemand,
    PersonalDemandType,
    PersonalNote,
    PersonalTask,
)

router = APIRouter(prefix="/api/v1/personal", tags=["personal"])

CONTEXT_HISTORY_LINES = 8


def _rule(fn, *args):
    try:
        return fn(*args)
    except rules.ContactRuleError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


async def _categories(db: AsyncSession) -> list[str]:
    keys = list((await db.execute(select(PersonalContactCategory.key).order_by(PersonalContactCategory.created_at))).scalars())
    return keys


async def _find(db: AsyncSession, phone: str) -> PersonalContact | None:
    normalized = rules.normalize_phone(phone)
    if not normalized:
        return None
    return (await db.execute(select(PersonalContact).where(PersonalContact.phone == normalized))).scalars().first()


async def _get_or_404(db: AsyncSession, phone: str) -> PersonalContact:
    contact = await _find(db, phone)
    if contact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Nenhum contato com o telefone {rules.format_phone(phone)}.")
    return contact


async def _out(db: AsyncSession, contact: PersonalContact) -> ContactOut:
    pending = (
        await db.execute(
            select(func.count()).where(
                PersonalCaptureSuggestion.contact_id == contact.id, PersonalCaptureSuggestion.status == "pending"
            )
        )
    ).scalar_one()
    messages = (
        await db.execute(select(func.count()).where(PersonalContactMessage.contact_id == contact.id))
    ).scalar_one()
    out = ContactOut.model_validate(contact)
    out.phone_display = rules.format_phone(contact.phone)
    out.pending_suggestions = pending
    out.message_count = messages
    return out


async def _upsert(db: AsyncSession, phone: str, payload: ContactUpsert, actor: str) -> PersonalContact:
    normalized = _rule(rules.require_phone, phone)
    category = rules.normalize_category(payload.category)
    if category is not None and category not in await _categories(db):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Categoria inválida. Use uma de: {', '.join(await _categories(db))}.",
        )
    birthday = _rule(rules.check_birthday, payload.birthday)
    contact = await _find(db, normalized)
    if contact is None:
        contact = PersonalContact(phone=normalized, created_by=actor, other_data={})
        db.add(contact)
    for field, value in (
        ("name", payload.name),
        ("relation", payload.relation),
        ("observations", payload.observations),
        ("who_is", payload.who_is),
        ("how_to_treat", payload.how_to_treat),
    ):
        if value is not None:
            setattr(contact, field, value.strip())
    if category is not None:
        contact.category = category
    if birthday is not None:
        contact.birthday = birthday
    other_data, blocked_by_marker = rules.split_blacklist_marker(payload.other_data)
    if payload.blocked is not None:
        contact.blocked = payload.blocked
    elif blocked_by_marker is not None:
        contact.blocked = blocked_by_marker
    if other_data:
        contact.other_data = rules.merge_other_data(contact.other_data, other_data)
    return contact


# --- categories -----------------------------------------------------------------------------------

@router.get("/contact-categories", response_model=list[str])
async def list_categories(actor: str = Depends(personal_actor), db: AsyncSession = Depends(get_db)) -> list[str]:
    return await _categories(db)


@router.post("/contact-categories", response_model=list[str])
async def create_category(payload: CategoryIn, actor: str = Depends(personal_actor),
                          db: AsyncSession = Depends(get_db)) -> list[str]:
    key = rules.normalize_category(payload.name)
    if not key or len(key) > 40:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Informe uma categoria com até 40 caracteres.")
    if key not in await _categories(db):
        db.add(PersonalContactCategory(key=key))
        await db.commit()
    return await _categories(db)


# --- contacts -------------------------------------------------------------------------------------

@router.get("/contacts", response_model=list[ContactOut])
async def list_contacts(
    category: str | None = None,
    q: str | None = None,
    actor: str = Depends(personal_actor),
    db: AsyncSession = Depends(get_db),
) -> list[ContactOut]:
    stmt = select(PersonalContact)
    if category:
        stmt = stmt.where(PersonalContact.category == rules.normalize_category(category))
    if q and q.strip():
        like = f"%{q.strip()}%"
        digits = rules.digits(q)
        conditions = [PersonalContact.name.ilike(like), PersonalContact.relation.ilike(like),
                      PersonalContact.observations.ilike(like)]
        if digits:
            conditions.append(PersonalContact.phone.contains(digits))
        stmt = stmt.where(or_(*conditions))
    stmt = stmt.order_by(PersonalContact.last_contact_at.desc().nulls_last(), PersonalContact.name)
    contacts = list((await db.execute(stmt)).scalars())
    pending = dict(
        (
            await db.execute(
                select(PersonalCaptureSuggestion.contact_id, func.count())
                .where(PersonalCaptureSuggestion.status == "pending")
                .group_by(PersonalCaptureSuggestion.contact_id)
            )
        ).all()
    )
    counts = dict(
        (
            await db.execute(
                select(PersonalContactMessage.contact_id, func.count()).group_by(PersonalContactMessage.contact_id)
            )
        ).all()
    )
    result = []
    for c in contacts:
        out = ContactOut.model_validate(c)
        out.phone_display = rules.format_phone(c.phone)
        out.pending_suggestions = pending.get(c.id, 0)
        out.message_count = counts.get(c.id, 0)
        result.append(out)
    return result


@router.get("/contacts/{phone}", response_model=ContactOut)
async def get_contact(phone: str, actor: str = Depends(personal_actor), db: AsyncSession = Depends(get_db)) -> ContactOut:
    return await _out(db, await _get_or_404(db, phone))


@router.put("/contacts/{phone}", response_model=ContactOut)
async def upsert_contact(phone: str, payload: ContactUpsert, actor: str = Depends(personal_actor),
                         db: AsyncSession = Depends(get_db)) -> ContactOut:
    contact = await _upsert(db, phone, payload, actor)
    await db.commit()
    await db.refresh(contact)
    return await _out(db, contact)


@router.post("/contacts:upsert-many")
async def upsert_many(payload: ContactUpsertMany, actor: str = Depends(personal_actor),
                      db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Each contact on its own: one bad item never blocks the others."""
    saved, errors = [], []
    for item in payload.contacts:
        try:
            contact = await _upsert(db, item.phone, item, actor)
            await db.commit()
            saved.append({"phone": contact.phone, "name": contact.name, "category": contact.category})
        except HTTPException as exc:
            await db.rollback()
            errors.append({"phone": item.phone, "error": str(exc.detail)})
    return {"saved": saved, "errors": errors}


@router.post("/contacts/{phone}:append-observation", response_model=ContactOut)
async def append_observation(phone: str, payload: TextIn, actor: str = Depends(personal_actor),
                             db: AsyncSession = Depends(get_db)) -> ContactOut:
    contact = await _get_or_404(db, phone)
    text = payload.text.strip().replace("\n", " ")
    contact.observations = f"{contact.observations.strip()}; {text}" if contact.observations.strip() else text
    await db.commit()
    await db.refresh(contact)
    return await _out(db, contact)


@router.post("/contacts/{phone}:change-phone", response_model=ContactOut)
async def change_phone(phone: str, payload: PhoneIn, actor: str = Depends(personal_actor),
                       db: AsyncSession = Depends(get_db)) -> ContactOut:
    """Moves the contact (record and history) to a new number."""
    contact = await _get_or_404(db, phone)
    new = _rule(rules.require_phone, payload.phone)
    if new != contact.phone:
        if await _find(db, new) is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "O novo telefone já pertence a outro contato.")
        contact.phone = new
        await db.commit()
        await db.refresh(contact)
    return await _out(db, contact)


@router.delete("/contacts/{phone}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(phone: str, actor: str = Depends(personal_actor), db: AsyncSession = Depends(get_db)) -> None:
    """Marcelo only; takes the contact's history and suggestions with it."""
    _owner_only(actor)
    await db.delete(await _get_or_404(db, phone))
    await db.commit()


@router.get("/birthdays")
async def birthdays(days: int = Query(30, ge=0, le=366), actor: str = Depends(personal_actor),
                    db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
    today = datetime.now(rules.TZ).date()
    result = []
    for c in (await db.execute(select(PersonalContact).where(PersonalContact.birthday != ""))).scalars():
        upcoming = rules.upcoming_birthday(c.birthday, today, days)
        if upcoming:
            result.append({"nome": c.name, "telefone": rules.format_phone(c.phone), "relacao": c.relation, **upcoming})
    return sorted(result, key=lambda b: b["faltam_dias"])


# --- history --------------------------------------------------------------------------------------

@router.get("/contacts/{phone}/messages", response_model=list[MessageOut])
async def list_messages(
    phone: str,
    limit: int = Query(50, ge=1, le=500),
    before: datetime | None = None,
    actor: str = Depends(personal_actor),
    db: AsyncSession = Depends(get_db),
) -> list[PersonalContactMessage]:
    """Newest first; page back with ``before``."""
    contact = await _get_or_404(db, phone)
    stmt = select(PersonalContactMessage).where(PersonalContactMessage.contact_id == contact.id)
    if before is not None:
        stmt = stmt.where(PersonalContactMessage.at < before)
    stmt = stmt.order_by(PersonalContactMessage.at.desc()).limit(limit)
    return list((await db.execute(stmt)).scalars())


def _record(contact: PersonalContact, *, text: str, direction: str, author: str, source: str,
            at: datetime | None) -> PersonalContactMessage:
    when = at or datetime.now(timezone.utc)
    message = PersonalContactMessage(
        contact_id=contact.id,
        at=when,
        direction=direction,
        author=author.strip()[:100],
        text=text.strip(),
        source=source,
        # Only what a contact wrote gets a context reading; the rest needs none.
        context_status="pending" if direction == "in" else "skipped",
    )
    if direction in ("in", "out") and (contact.last_contact_at is None or when > contact.last_contact_at):
        contact.last_contact_at = when
    return message


@router.post("/contacts/{phone}/messages", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
async def add_message(phone: str, payload: MessageIn, actor: str = Depends(personal_actor),
                      db: AsyncSession = Depends(get_db)) -> PersonalContactMessage:
    """A history line added by Marcelo (screen) or by the Maia on his behalf (Telegram)."""
    contact = await _get_or_404(db, phone)
    message = _record(contact, text=payload.text, direction=payload.direction, author=payload.author,
                      source=payload.source, at=payload.at)
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


@router.post("/messages/{message_id}:reprocess", response_model=MessageOut)
async def reprocess_message(message_id: uuid.UUID, actor: str = Depends(personal_actor),
                            db: AsyncSession = Depends(get_db)) -> PersonalContactMessage:
    """Send a message back to the context pass (after a failure, or to read it again)."""
    message = await db.get(PersonalContactMessage, message_id)
    if message is None or message.direction != "in":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mensagem não encontrada")
    message.context_status = "pending"
    await db.commit()
    await db.refresh(message)
    return message


# --- the WhatsApp plugin --------------------------------------------------------------------------

async def _settings_row(db: AsyncSession) -> PersonalAssistantSettings:
    row = (await db.execute(select(PersonalAssistantSettings).limit(1))).scalars().first()
    if row is None:
        row = PersonalAssistantSettings()
        db.add(row)
        await db.flush()
    return row


def context_text(contact: PersonalContact, history: list[PersonalContactMessage]) -> str:
    """Who is writing, how to treat them and the recent conversation, as the plugin injects it before
    the Maia answers -- same content the old ficha-based ``contatos.contexto`` produced."""
    parts = []
    ident = " · ".join(x for x in (contact.name, contact.category, contact.relation,
                                   f"aniversário {contact.birthday}" if contact.birthday else "") if x)
    if ident:
        parts.append(f"Quem escreve: {ident}.")
    if contact.who_is:
        parts.append(f"Quem é: {contact.who_is[:1500]}")
    if contact.how_to_treat:
        parts.append(f"Como tratar (orientação do Marcelo): {contact.how_to_treat[:1500]}")
    if contact.other_data:
        extras = "; ".join(f"{k}: {v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)}"
                           for k, v in contact.other_data.items())
        parts.append(f"Outros dados: {extras[:1000]}")
    if history:
        lines = [f"- {m.at.astimezone(rules.TZ):%d/%m/%Y %H:%M} · {m.author or m.direction}: {m.text[:500]}"
                 + (f" [contexto: {m.context}]" if m.context else "") for m in history]
        parts.append("Conversas recentes:\n" + "\n".join(lines))
    return "\n".join(parts)


@router.get("/whatsapp/context/{phone}", response_model=WhatsappContextOut)
async def whatsapp_context(phone: str, actor: str = Depends(personal_actor),
                           db: AsyncSession = Depends(get_db)) -> WhatsappContextOut:
    cfg = await _settings_row(db)
    await db.commit()
    contact = await _find(db, phone)
    if contact is None:
        return WhatsappContextOut(contact=None, blocked=False, context_text="",
                                  instructions=cfg.instructions, wait_minutes=cfg.wait_minutes)
    history = list(
        (
            await db.execute(
                select(PersonalContactMessage)
                .where(PersonalContactMessage.contact_id == contact.id, PersonalContactMessage.direction != "note")
                .order_by(PersonalContactMessage.at.desc())
                .limit(CONTEXT_HISTORY_LINES)
            )
        ).scalars()
    )[::-1]
    return WhatsappContextOut(contact=await _out(db, contact), blocked=contact.blocked,
                              context_text=context_text(contact, history),
                              instructions=cfg.instructions, wait_minutes=cfg.wait_minutes)


@router.post("/whatsapp/messages", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
async def whatsapp_message(payload: WhatsappMessageIn, actor: str = Depends(personal_actor),
                           db: AsyncSession = Depends(get_db)) -> PersonalContactMessage:
    """One WhatsApp message as the plugin saw it. An unknown number becomes a contact to classify,
    exactly as the plugin did with the old files."""
    phone = _rule(rules.require_phone, payload.phone)
    contact = await _find(db, phone)
    if contact is None:
        contact = PersonalContact(phone=phone, category="a_classificar", created_by=actor, other_data={})
        db.add(contact)
        await db.flush()
    default_author = "Marcelo" if payload.direction == "out" else (contact.name or "contato")
    message = _record(contact, text=payload.text, direction=payload.direction,
                      author=payload.author or default_author, source="whatsapp", at=payload.at)
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


# --- capture suggestions --------------------------------------------------------------------------

@router.get("/suggestions", response_model=list[SuggestionOut])
async def list_suggestions(
    suggestion_status: str | None = Query("pending", alias="status"),
    contact_phone: str | None = None,
    actor: str = Depends(personal_actor),
    db: AsyncSession = Depends(get_db),
) -> list[SuggestionOut]:
    stmt = select(PersonalCaptureSuggestion, PersonalContact).join(
        PersonalContact, PersonalContact.id == PersonalCaptureSuggestion.contact_id
    )
    if suggestion_status:
        stmt = stmt.where(PersonalCaptureSuggestion.status == suggestion_status)
    if contact_phone:
        stmt = stmt.where(PersonalContact.phone == rules.normalize_phone(contact_phone))
    stmt = stmt.order_by(PersonalCaptureSuggestion.created_at.desc()).limit(200)
    result = []
    for suggestion, contact in (await db.execute(stmt)).all():
        out = SuggestionOut.model_validate(suggestion)
        out.contact_name = contact.name
        out.contact_phone = contact.phone
        result.append(out)
    return result


async def _pending_suggestion(db: AsyncSession, suggestion_id: uuid.UUID) -> PersonalCaptureSuggestion:
    suggestion = await db.get(PersonalCaptureSuggestion, suggestion_id)
    if suggestion is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sugestão não encontrada")
    if suggestion.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, "Esta sugestão já foi decidida")
    return suggestion


@router.post("/suggestions/{suggestion_id}:accept", response_model=SuggestionOut)
async def accept_suggestion(suggestion_id: uuid.UUID, payload: SuggestionAccept, actor: str = Depends(personal_actor),
                            db: AsyncSession = Depends(get_db)) -> SuggestionOut:
    """Turns the suggestion into a real demand, task or note, with where it came from."""
    suggestion = await _pending_suggestion(db, suggestion_id)
    contact = await db.get(PersonalContact, suggestion.contact_id)
    kind = payload.kind or suggestion.kind
    title = (payload.title or suggestion.title).strip()
    details = (payload.details if payload.details is not None else suggestion.details).strip()
    origin = f"Capturado do WhatsApp — {contact.name or 'contato'} ({rules.format_phone(contact.phone)})"
    body = f"{details}\n\n{origin}" if details else origin
    item: PersonalDemand | PersonalTask | PersonalNote
    if kind == "demand":
        if payload.type_id is not None and await db.get(PersonalDemandType, payload.type_id) is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown demand type")
        item = PersonalDemand(title=title, notes=body, type_id=payload.type_id, created_by=actor)
    elif kind == "task":
        item = PersonalTask(title=title, notes=body, list_name="Pessoal", reminders=[], created_by=actor)
    else:
        item = PersonalNote(title=title, content=body, tags=["whatsapp"], created_by=actor)
    db.add(item)
    await db.flush()
    suggestion.kind = kind
    suggestion.title = title
    suggestion.details = details
    suggestion.status = "accepted"
    suggestion.created_item_id = item.id
    suggestion.decided_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(suggestion)
    out = SuggestionOut.model_validate(suggestion)
    out.contact_name, out.contact_phone = contact.name, contact.phone
    return out


@router.post("/suggestions/{suggestion_id}:dismiss", response_model=SuggestionOut)
async def dismiss_suggestion(suggestion_id: uuid.UUID, actor: str = Depends(personal_actor),
                             db: AsyncSession = Depends(get_db)) -> SuggestionOut:
    suggestion = await _pending_suggestion(db, suggestion_id)
    suggestion.status = "dismissed"
    suggestion.decided_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(suggestion)
    return SuggestionOut.model_validate(suggestion)


# --- the Maia's service rules ---------------------------------------------------------------------

@router.get("/assistant-settings", response_model=AssistantSettingsOut)
async def get_assistant_settings(actor: str = Depends(personal_actor),
                                 db: AsyncSession = Depends(get_db)) -> PersonalAssistantSettings:
    row = await _settings_row(db)
    await db.commit()
    return row


@router.put("/assistant-settings", response_model=AssistantSettingsOut)
async def update_assistant_settings(payload: AssistantSettingsUpdate, actor: str = Depends(personal_actor),
                                    db: AsyncSession = Depends(get_db)) -> PersonalAssistantSettings:
    row = await _settings_row(db)
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(row, key, value)
    await db.commit()
    await db.refresh(row)
    return row


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


@router.get("/assistant-state", response_model=AssistantStateOut)
async def assistant_state(actor: str = Depends(personal_actor), db: AsyncSession = Depends(get_db)) -> AssistantStateOut:
    """What the WhatsApp plugin is doing right now (its own runtime files, read-only here) plus the
    capture queue's numbers."""
    state_dir = Path(settings.PERSONAL_WHATSAPP_STATE_DIR)
    now = datetime.now(timezone.utc).timestamp()
    names = {c.phone: c.name for c in (await db.execute(select(PersonalContact))).scalars()}

    paused = []
    for chat, until in _read_json(state_dir / "pausas.json").items():
        phone = rules.normalize_phone(chat.split("@")[0])
        try:
            until_ts = float(until)
        except (TypeError, ValueError):
            continue
        if until_ts > now:
            paused.append(PausedChat(phone=phone, name=names.get(phone, ""),
                                     until=datetime.fromtimestamp(until_ts, timezone.utc)))
    tasks = []
    for phone_raw, task in _read_json(state_dir / "tarefas.json").items():
        if not isinstance(task, dict):
            continue
        expires = task.get("expira_ts")
        if expires is not None and float(expires) <= now:
            continue
        phone = rules.normalize_phone(phone_raw)
        tasks.append(OpenTask(
            phone=phone, name=names.get(phone, ""), goal=str(task.get("objetivo", "")),
            created=str(task.get("criada", "")),
            expires_at=datetime.fromtimestamp(float(expires), timezone.utc) if expires is not None else None,
        ))

    async def count(*conditions) -> int:
        return (await db.execute(select(func.count()).where(*conditions))).scalar_one()

    return AssistantStateOut(
        paused=sorted(paused, key=lambda p: p.until),
        open_tasks=tasks,
        context_pending=await count(PersonalContactMessage.context_status == "pending"),
        context_failed=await count(PersonalContactMessage.context_status == "failed"),
        suggestions_pending=await count(PersonalCaptureSuggestion.status == "pending"),
        contacts=await count(PersonalContact.id.isnot(None)),
        blocked=await count(PersonalContact.blocked.is_(True)),
    )

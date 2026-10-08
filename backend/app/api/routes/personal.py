"""Personal domain routes: Marcelo's tasks, agenda and notes (2026-10-07).

Access: the admin user (the ForgeHub UI) and the agents in ``settings.PERSONAL_AGENT_SLUGS``
(default ``maia``, his personal assistant, with her own ``agt_`` credential). Every other user or
agent gets 403 -- this is one person's private data, not software-factory work. Deleting is
admin-only: Maia cancels or archives, she never deletes (same rule as her contacts and history).

``POST /reminders:due`` is what Maia's cron calls every minute: it returns the reminder lines that
came due and marks them sent, so each one fires exactly once. ``GET /summary`` feeds her morning
summary.
"""
import uuid
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.personal import (
    AgendaItemOut,
    DaySummaryOut,
    PersonalEventCreate,
    PersonalEventOut,
    PersonalEventUpdate,
    PersonalNoteCreate,
    PersonalNoteOut,
    PersonalNoteUpdate,
    PersonalTaskCreate,
    PersonalTaskOut,
    PersonalTaskUpdate,
    RemindersDueOut,
)
from app.core.config import settings
from app.core.deps import ActorPrincipal, get_actor_principal
from app.core.personal_schedule import (
    DEFAULT_REMINDERS,
    collect_due,
    day_summary,
    next_occurrence,
    now_local,
    task_moment,
)
from app.db.base import get_db
from app.db.models.personal import PersonalEvent, PersonalNote, PersonalTask

router = APIRouter(prefix="/api/v1/personal", tags=["personal"])

OWNER = "marcelo"


async def personal_actor(
    principal: ActorPrincipal = Depends(get_actor_principal), db: AsyncSession = Depends(get_db)
) -> str:
    """"marcelo" for the admin user, the agent's profile_slug for an allowed agent; else 403."""
    if principal.principal_type == "user":
        if principal.is_admin:
            return OWNER
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Personal data is restricted to its owner")
    from app.db.models.agent import Agent

    agent = await db.get(Agent, principal.principal_id)
    allowed = {s.strip().lower() for s in settings.PERSONAL_AGENT_SLUGS.split(",") if s.strip()}
    slug = (agent.profile_slug or "").strip().lower() if agent else ""
    if slug and slug in allowed:
        return slug
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Personal data is restricted to its owner")


def _owner_only(actor: str) -> None:
    if actor != OWNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only Marcelo can delete; cancel or archive instead")


async def _get(db: AsyncSession, model, item_id: uuid.UUID):
    row = await db.get(model, item_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} not found")
    return row


# --- tasks -------------------------------------------------------------------------------------

@router.get("/tasks", response_model=list[PersonalTaskOut])
async def list_tasks(
    task_status: str | None = Query(default="pending", alias="status"),
    list_name: str | None = None,
    q: str | None = None,
    actor: str = Depends(personal_actor),
    db: AsyncSession = Depends(get_db),
) -> list[PersonalTask]:
    stmt = select(PersonalTask)
    if task_status:
        stmt = stmt.where(PersonalTask.status == task_status)
    if list_name:
        stmt = stmt.where(PersonalTask.list_name == list_name)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(PersonalTask.title.ilike(like), PersonalTask.notes.ilike(like)))
    stmt = stmt.order_by(PersonalTask.due_at.is_(None), PersonalTask.due_at, PersonalTask.created_at)
    return list((await db.execute(stmt)).scalars())


@router.post("/tasks", response_model=PersonalTaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(payload: PersonalTaskCreate, actor: str = Depends(personal_actor),
                      db: AsyncSession = Depends(get_db)) -> PersonalTask:
    data = payload.model_dump(exclude_none=True)
    if data.get("reminders") is None:
        data["reminders"] = DEFAULT_REMINDERS["task"] if payload.due_at else []
    if payload.due_at is not None and payload.due_has_time is None:
        data["due_has_time"] = bool(payload.due_at.hour or payload.due_at.minute)
    task = PersonalTask(**data, created_by=actor)
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


@router.patch("/tasks/{task_id}", response_model=PersonalTaskOut)
async def update_task(task_id: uuid.UUID, payload: PersonalTaskUpdate, actor: str = Depends(personal_actor),
                      db: AsyncSession = Depends(get_db)) -> PersonalTask:
    task = await _get(db, PersonalTask, task_id)
    data = payload.model_dump(exclude_unset=True)
    new_status = data.pop("status", None)
    for key, value in data.items():
        setattr(task, key, value)
    if {"due_at", "due_has_time", "reminders"} & data.keys():
        task.reminders_sent = []
    if new_status == "done":
        _complete(task)
    elif new_status:
        task.status = new_status
        task.completed_at = None
    await db.commit()
    await db.refresh(task)
    return task


def _complete(task: PersonalTask) -> None:
    """Done. A recurring task with a due date rolls to its next occurrence and stays pending."""
    moment = task_moment(task)
    if task.recurrence and moment is not None:
        nxt = next_occurrence(moment, task.recurrence)
        task.due_at = nxt if task.due_has_time else nxt.replace(hour=0, minute=0)
        task.reminders_sent = []
        task.status = "pending"
        task.completed_at = None
    else:
        task.status = "done"
        task.completed_at = datetime.now().astimezone()


@router.post("/tasks/{task_id}:complete", response_model=PersonalTaskOut)
async def complete_task(task_id: uuid.UUID, actor: str = Depends(personal_actor),
                        db: AsyncSession = Depends(get_db)) -> PersonalTask:
    task = await _get(db, PersonalTask, task_id)
    _complete(task)
    await db.commit()
    await db.refresh(task)
    return task


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: uuid.UUID, actor: str = Depends(personal_actor),
                      db: AsyncSession = Depends(get_db)) -> None:
    _owner_only(actor)
    await db.delete(await _get(db, PersonalTask, task_id))
    await db.commit()


# --- events (agenda) ---------------------------------------------------------------------------

@router.get("/events", response_model=list[PersonalEventOut])
async def list_events(
    start: datetime | None = None,
    end: datetime | None = None,
    include_cancelled: bool = False,
    actor: str = Depends(personal_actor),
    db: AsyncSession = Depends(get_db),
) -> list[PersonalEvent]:
    stmt = select(PersonalEvent)
    if not include_cancelled:
        stmt = stmt.where(PersonalEvent.status == "scheduled")
    if start:
        stmt = stmt.where(PersonalEvent.starts_at >= start.replace(tzinfo=None))
    if end:
        stmt = stmt.where(PersonalEvent.starts_at < end.replace(tzinfo=None))
    return list((await db.execute(stmt.order_by(PersonalEvent.starts_at))).scalars())


@router.post("/events", response_model=PersonalEventOut, status_code=status.HTTP_201_CREATED)
async def create_event(payload: PersonalEventCreate, actor: str = Depends(personal_actor),
                       db: AsyncSession = Depends(get_db)) -> PersonalEvent:
    data = payload.model_dump(exclude_none=True)
    if data.get("reminders") is None:
        data["reminders"] = DEFAULT_REMINDERS["event"]
    if data.get("ends_at") and data["ends_at"] < data["starts_at"]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "ends_at must not be before starts_at")
    event = PersonalEvent(**data, created_by=actor)
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


@router.patch("/events/{event_id}", response_model=PersonalEventOut)
async def update_event(event_id: uuid.UUID, payload: PersonalEventUpdate, actor: str = Depends(personal_actor),
                       db: AsyncSession = Depends(get_db)) -> PersonalEvent:
    event = await _get(db, PersonalEvent, event_id)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(event, key, value)
    if event.ends_at and event.ends_at < event.starts_at:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "ends_at must not be before starts_at")
    if {"starts_at", "reminders"} & data.keys():
        event.reminders_sent = []
    await db.commit()
    await db.refresh(event)
    return event


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(event_id: uuid.UUID, actor: str = Depends(personal_actor),
                       db: AsyncSession = Depends(get_db)) -> None:
    _owner_only(actor)
    await db.delete(await _get(db, PersonalEvent, event_id))
    await db.commit()


# --- notes -------------------------------------------------------------------------------------

@router.get("/notes", response_model=list[PersonalNoteOut])
async def list_notes(
    q: str | None = None,
    tag: str | None = None,
    archived: bool = False,
    actor: str = Depends(personal_actor),
    db: AsyncSession = Depends(get_db),
) -> list[PersonalNote]:
    stmt = select(PersonalNote).where(PersonalNote.archived.is_(archived))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(PersonalNote.title.ilike(like), PersonalNote.content.ilike(like)))
    if tag:
        stmt = stmt.where(PersonalNote.tags.contains([tag]))
    stmt = stmt.order_by(PersonalNote.pinned.desc(), PersonalNote.updated_at.desc())
    return list((await db.execute(stmt)).scalars())


@router.post("/notes", response_model=PersonalNoteOut, status_code=status.HTTP_201_CREATED)
async def create_note(payload: PersonalNoteCreate, actor: str = Depends(personal_actor),
                      db: AsyncSession = Depends(get_db)) -> PersonalNote:
    note = PersonalNote(**payload.model_dump(), created_by=actor)
    note.tags = sorted({t.strip() for t in note.tags if t.strip()})
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return note


@router.get("/notes/{note_id}", response_model=PersonalNoteOut)
async def get_note(note_id: uuid.UUID, actor: str = Depends(personal_actor),
                   db: AsyncSession = Depends(get_db)) -> PersonalNote:
    return await _get(db, PersonalNote, note_id)


@router.patch("/notes/{note_id}", response_model=PersonalNoteOut)
async def update_note(note_id: uuid.UUID, payload: PersonalNoteUpdate, actor: str = Depends(personal_actor),
                      db: AsyncSession = Depends(get_db)) -> PersonalNote:
    note = await _get(db, PersonalNote, note_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        if key == "tags" and value is not None:
            value = sorted({t.strip() for t in value if t.strip()})
        setattr(note, key, value)
    await db.commit()
    await db.refresh(note)
    return note


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(note_id: uuid.UUID, actor: str = Depends(personal_actor),
                      db: AsyncSession = Depends(get_db)) -> None:
    _owner_only(actor)
    await db.delete(await _get(db, PersonalNote, note_id))
    await db.commit()


# --- combined agenda, reminders, summary -------------------------------------------------------

@router.get("/agenda", response_model=list[AgendaItemOut])
async def agenda(
    start: datetime | None = None,
    end: datetime | None = None,
    actor: str = Depends(personal_actor),
    db: AsyncSession = Depends(get_db),
) -> list[AgendaItemOut]:
    """Events and dated tasks between start and end (default: today and the next 7 days), plus
    every overdue pending task."""
    now = now_local()
    start = (start.replace(tzinfo=None) if start else now.replace(hour=0, minute=0))
    end = (end.replace(tzinfo=None) if end else start + timedelta(days=8))
    events = (await db.execute(select(PersonalEvent).where(and_(
        PersonalEvent.status == "scheduled", PersonalEvent.starts_at >= start, PersonalEvent.starts_at < end,
    )))).scalars()
    tasks = (await db.execute(select(PersonalTask).where(and_(
        PersonalTask.status == "pending", PersonalTask.due_at.is_not(None), PersonalTask.due_at < end,
    )))).scalars()
    items = [AgendaItemOut(kind="event", id=e.id, title=e.title, starts_at=e.starts_at, ends_at=e.ends_at,
                           has_time=not e.all_day, location=e.location, status=e.status) for e in events]
    for t in tasks:
        moment = task_moment(t)
        overdue = moment < now
        if moment < start and not overdue:
            continue
        items.append(AgendaItemOut(kind="task", id=t.id, title=t.title, starts_at=moment, has_time=t.due_has_time,
                                   status=t.status, list_name=t.list_name, overdue=overdue))
    return sorted(items, key=lambda i: i.starts_at)


@router.post("/reminders:due", response_model=RemindersDueOut)
async def reminders_due(actor: str = Depends(personal_actor), db: AsyncSession = Depends(get_db)) -> RemindersDueOut:
    """Reminder lines that came due (marks them sent; recurring items roll forward)."""
    now = now_local()
    horizon = now + timedelta(days=8)  # longest reminder is 7 days before
    events = list((await db.execute(select(PersonalEvent).where(and_(
        PersonalEvent.status == "scheduled", PersonalEvent.starts_at < horizon,
        PersonalEvent.starts_at > now - timedelta(days=400),
    )))).scalars())
    tasks = list((await db.execute(select(PersonalTask).where(and_(
        PersonalTask.status == "pending", PersonalTask.due_at.is_not(None), PersonalTask.due_at < horizon,
    )))).scalars())
    lines = collect_due([("event", e) for e in events] + [("task", t) for t in tasks], now)
    await db.commit()
    return RemindersDueOut(lines=lines)


@router.get("/summary", response_model=DaySummaryOut)
async def summary(day: date | None = None, actor: str = Depends(personal_actor),
                  db: AsyncSession = Depends(get_db)) -> DaySummaryOut:
    day = day or now_local().date()
    start = datetime.combine(day, datetime.min.time())
    events = list((await db.execute(select(PersonalEvent).where(and_(
        PersonalEvent.status == "scheduled", PersonalEvent.starts_at >= start,
        PersonalEvent.starts_at < start + timedelta(days=4),
    )))).scalars())
    tasks = list((await db.execute(select(PersonalTask).where(and_(
        PersonalTask.status == "pending", PersonalTask.due_at.is_not(None),
        PersonalTask.due_at < start + timedelta(days=4),
    )))).scalars())
    return DaySummaryOut(day=day.isoformat(), text=day_summary(day, events, tasks))

"""Schemas of the personal domain (Marcelo's tasks, agenda and notes -- see db/models/personal.py).

Datetimes are naive America/Sao_Paulo wall time ("2026-10-08T15:00"), the same convention the
model uses; a timezone-aware value is converted to São Paulo time and stripped.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.personal_schedule import TZ
from app.db.models.personal import (
    PERSONAL_EVENT_STATUSES,
    PERSONAL_RECURRENCES,
    PERSONAL_TASK_PRIORITIES,
    PERSONAL_TASK_STATUSES,
)


def _local(v: datetime | None) -> datetime | None:
    if v is None or v.tzinfo is None:
        return v
    return v.astimezone(TZ).replace(tzinfo=None)


def _choice(v: str | None, allowed: tuple[str, ...], field: str) -> str | None:
    if v is not None and v not in allowed:
        raise ValueError(f"{field} must be one of {allowed}")
    return v


def _reminders(v: list[int] | None) -> list[int] | None:
    if v is None:
        return v
    if any(not isinstance(x, int) or x < 0 or x > 10080 for x in v):
        raise ValueError("reminders are minutes before, between 0 and 10080 (7 days)")
    return sorted(set(v), reverse=True)


class _TaskFields(BaseModel):
    notes: str | None = None
    list_name: str | None = Field(default=None, max_length=80)
    priority: str | None = None
    due_at: datetime | None = None
    due_has_time: bool | None = None
    recurrence: str | None = None
    reminders: list[int] | None = None

    _due = field_validator("due_at")(classmethod(lambda cls, v: _local(v)))
    _prio = field_validator("priority")(classmethod(lambda cls, v: _choice(v, PERSONAL_TASK_PRIORITIES, "priority")))
    _rec = field_validator("recurrence")(classmethod(lambda cls, v: _choice(v, PERSONAL_RECURRENCES, "recurrence")))
    _rem = field_validator("reminders")(classmethod(lambda cls, v: _reminders(v)))


class PersonalTaskCreate(_TaskFields):
    title: str = Field(min_length=1, max_length=300)


class PersonalTaskUpdate(_TaskFields):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    status: str | None = None

    _status = field_validator("status")(classmethod(lambda cls, v: _choice(v, PERSONAL_TASK_STATUSES, "status")))


class PersonalTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    notes: str | None
    list_name: str
    priority: str
    status: str
    due_at: datetime | None
    due_has_time: bool
    recurrence: str
    reminders: list[int]
    completed_at: datetime | None
    created_by: str
    created_at: datetime
    updated_at: datetime


class _EventFields(BaseModel):
    ends_at: datetime | None = None
    all_day: bool | None = None
    location: str | None = Field(default=None, max_length=300)
    notes: str | None = None
    recurrence: str | None = None
    reminders: list[int] | None = None

    _ends = field_validator("ends_at")(classmethod(lambda cls, v: _local(v)))
    _rec = field_validator("recurrence")(classmethod(lambda cls, v: _choice(v, PERSONAL_RECURRENCES, "recurrence")))
    _rem = field_validator("reminders")(classmethod(lambda cls, v: _reminders(v)))


class PersonalEventCreate(_EventFields):
    title: str = Field(min_length=1, max_length=300)
    starts_at: datetime

    _starts = field_validator("starts_at")(classmethod(lambda cls, v: _local(v)))


class PersonalEventUpdate(_EventFields):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    starts_at: datetime | None = None
    status: str | None = None

    _starts = field_validator("starts_at")(classmethod(lambda cls, v: _local(v)))
    _status = field_validator("status")(classmethod(lambda cls, v: _choice(v, PERSONAL_EVENT_STATUSES, "status")))


class PersonalEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    starts_at: datetime
    ends_at: datetime | None
    all_day: bool
    location: str | None
    notes: str | None
    status: str
    recurrence: str
    reminders: list[int]
    created_by: str
    created_at: datetime
    updated_at: datetime


class PersonalNoteCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = ""
    tags: list[str] = Field(default_factory=list)
    pinned: bool = False


class PersonalNoteUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    content: str | None = None
    tags: list[str] | None = None
    pinned: bool | None = None
    archived: bool | None = None


class PersonalNoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    content: str
    tags: list[str]
    pinned: bool
    archived: bool
    created_by: str
    created_at: datetime
    updated_at: datetime


class AgendaItemOut(BaseModel):
    """One row of the combined agenda view: an event, or a task with a due date."""

    kind: str  # "event" | "task"
    id: uuid.UUID
    title: str
    starts_at: datetime
    ends_at: datetime | None = None
    has_time: bool
    location: str | None = None
    status: str
    list_name: str | None = None
    overdue: bool = False


class RemindersDueOut(BaseModel):
    lines: list[str]


class DaySummaryOut(BaseModel):
    day: str
    text: str

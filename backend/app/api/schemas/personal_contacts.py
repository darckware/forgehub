"""Schemas of the personal contacts domain (the Maia's WhatsApp contacts, history, context and
capture suggestions -- see app/db/models/personal.py and api/routes/personal_contacts.py)."""
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ContactUpsert(BaseModel):
    """Every field optional: what's left out is kept (same contract as the Maia's old upsert).
    ``other_data`` merges key by key, an empty value removes the key."""

    name: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, max_length=60)
    relation: str | None = Field(default=None, max_length=200)
    birthday: str | None = Field(default=None, max_length=10)
    observations: str | None = None
    who_is: str | None = None
    how_to_treat: str | None = None
    other_data: dict[str, Any] | None = None
    blocked: bool | None = None


class ContactUpsertItem(ContactUpsert):
    phone: str


class ContactUpsertMany(BaseModel):
    contacts: list[ContactUpsertItem] = Field(min_length=1, max_length=100)


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    phone: str
    phone_display: str = ""
    name: str
    category: str
    relation: str
    birthday: str
    observations: str
    who_is: str
    how_to_treat: str
    other_data: dict[str, Any]
    blocked: bool
    last_contact_at: datetime | None
    created_by: str
    created_at: datetime
    updated_at: datetime
    pending_suggestions: int = 0
    message_count: int = 0


class TextIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class PhoneIn(BaseModel):
    phone: str = Field(min_length=8, max_length=30)


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    direction: Literal["in", "out", "note"] = "note"
    author: str = Field(default="Marcelo", max_length=100)
    source: Literal["whatsapp", "telegram", "manual"] = "manual"
    at: datetime | None = None


class WhatsappMessageIn(BaseModel):
    """What the Maia's WhatsApp plugin records for each message (it creates the contact if new)."""

    phone: str = Field(min_length=8, max_length=30)
    text: str = Field(min_length=1, max_length=8000)
    direction: Literal["in", "out"] = "in"
    author: str = Field(default="", max_length=100)
    at: datetime | None = None


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    contact_id: uuid.UUID
    at: datetime
    direction: str
    author: str
    text: str
    source: str
    context: str | None
    context_status: str


class SuggestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    contact_id: uuid.UUID
    message_id: uuid.UUID | None
    kind: str
    title: str
    details: str
    status: str
    created_item_id: uuid.UUID | None
    decided_at: datetime | None
    created_at: datetime
    contact_name: str = ""
    contact_phone: str = ""


class SuggestionAccept(BaseModel):
    """Marcelo may correct the suggestion while accepting it."""

    kind: Literal["demand", "task", "note"] | None = None
    title: str | None = Field(default=None, min_length=1, max_length=300)
    details: str | None = None
    #: Demand only: its type (tag).
    type_id: uuid.UUID | None = None


class AssistantSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    instructions: str
    wait_minutes: int
    capture_enabled: bool
    updated_at: datetime


class AssistantSettingsUpdate(BaseModel):
    instructions: str | None = Field(default=None, max_length=6000)
    wait_minutes: int | None = Field(default=None, ge=0, le=240)
    capture_enabled: bool | None = None

    @field_validator("instructions")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        return v.strip() if v is not None else v


class PausedChat(BaseModel):
    phone: str
    name: str
    until: datetime


class OpenTask(BaseModel):
    phone: str
    name: str
    goal: str
    created: str
    expires_at: datetime | None


class AssistantStateOut(BaseModel):
    paused: list[PausedChat]
    open_tasks: list[OpenTask]
    context_pending: int
    context_failed: int
    suggestions_pending: int
    contacts: int
    blocked: int


class WhatsappContextOut(BaseModel):
    """What the plugin needs before answering a message."""

    contact: ContactOut | None
    blocked: bool
    context_text: str
    instructions: str
    wait_minutes: int

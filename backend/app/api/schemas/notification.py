"""Pydantic schemas for the notifications domain (see db/models/notification.py)."""
from datetime import datetime

from pydantic import BaseModel, Field


class NotificationOut(BaseModel):
    id: str
    source: str
    severity: str
    title: str
    message: str | None
    summary: str | None
    job_id: str | None
    job_name: str | None
    profile: str | None
    script_name: str | None
    occurred_at: datetime
    read_at: datetime | None
    created_at: datetime


class NotificationListOut(BaseModel):
    notifications: list[NotificationOut]
    total: int
    unread_count: int


class MarkReadIn(BaseModel):
    """Mark specific notifications (ids) or every unread one (all=True) as read."""

    ids: list[str] | None = None
    all: bool = False


class MarkReadOut(BaseModel):
    marked: int


class CleanupIn(BaseModel):
    """mode='all' deletes everything; mode='keep_days' keeps the last
    `keep_days` days (UI offers 15 or 30) and deletes older rows."""

    mode: str = Field(pattern="^(all|keep_days)$")
    keep_days: int | None = Field(default=None, ge=1, le=365)


class CleanupOut(BaseModel):
    deleted: int

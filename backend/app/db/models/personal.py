"""Personal domain -- Marcelo's own tasks, agenda and notes (2026-10-07).

Marcelo: "não seria bom criar no ForgeHub lista de tarefas, anotações, agenda para a Maia ter
acesso". These rows belong to Marcelo, not to any product/version/project: the traceability chain of
the software factory does not apply here. Access is the admin user (UI) and the agents listed in
``settings.PERSONAL_AGENT_SLUGS`` (default ``maia``, his personal assistant) -- see
``api/routes/personal.py``. Maia reads and writes them through her ``pessoal`` MCP server, and her
cron turns due reminders into Telegram messages (``POST /api/v1/personal/reminders:due``).

Reminders are minutes before the moment (``[1440, 60]`` = a day and an hour before);
``reminders_sent`` holds ``"<moment iso>|<minutes>"`` keys so each one fires once per occurrence,
and moving the moment re-arms them. Recurring items roll forward to their next occurrence.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

PERSONAL_RECURRENCES = ("", "daily", "weekly", "monthly", "yearly")
PERSONAL_TASK_STATUSES = ("pending", "done", "cancelled")
PERSONAL_TASK_PRIORITIES = ("low", "normal", "high")
PERSONAL_EVENT_STATUSES = ("scheduled", "cancelled")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


class PersonalTask(Base, TimestampMixin):
    __tablename__ = "personal_tasks"
    __table_args__ = (
        CheckConstraint(f"status IN ({_in(PERSONAL_TASK_STATUSES)})", name="ck_personal_tasks_status"),
        CheckConstraint(f"priority IN ({_in(PERSONAL_TASK_PRIORITIES)})", name="ck_personal_tasks_priority"),
        CheckConstraint(f"recurrence IN ({_in(PERSONAL_RECURRENCES)})", name="ck_personal_tasks_recurrence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Free list name ("Pessoal", "SEMED", "Darckware", "Casa"...) -- grouping, not a FK.
    list_name: Mapped[str] = mapped_column(String(80), nullable=False, default="Pessoal", server_default="Pessoal")
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default="normal", server_default="normal")
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="pending", server_default="pending")
    #: Local São Paulo wall time (naive). due_has_time=False -> a date-only task (reminds at 8h).
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True, index=True)
    due_has_time: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    recurrence: Mapped[str] = mapped_column(String(10), nullable=False, default="", server_default="")
    reminders: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    reminders_sent: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Who created it: "marcelo" (UI) or the agent's profile slug (e.g. "maia").
    created_by: Mapped[str] = mapped_column(String(50), nullable=False, default="marcelo", server_default="marcelo")


class PersonalEvent(Base, TimestampMixin):
    __tablename__ = "personal_events"
    __table_args__ = (
        CheckConstraint(f"status IN ({_in(PERSONAL_EVENT_STATUSES)})", name="ck_personal_events_status"),
        CheckConstraint(f"recurrence IN ({_in(PERSONAL_RECURRENCES)})", name="ck_personal_events_recurrence"),
        CheckConstraint("ends_at IS NULL OR ends_at >= starts_at", name="ck_personal_events_window"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    #: Local São Paulo wall time (naive).
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, index=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    all_day: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="scheduled", server_default="scheduled")
    recurrence: Mapped[str] = mapped_column(String(10), nullable=False, default="", server_default="")
    reminders: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    reminders_sent: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    created_by: Mapped[str] = mapped_column(String(50), nullable=False, default="marcelo", server_default="marcelo")


class PersonalNote(Base, TimestampMixin):
    __tablename__ = "personal_notes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_by: Mapped[str] = mapped_column(String(50), nullable=False, default="marcelo", server_default="marcelo")

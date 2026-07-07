"""Notification model — persistent record of every surfaced alert.

Replaces the previous client-only notification handling (the bell dropdown
read cron failures live from jobs.json and tracked "seen" in localStorage).
Every cron run outcome is ingested as one row here, so the history survives
page reloads and is shared across browsers/users, read state is tracked
server-side (`read_at`), and old rows can be purged via the cleanup endpoint
(delete all / keep last N days).

Each notification maps back to the cron that produced it via
`job_id`/`job_name`/`profile`/`script_name`. `event_key` is the dedupe key
(`cron:<job_id>:<last_run_at>`) so re-ingesting the same jobs.json snapshot
never duplicates a run. `NotificationIngestState` keeps a per-source
suppression watermark so runs purged via cleanup are never re-ingested
(jobs.json still lists each job's latest run after the rows are deleted).

Conventions: UUID PK (Python-side default), TimestampMixin, String +
CheckConstraint instead of native enums.
"""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

NOTIFICATION_SOURCES = ("cron", "system")
NOTIFICATION_SEVERITIES = ("info", "success", "warning", "error")


class Notification(Base, TimestampMixin):
    """One recorded notification (currently: one cron run outcome).

    `occurred_at` is when the underlying event happened (the cron's
    last_run_at), not when the row was ingested — cleanup retention and
    ordering both use it.
    """

    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "source IN ('cron', 'system')", name="ck_notifications_source"
        ),
        CheckConstraint(
            "severity IN ('info', 'success', 'warning', 'error')",
            name="ck_notifications_severity",
        ),
        # Created by the a4d81f0c2b77 migration but never declared here --
        # the drift made a later autogenerate try to drop it. Keep the
        # migration's custom name (not the ix_company_* convention).
        Index("ix_notifications_occurred_at", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="cron")
    severity: Mapped[str] = mapped_column(String(50), nullable=False, default="info")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Digest of what the run did — extracted from the job's output file
    # (## Response / ## Script Error section), when one exists for the run
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Cron mapping — which job/run produced this notification
    job_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    profile: Mapped[str | None] = mapped_column(String(100), nullable=True)
    script_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Dedupe key: one row per distinct event (e.g. "cron:<job_id>:<run_at>")
    event_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NotificationIngestState(Base, TimestampMixin):
    """Per-source ingestion watermark (one row per source, e.g. 'cron').

    Events whose `occurred_at` is at or before `suppress_before` are skipped
    by ingestion. Cleanup advances it (never backwards): 'all' → now,
    'keep_days' → the retention cutoff. Without this, deleting rows would
    only be temporary — the next listing re-ingests every run still present
    in jobs.json as a fresh unread notification.
    """

    __tablename__ = "notification_ingest_state"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    suppress_before: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

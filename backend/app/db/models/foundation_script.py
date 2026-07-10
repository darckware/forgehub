"""FoundationScript model — registry of scripts the Foundation docs rely on.

Backs the Foundation page's "Scripts" card: a small, manually curated (or
sync-populated) list distinct from the full per-profile Crons/Scripts
catalog (cron_script.py) -- this one specifically tracks which scripts
implement something *documented* under /root/.hermes/foundation (governance
rules, agent docs, integration notes), e.g. a Telegram voice-message
transcriber mentioned in an integrations doc. POST .../sync scans every
Foundation markdown doc for script filename mentions and upserts new rows
(source="sync", doc_path set); operators can also add/remove rows by hand
(source="manual").
"""
import uuid

from sqlalchemy import CheckConstraint, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

FOUNDATION_SCRIPT_SOURCES = ("manual", "sync")


class FoundationScript(Base, TimestampMixin):
    __tablename__ = "foundation_scripts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Relative path (under /foundation-root) of the doc that mentions this
    # script -- set by sync, left null for manually added rows unless the
    # operator fills it in.
    doc_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")

    __table_args__ = (
        CheckConstraint(f"source IN {FOUNDATION_SCRIPT_SOURCES}", name="ck_foundation_scripts_source"),
    )

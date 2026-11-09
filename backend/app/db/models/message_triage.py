"""Durable advisory analysis and fenced operational jobs; Messages stays authoritative."""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class MessageAnalysisRun(Base, TimestampMixin):
    __tablename__ = "message_analysis_runs"
    __table_args__ = (
        CheckConstraint("status IN ('queued','running','completed','failed')", name="ck_message_analysis_status"),
        Index("uq_message_analysis_active_scope", "scope_key", unique=True,
              postgresql_where=text("status IN ('queued','running')")),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope_key: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[dict] = mapped_column(JSONB, nullable=False)
    requested_by: Mapped[str] = mapped_column(String(150), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    applied: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    summary: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class MessageTriageResult(Base, TimestampMixin):
    __tablename__ = "message_triage_results"
    __table_args__ = (CheckConstraint("operator_state IN ('decision','processing','waiting','resolved')",
                                    name="ck_message_triage_state"),)
    message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey("company.agent_demands.id", ondelete="CASCADE"), primary_key=True)
    analysis_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
        ForeignKey("company.message_analysis_runs.id", ondelete="SET NULL"))
    source_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    context_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    context_versions: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    operator_state: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_action: Mapped[str] = mapped_column(String(40), nullable=False)
    related_message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
        ForeignKey("company.agent_demands.id", ondelete="SET NULL"))
    evidence_refs: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    applied_action: Mapped[str | None] = mapped_column(String(40))


class MessageAnalysisItem(Base, TimestampMixin):
    __tablename__ = "message_analysis_items"
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey("company.message_analysis_runs.id", ondelete="CASCADE"), primary_key=True)
    # Keep progress/history even if an operator removes the source later.
    message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)

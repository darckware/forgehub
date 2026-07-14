"""Authoritative progress checkpoints and deterministic stage completion assessments."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

CHECKPOINT_TYPES = (
    "started", "progress", "evidence", "blocked", "failed", "paused",
    "heartbeat_lost", "reconciled", "resumed", "completed",
)
ACTOR_TYPES = ("user", "agent", "system")
ASSESSMENT_RESULTS = ("ready", "not_ready", "stale")


class ProgressCheckpoint(Base, TimestampMixin):
    """Append-only fact describing the last confirmed recoverable execution point."""

    __tablename__ = "progress_checkpoints"
    __table_args__ = (
        CheckConstraint(f"checkpoint_type IN {CHECKPOINT_TYPES!r}", name="ck_progress_checkpoint_type"),
        CheckConstraint(f"actor_type IN {ACTOR_TYPES!r}", name="ck_progress_checkpoint_actor_type"),
        UniqueConstraint("task_execution_id", "sequence", name="uq_progress_checkpoint_execution_sequence"),
        UniqueConstraint("idempotency_key", name="uq_progress_checkpoint_idempotency"),
        Index("ix_progress_checkpoint_project_created", "project_id", "created_at"),
        Index("ix_progress_checkpoint_stage_created", "pipeline_stage_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.projects.id", ondelete="CASCADE"), nullable=False
    )
    pipeline_stage_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.pipeline_stages.id", ondelete="CASCADE"), nullable=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.project_tasks.id", ondelete="CASCADE"), nullable=True
    )
    task_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.task_executions.id", ondelete="CASCADE"), nullable=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    checkpoint_type: Mapped[str] = mapped_column(String(30), nullable=False)
    step_key: Mapped[str] = mapped_column(String(150), nullable=False)
    step_label: Mapped[str] = mapped_column(String(255), nullable=False)
    state_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    completed_requirement_keys: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    evidence_refs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    last_confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    resume_from_step_key: Mapped[str | None] = mapped_column(String(150), nullable=True)
    blocker_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_name: Mapped[str] = mapped_column(String(150), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)


class StageCompletionAssessment(Base, TimestampMixin):
    """Immutable deterministic evaluation of whether a stage can complete."""

    __tablename__ = "stage_completion_assessments"
    __table_args__ = (
        CheckConstraint(f"result IN {ASSESSMENT_RESULTS!r}", name="ck_stage_completion_result"),
        UniqueConstraint("pipeline_stage_id", "input_hash", name="uq_stage_completion_stage_input"),
        Index("ix_stage_completion_stage_evaluated", "pipeline_stage_id", "evaluated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pipeline_stage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.pipeline_stages.id", ondelete="CASCADE"), nullable=False
    )
    stage_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    baseline_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.plan_baselines.id", ondelete="SET NULL"), nullable=True
    )
    policy_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.policy_versions.id", ondelete="SET NULL"), nullable=True
    )
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    requirement_results: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    missing_requirements: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    blocking_reasons: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    evidence_refs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    evaluator_version: Mapped[str] = mapped_column(String(50), nullable=False, default="stage-completion-v1")
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    evaluated_by_type: Mapped[str] = mapped_column(String(20), nullable=False)
    evaluated_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    evaluated_by_name: Mapped[str] = mapped_column(String(150), nullable=False)


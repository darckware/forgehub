"""Durable execution waves, work packages, runner leases, events and results."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

WAVE_STATUSES = ("draft", "approved", "active", "paused", "completed", "cancelled")
PACKAGE_STATUSES = ("draft", "validated", "issued", "superseded", "expired", "cancelled")
LEASE_STATUSES = ("claimed", "running", "expired", "released", "cancelled")
RUNNER_STATUSES = ("online", "degraded", "offline", "disabled")


class ExecutionWave(Base, TimestampMixin):
    __tablename__ = "execution_waves"
    __table_args__ = (
        CheckConstraint(f"status IN {WAVE_STATUSES!r}", name="ck_execution_wave_status"),
        UniqueConstraint("project_id", "idempotency_key", name="uq_execution_wave_project_idempotency"),
        Index("ix_execution_wave_project_status", "project_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company.projects.id", ondelete="CASCADE"), nullable=False)
    baseline_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company.plan_baselines.id", ondelete="RESTRICT"), nullable=False)
    pipeline_stage_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("company.pipeline_stages.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    authorized_by_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    authorized_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    delegation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("company.authority_delegations.id", ondelete="SET NULL"), nullable=True)
    wip_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    budget_limit: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    preflight_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    preflight_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExecutionWaveTask(Base, TimestampMixin):
    __tablename__ = "execution_wave_tasks"
    __table_args__ = (
        UniqueConstraint("execution_wave_id", "task_id", name="uq_execution_wave_task"),
        Index("ix_execution_wave_task_task", "task_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    execution_wave_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company.execution_waves.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company.project_tasks.id", ondelete="CASCADE"), nullable=False)
    release_order: Mapped[int] = mapped_column(Integer, nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExecutionWorkPackage(Base, TimestampMixin):
    __tablename__ = "execution_work_packages"
    __table_args__ = (
        CheckConstraint(f"status IN {PACKAGE_STATUSES!r}", name="ck_execution_work_package_status"),
        UniqueConstraint("task_id", "revision", name="uq_execution_work_package_task_revision"),
        UniqueConstraint("idempotency_key", name="uq_execution_work_package_idempotency"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company.project_tasks.id", ondelete="CASCADE"), nullable=False)
    assignment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company.task_assignments.id", ondelete="RESTRICT"), nullable=False)
    runtime_profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company.agent_runtime_profiles.id", ondelete="RESTRICT"), nullable=False)
    execution_wave_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company.execution_waves.id", ondelete="RESTRICT"), nullable=False)
    baseline_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company.plan_baselines.id", ondelete="RESTRICT"), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    contract_version: Mapped[str] = mapped_column(String(80), nullable=False, default="forge-engineering-work-package/v1")
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    validation_errors: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExecutionRunner(Base, TimestampMixin):
    __tablename__ = "execution_runners"
    __table_args__ = (CheckConstraint(f"status IN {RUNNER_STATUSES!r}", name="ck_execution_runner_status"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    runner_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="offline")
    adapter_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    capabilities: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ExecutionLease(Base, TimestampMixin):
    __tablename__ = "execution_leases"
    __table_args__ = (
        CheckConstraint(f"status IN {LEASE_STATUSES!r}", name="ck_execution_lease_status"),
        UniqueConstraint("work_package_id", name="uq_execution_lease_work_package"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    work_package_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company.execution_work_packages.id", ondelete="CASCADE"), nullable=False)
    runner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company.execution_runners.id", ondelete="RESTRICT"), nullable=False)
    task_execution_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("company.task_executions.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="claimed")
    leased_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExecutionEvent(Base, TimestampMixin):
    __tablename__ = "execution_events"
    __table_args__ = (
        UniqueConstraint("task_execution_id", "sequence", name="uq_execution_event_sequence"),
        UniqueConstraint("idempotency_key", name="uq_execution_event_idempotency"),
        Index("ix_execution_event_execution_created", "task_execution_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_execution_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company.task_executions.id", ondelete="CASCADE"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)


class ExecutionResult(Base, TimestampMixin):
    __tablename__ = "execution_results"
    __table_args__ = (UniqueConstraint("task_execution_id", name="uq_execution_result_execution"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_execution_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company.task_executions.id", ondelete="CASCADE"), nullable=False)
    contract_version: Mapped[str] = mapped_column(String(80), nullable=False, default="forge-engineering-result/v1")
    result_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    result_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    is_stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    validation_errors: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

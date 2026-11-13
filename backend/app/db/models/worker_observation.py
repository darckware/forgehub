"""Bounded metadata for independently auditing completed background passes."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class WorkerObservation(Base, TimestampMixin):
    __tablename__ = 'operational_worker_observations'
    __table_args__ = (
        UniqueConstraint('worker_name', name='uq_worker_observations_name'),
        CheckConstraint("last_status IN ('starting','running','ok','error','disabled')", name='ck_worker_observations_status'),
        CheckConstraint('interval_seconds > 0', name='ck_worker_observations_interval'),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    worker_name: Mapped[str] = mapped_column(String(80), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    active_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    last_status: Mapped[str] = mapped_column(String(16), nullable=False)
    last_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_type: Mapped[str | None] = mapped_column(String(80))

"""Off-site backup: what goes to the encrypted restic repository on Google
Drive, one unit per project (2026-10-20, Marcelo: "melhor fazer por projeto"
and "adicione esse controle na tela Controle do sistema ... onde posso adicionar
outras pastas").

ForgeHub holds the list and the history; the work runs on the host, in Athos'
`backup_offsite_projects.py` (scheduled by `hermes cron`), which reads the plan
from `GET /api/v1/offsite-backup/internal/plan` and reports each target's
outcome back. One restic repository for every target, each snapshot tagged
`target:<name>`, so data shared between projects is stored once and a project
is still restored on its own.
"""
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

OFFSITE_BACKUP_RUN_STATUSES = ("running", "ok", "failed", "interrupted")
OFFSITE_BACKUP_TRIGGERS = ("schedule", "manual")
# Repository-wide maintenance (Sunday prune + integrity check) is recorded as a
# run with no target and this name -- it belongs to no single project.
REPOSITORY_RUN_NAME = "__repository__"


class OffsiteBackupTarget(Base, TimestampMixin):
    __tablename__ = "offsite_backup_targets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Slug, never renamed: it is the restic tag every past snapshot carries.
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    # Absolute host paths (folders or files).
    paths: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    # restic --exclude patterns, on top of the worker's global list
    # (node_modules, venvs, caches, build output).
    excludes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    # Every database of this Postgres container is dumped and goes in the same snapshot.
    postgres_container: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Online SQLite copies of Hermes/Foundation plus installed-package state:
    # what rebuilding the host needs and a file copy can't capture.
    include_system_state: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class OffsiteBackupRun(Base, TimestampMixin):
    __tablename__ = "offsite_backup_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'ok', 'failed', 'interrupted')", name="ck_offsite_backup_run_status"
        ),
        CheckConstraint("trigger IN ('schedule', 'manual')", name="ck_offsite_backup_run_trigger"),
        Index("ix_offsite_backup_runs_target_started", "target_name", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # SET NULL keeps the history of a removed target; target_name says whose it was.
    target_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.offsite_backup_targets.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    target_name: Mapped[str] = mapped_column(String(64), nullable=False)
    trigger: Mapped[str] = mapped_column(String(20), nullable=False, default="schedule")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    files_new: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_added: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    total_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

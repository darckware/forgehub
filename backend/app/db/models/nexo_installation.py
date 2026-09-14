"""Nexo agent build artifacts and current workstation installation history."""
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


BUILD_STATUSES = ("queued", "building", "ready", "failed")
INSTALLATION_STATUSES = ("package_ready", "downloaded", "online", "outdated", "error")
INSTALLATION_EVENT_TYPES = (
    "package_generated",
    "downloaded",
    "first_report",
    "version_mismatch",
    "error",
)


class NexoAgentBuild(Base, TimestampMixin):
    __tablename__ = "nexo_agent_builds"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    git_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    agent_version: Mapped[str] = mapped_column(String(50), nullable=False)
    os_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    artifact_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    artifact_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    build_log_excerpt: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("os_kind IN ('linux', 'windows')", name="ck_nexo_agent_builds_os_kind"),
        CheckConstraint(
            "status IN ('queued', 'building', 'ready', 'failed')",
            name="ck_nexo_agent_builds_status",
        ),
        UniqueConstraint("git_sha", "os_kind", name="uq_nexo_agent_builds_sha_os"),
        Index("ix_nexo_agent_builds_status", "status"),
    )


class WorkstationInstallation(Base, TimestampMixin):
    __tablename__ = "workstation_installations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workstation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.workstations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    build_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.nexo_agent_builds.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    package_generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    online_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('package_ready', 'downloaded', 'online', 'outdated', 'error')",
            name="ck_workstation_installations_status",
        ),
    )


class WorkstationInstallationEvent(Base):
    __tablename__ = "workstation_installation_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    installation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.workstation_installations.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    detail: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "event_type IN ('package_generated', 'downloaded', 'first_report', "
            "'version_mismatch', 'error')",
            name="ck_workstation_installation_events_event_type",
        ),
        CheckConstraint(
            "from_status IS NULL OR from_status IN "
            "('package_ready', 'downloaded', 'online', 'outdated', 'error')",
            name="ck_workstation_installation_events_from_status",
        ),
        CheckConstraint(
            "to_status IN ('package_ready', 'downloaded', 'online', 'outdated', 'error')",
            name="ck_workstation_installation_events_to_status",
        ),
        Index(
            "ix_workstation_installation_events_installation_created",
            "installation_id",
            "created_at",
        ),
    )

"""Script library and schedules for Remote Access (plan step 1, 2026-10-16,
docs/architecture/REMOTE_MAINTENANCE_PLAN.md).

A `HostScript` is a reusable, versioned script for one platform (Windows
PowerShell, Linux sh, macOS sh), classified by a `HostScriptCategory`
(fixed list, extensible by an admin). Every edit of the content is a new
`HostScriptVersion`; an execution records the exact version it ran.
Parameters are declared on the script and reach it as variables
($NAME in PowerShell, $NAME in sh) set before the content -- values are
quoted, never spliced into the script text.

A `HostSchedule` runs a script on machines/groups once (`run_at`) or on a
weekly rhythm (weekdays + time, in the client's timezone). Each run is an
ordinary HostExecution (trigger="schedule"); a machine that can't be reached
is retried until the run's window closes, then reads "not run".
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

SCRIPT_PLATFORMS = ("windows", "linux", "macos")
SCRIPT_RISKS = ("read", "change", "destructive")
DEFAULT_CATEGORIES = (
    ("diagnostico", "Diagnóstico"),
    ("manutencao", "Manutenção"),
    ("instalacao", "Instalação"),
    ("seguranca", "Segurança"),
    ("limpeza", "Limpeza"),
)


class HostScriptCategory(Base, TimestampMixin):
    __tablename__ = "host_script_categories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class HostScript(Base, TimestampMixin):
    __tablename__ = "host_scripts"
    __table_args__ = (
        CheckConstraint("platform IN ('windows', 'linux', 'macos')", name="ck_host_scripts_platform"),
        CheckConstraint("risk IN ('read', 'change', 'destructive')", name="ck_host_scripts_risk"),
        UniqueConstraint("name", "platform", name="uq_host_scripts_name_platform"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.host_script_categories.id", ondelete="RESTRICT"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Decides where it may run and how: windows -> PowerShell, linux/macos -> sh.
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    risk: Mapped[str] = mapped_column(String(20), nullable=False, default="read")
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    # [{"name": "SERVICE", "label": "...", "required": true, "default": null}]
    parameters: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Shipped by ForgeHub (preparation, enrollment, rotations): not editable or
    # deletable from the screen.
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    # Stable identity of a system script ("tailscale_install", ...): the seed
    # updates it in place, and the runner knows what to record on success.
    system_key: Mapped[str | None] = mapped_column(String(60), nullable=True, unique=True)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_by: Mapped[str] = mapped_column(String(150), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(150), nullable=False)


class HostScriptVersion(Base, TimestampMixin):
    __tablename__ = "host_script_versions"
    __table_args__ = (UniqueConstraint("script_id", "version", name="uq_host_script_versions"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    script_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.host_scripts.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    parameters: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    changed_by: Mapped[str] = mapped_column(String(150), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)


class HostSchedule(Base, TimestampMixin):
    __tablename__ = "host_schedules"
    __table_args__ = (
        CheckConstraint("kind IN ('once', 'weekly')", name="ck_host_schedules_kind"),
        CheckConstraint(
            "(kind = 'once' AND run_at IS NOT NULL) OR (kind = 'weekly' AND weekdays IS NOT NULL AND time_of_day IS NOT NULL)",
            name="ck_host_schedules_shape",
        ),
        Index("ix_host_schedules_due", "enabled", "next_run_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    script_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.host_scripts.id", ondelete="CASCADE"), nullable=False
    )
    parameter_values: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    server_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    group_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # weekly: ISO weekdays 1 (Mon) .. 7 (Sun) and "HH:MM" in `timezone`.
    weekdays: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    time_of_day: Mapped[str | None] = mapped_column(String(5), nullable=True)
    timezone: Mapped[str] = mapped_column(String(60), nullable=False, default="America/Sao_Paulo")
    # How long an unreachable machine is retried after the due time.
    window_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=120)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.host_executions.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[str] = mapped_column(String(150), nullable=False)
    # Set when an agent created it (MCP), so its runs log under that agent.
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agents.id", ondelete="SET NULL"), nullable=True
    )

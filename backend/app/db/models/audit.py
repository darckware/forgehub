"""Audit domain: configurable ecosystem checkpoints.

`audit_checks` is the checklist -- each row is one verification point
(a bash command executed on the HOST via the chat bridge's /v1/exec,
exit code 0 = ok). `audit_check_runs` records every execution so the
Auditor page can show current health and history. Checks are seeded
from the pre-existing healthcheck scripts in the athos profile (script
audit of 2026-07-07) and managed from the Auditor page.
"""
import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

AUDIT_RUN_STATUSES = ("ok", "fail", "error", "timeout")


class AuditCheck(Base, TimestampMixin):
    __tablename__ = "audit_checks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Free-form grouping shown as a badge (e.g. "infra", "cron", "kanboard").
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Bash command executed on the host through the chat bridge. Exit 0 = ok.
    command: Mapped[str] = mapped_column(Text, nullable=False)
    # Optional, explicit recovery action. It is never run as part of the
    # checklist: an administrator must confirm it from the Auditor page.
    remediation_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    remediation_command: Mapped[str | None] = mapped_column(Text, nullable=True)
    workdir: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Profile responsible for this checkpoint (display/ownership -- execution
    # is host-side via the bridge either way).
    agent_profile: Mapped[str] = mapped_column(String(50), nullable=False, default="athos")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Defaults to 55s; explicitly bounded maintenance may use up to 600s.
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=55)

    runs: Mapped[list["AuditCheckRun"]] = relationship(
        back_populates="check", cascade="all, delete-orphan"
    )


class AuditCheckRun(Base, TimestampMixin):
    __tablename__ = "audit_check_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    check_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.audit_checks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # stdout+stderr, truncated by the route layer (never store unbounded).
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # "manual"/"cron", or "remediation"/"remediation-verification" for
    # the administrator-confirmed repair cycle.
    requested_by: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")

    check: Mapped[AuditCheck] = relationship(back_populates="runs")

    __table_args__ = (
        CheckConstraint(
            f"status IN {AUDIT_RUN_STATUSES}", name="ck_audit_check_runs_status"
        ),
    )

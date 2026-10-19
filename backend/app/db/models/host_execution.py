"""Command executions on machines (Remote Access phase 4,
docs/architecture/REMOTE_MAINTENANCE_PLAN.md).

One `HostExecution` is one request ("run this on these machines"); it has one
`HostExecutionResult` per machine, which is what the execution screen shows:
output, exit code, duration and a clear succeeded/failed verdict. A follow-up
run on the machines that failed points back through `parent_execution_id`, so
the history reads failure -> fix -> result.

The command and the outputs are stored already masked (core/secret_masking.py):
the unmasked script only ever lives in memory for the duration of the run.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

HOST_EXECUTION_SHELLS = ("sh", "powershell")
HOST_EXECUTION_STATUSES = ("running", "completed", "cancelled")
HOST_RESULT_STATUSES = ("pending", "running", "succeeded", "failed", "skipped")
HOST_RESULT_FAILURES = ("timeout", "auth", "connection", "command", "interrupted")


class HostExecution(Base, TimestampMixin):
    __tablename__ = "host_executions"
    __table_args__ = (
        CheckConstraint("shell IN ('sh', 'powershell')", name="ck_host_executions_shell"),
        CheckConstraint(
            "status IN ('running', 'completed', 'cancelled')", name="ck_host_executions_status"
        ),
        Index("ix_host_executions_parent", "parent_execution_id"),
        CheckConstraint(
            "trigger IN ('manual', 'schedule', 'agent')", name="ck_host_executions_trigger"
        ),
        CheckConstraint(
            "(darckware_item_kind IS NULL AND darckware_item_id IS NULL) OR "
            "(darckware_item_kind IN ('ticket', 'demand') AND darckware_item_id IS NOT NULL)",
            name="ck_host_executions_darckware_item",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parent_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.host_executions.id", ondelete="SET NULL"), nullable=True
    )
    shell: Mapped[str] = mapped_column(String(20), nullable=False)
    # Masked copy of what ran.
    command: Mapped[str] = mapped_column(Text, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    requested_by: Mapped[str] = mapped_column(String(150), nullable=False)
    # Where it came from (decision 7, 2026-10-16: logs per agent): "manual"
    # (a person on the screen), "schedule" or "agent" (MCP). `agent_id` is
    # the agent that asked -- directly, or by owning the schedule.
    trigger: Mapped[str] = mapped_column(String(20), nullable=False, default="manual", server_default="manual")
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.host_schedules.id", ondelete="SET NULL"), nullable=True
    )
    # The library script and exact version that ran (NULL = ad-hoc command).
    script_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.host_scripts.id", ondelete="SET NULL"), nullable=True
    )
    script_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    script_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    # Unreachable machines are retried until this instant (scheduled runs).
    retry_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Human description of what was targeted ("Secretaria + 2 machines").
    target_summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Touched every HEARTBEAT_SECONDS by the process running it. Recovery
    # closes only executions whose heartbeat went stale -- dev and production
    # share this database, so "I just started, so everything running is
    # mine and dead" would kill the other process's live runs.
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The maintenance record (2026-10-19): why it ran -- required when an
    # agent asks -- and the Darckware client ticket/demand it serves
    # (Darckware's id, no FK: the item lives in Darckware).
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    darckware_item_kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    darckware_item_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class HostExecutionResult(Base, TimestampMixin):
    __tablename__ = "host_execution_results"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', 'skipped')",
            name="ck_host_execution_results_status",
        ),
        CheckConstraint(
            "failure IS NULL OR failure IN ('timeout', 'auth', 'connection', 'command', 'interrupted')",
            name="ck_host_execution_results_failure",
        ),
        Index("ix_host_execution_results_execution", "execution_id"),
        Index("ix_host_execution_results_server_status", "server_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.host_executions.id", ondelete="CASCADE"), nullable=False
    )
    # SET NULL + name snapshot: deleting a machine must not erase what was
    # done on it.
    server_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.servers.id", ondelete="SET NULL"), nullable=True
    )
    server_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    failure: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Why a machine was not run at all (parked, no login, wrong OS, busy,
    # cancelled).
    skip_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stdout: Mapped[str | None] = mapped_column(Text, nullable=True)
    stderr: Mapped[str | None] = mapped_column(Text, nullable=True)
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

"""Collaborative execution in an active session with Marcelo
(docs/architecture/REMOTE_ACCESS_RULE.md, "Execução colaborativa autorizada em
sessão ativa"). Behind settings.REMOTE_COLLABORATION_ENABLED, off by default.

A session binds, at opening, Marcelo's live browser session, one agent, the
task and the exact run it was dispatched with, one machine and the operation he
authorized. Each command is authorized by him beforehand, byte for byte, and
runs at most once. Nothing here is a grant by itself: core/remote_collaboration.py
re-checks every binding at each command, so the session ends with the first of
logout, run end, expiry, pause or an explicit end.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

COLLABORATION_SESSION_STATUSES = ("active", "ended", "revoked")
COLLABORATION_COMMAND_STATUSES = ("authorized", "used", "revoked")


class RemoteCollaborationSession(Base, TimestampMixin):
    __tablename__ = "remote_collaboration_sessions"
    __table_args__ = (
        CheckConstraint("status IN ('active','ended','revoked')", name="ck_remote_collaboration_session_status"),
        CheckConstraint("length(btrim(operation)) > 0", name="ck_remote_collaboration_session_operation"),
        Index("ix_remote_collaboration_sessions_agent_status", "agent_id", "status"),
        # At most one active session per agent, even under a race between two openings.
        Index("uq_remote_collaboration_sessions_one_active", "agent_id", unique=True,
              postgresql_where=text("status = 'active'")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.users.id"), nullable=False)
    # SET NULL, never CASCADE: purge_old_sessions (90 days) or deleting a machine
    # must not erase the authorization record. NULL = the session can't be used
    # (require_session_current/_dead_reason fail closed on it).
    user_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.user_sessions.id", ondelete="SET NULL"), nullable=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company.agents.id"), nullable=False)
    agent_demand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agent_demands.id"), nullable=False)
    agent_run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    server_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.servers.id", ondelete="SET NULL"), nullable=True)
    operation: Mapped[str] = mapped_column(Text, nullable=False)
    allow_elevation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_by: Mapped[str | None] = mapped_column(String(200))
    end_reason: Mapped[str | None] = mapped_column(Text)


class RemoteCollaborationCommand(Base, TimestampMixin):
    __tablename__ = "remote_collaboration_commands"
    __table_args__ = (
        CheckConstraint("status IN ('authorized','used','revoked')", name="ck_remote_collaboration_command_status"),
        CheckConstraint("shell IN ('sh','powershell')", name="ck_remote_collaboration_command_shell"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # CASCADE is inert: the application never deletes a collaborative session
    # (they end, with status), and no FK above cascades a delete onto one.
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.remote_collaboration_sessions.id", ondelete="CASCADE"),
        nullable=False, index=True)
    command: Mapped[str] = mapped_column(Text, nullable=False)
    shell: Mapped[str] = mapped_column(String(20), nullable=False)
    command_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    allow_elevation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    authorized_by: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="authorized", server_default="authorized")
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.host_executions.id", ondelete="SET NULL"), unique=True)

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class VpnOperationEvent(Base, TimestampMixin):
    __tablename__ = "vpn_operation_events"
    __table_args__ = (
        # "self"/"peer" since the Remote Access rework (2026-10-15); "local"/
        # "remote" and connect/disconnect only remain in older history rows.
        CheckConstraint(
            "target IN ('self', 'peer', 'local', 'remote')", name="ck_vpn_operation_events_target"
        ),
        CheckConstraint(
            "action IN ('connect', 'disconnect', 'restart', 'test')",
            name="ck_vpn_operation_events_action",
        ),
        CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')",
            name="ck_vpn_operation_events_status",
        ),
        Index("ix_vpn_operation_events_created_at", "created_at"),
        Index("ix_vpn_operation_events_target_created_at", "target", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    target: Mapped[str] = mapped_column(String(20), nullable=False)
    # Peer's stable Tailscale ID and machine name at the time of the action
    # (the name is a snapshot: a device can be renamed later).
    target_node_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    summary: Mapped[str | None] = mapped_column(String(500), nullable=True)

    actor: Mapped[object | None] = relationship("User", lazy="joined")


class TailnetPolicyVersion(Base, TimestampMixin):
    """A copy of the Tailscale policy file, pasted on the Remote Access page.

    Tailscale's admin console is where the policy actually lives; this is the
    record of what it said and who recorded it when, analyzed for the one rule
    Remote Access depends on (server -> client tags on SSH, see
    core/tailnet_policy.py). Append-only: a new paste is a new row.
    """

    __tablename__ = "tailnet_policy_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    saved_by: Mapped[str] = mapped_column(String(150), nullable=False)

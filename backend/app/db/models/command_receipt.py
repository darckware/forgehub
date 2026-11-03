"""Idempotency receipts for agent/operator commands (Plano Integrado M0.2a).

Contract: docs/architecture/MCP_MISSION_TOOLS_SPEC.md §0.4. One row per
(principal, idempotency_key): the request hash and the response that the
first call produced. Replaying the same key with the same body returns the
stored response; the same key with a different body is a 409. Written in the
same transaction as the effect, so a receipt never exists without its effect
(nor the other way round). Kept 30 days (``RECEIPT_RETENTION_DAYS``), then
deleted by the retention sweep in ``core/command_receipts.py``.

``target_type``/``target_id`` are polymorphic on purpose (no FK), like
``AuditEvent``: a receipt outlives nothing it points to, and it is only read
back by its own key.
"""
import uuid

from sqlalchemy import Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

RECEIPT_RETENTION_DAYS = 30


class AgentCommandReceipt(Base, TimestampMixin):
    __tablename__ = "agent_command_receipts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    principal_type: Mapped[str] = mapped_column(String(20), nullable=False)
    principal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(150), nullable=False)
    command: Mapped[str] = mapped_column(String(80), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict] = mapped_column(JSONB, nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "principal_type", "principal_id", "idempotency_key", name="uq_agent_command_receipts_principal_key"
        ),
        Index("ix_agent_command_receipts_created_at", "created_at"),
    )

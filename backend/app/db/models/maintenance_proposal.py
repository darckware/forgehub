"""Single-use human approval of an exact maintenance script fingerprint."""
import uuid
from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin


class MaintenanceProposal(Base, TimestampMixin):
    __tablename__ = "maintenance_proposals"
    __table_args__ = (CheckConstraint("status IN ('proposed','approved','rejected','expired','claimed','succeeded','failed')", name="ck_maintenance_proposal_status"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("company.agents.id"), nullable=False)
    agent_demand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("company.agent_demands.id"), nullable=False)
    server_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    shell: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    risk: Mapped[str] = mapped_column(String(20), nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    requires_elevation: Mapped[bool] = mapped_column(Boolean, nullable=False)
    parameters: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    expected_effect: Mapped[str] = mapped_column(Text, nullable=False)
    rollback: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="proposed")
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("company.users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execution_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("company.host_executions.id"), unique=True)

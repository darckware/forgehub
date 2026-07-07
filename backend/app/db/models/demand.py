"""AgentDemand: an inbox item submitted by an agent (or a user note),
"like an e-mail" per the request that created this domain -- read it,
then convert it into a Task, a Docs document, an Artifact, or a
Knowledge Base note (see app/core/conversions.py). Notes/annotations
(existing /root/docs files) go through the same conversion helpers via
api/routes/docs.py's /convert, without needing a demand row.
"""
import uuid

from sqlalchemy import CheckConstraint, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

DEMAND_STATUSES = ("new", "read", "converted", "archived")

# Kept in sync with core/conversions.py's CONVERT_TARGETS.
DEMAND_CONVERT_TARGETS = ("task", "doc", "artifact", "knowledge_base")


class AgentDemand(Base, TimestampMixin):
    __tablename__ = "agent_demands"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Hermes profile slug of the submitting agent (e.g. "athos").
    from_agent: Mapped[str] = mapped_column(String(50), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="new")

    # Set together when /convert succeeds -- what this demand became and
    # where to find it (task id / doc path / artifact id / vault note path).
    converted_entity_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    converted_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)

    __table_args__ = (
        CheckConstraint(f"status IN {DEMAND_STATUSES}", name="ck_agent_demands_status"),
        CheckConstraint(
            f"converted_entity_type IS NULL OR converted_entity_type IN {DEMAND_CONVERT_TARGETS}",
            name="ck_agent_demands_converted_entity_type",
        ),
    )

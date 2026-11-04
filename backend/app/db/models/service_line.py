"""Service-line catalog."""
import uuid

from sqlalchemy import Boolean, Integer, String, Text, false, true
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ServiceLine(Base, TimestampMixin):
    __tablename__ = "service_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    stages: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    required_documents: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    evidence_types: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    default_agents: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    sla_hours: Mapped[int | None] = mapped_column(Integer)
    darckware_contract_type: Mapped[str | None] = mapped_column(Text)
    client_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())

"""DocLink: cross-reference between a /root/docs document and a Planning
entity (product, version, project, pipeline, planning item, task,
artifact). Polymorphic (entity_type, entity_id) with no real FK, same
deliberate pattern as governance's Approval/AuditEvent -- the doc side is
a filesystem path, not a table row, so referential integrity is enforced
at the route layer (see api/routes/docs.py link endpoints).
"""
import uuid

from sqlalchemy import CheckConstraint, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

DOC_LINK_ENTITY_TYPES = (
    "product",
    "product_version",
    "project",
    "pipeline",
    "planning_item",
    "task",
    "artifact",
)


class DocLink(Base, TimestampMixin):
    __tablename__ = "doc_links"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Path relative to /docs (the Docs page's tree paths).
    doc_path: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    __table_args__ = (
        CheckConstraint(
            f"entity_type IN {DOC_LINK_ENTITY_TYPES}", name="ck_doc_links_entity_type"
        ),
        UniqueConstraint(
            "doc_path", "entity_type", "entity_id", name="uq_doc_links_doc_entity"
        ),
    )

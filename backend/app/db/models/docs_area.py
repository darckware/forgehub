"""DocsArea: a user-configurable "área de criação" root for the Docs page
-- any absolute path on the host filesystem (mounted whole at /host-root,
see docker-compose.yml), not just /root/docs. At least one area must
always exist (enforced at the route layer, see docs.py's DELETE /areas).
"""
import uuid

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class DocsArea(Base, TimestampMixin):
    __tablename__ = "docs_creation_areas"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Absolute path on the HOST filesystem, e.g. "/root/docs", "/root/project".
    # Resolved inside the container as HOST_ROOT / host_path.lstrip("/").
    host_path: Mapped[str] = mapped_column(String(1000), nullable=False, unique=True)

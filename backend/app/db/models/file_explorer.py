"""ExplorerQuickAccessEntry -- one user's Workspace Explorer Quick access.

The Explorer's Quick access starts from built-in entries computed by the
frontend (Home, Projects, the Workspace working folder, every Project with a
working_directory_path, Root). A row here is one user's change to that list:
  hidden = False -> a folder the user pinned ("Pin to Quick access");
  hidden = True  -> a built-in entry the user removed ("Unpin").
Storing only the user's deviations -- not a full copy of the list -- means a
newly registered Project still shows up for everyone without a backfill, and
unpinning a built-in survives reloads and other browsers (localStorage would
not). One row per (user, path).
"""
import uuid

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ExplorerQuickAccessEntry(Base, TimestampMixin):
    __tablename__ = "explorer_quick_access"
    __table_args__ = (UniqueConstraint("user_id", "path", name="uq_explorer_quick_access_user_path"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    path: Mapped[str] = mapped_column(String(4096), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

"""Profile and ProfilePermission models for RBAC.

A Profile groups a named set of per-module permissions.  Users are
assigned exactly one profile (nullable — admins bypass all checks).
Each ProfilePermission row covers one module with four boolean flags:
  can_view    — module visible in the sidebar, page accessible
  can_query   — list/read records (GET endpoints)
  can_write   — create/update records (POST/PATCH endpoints)
  can_delete  — delete records (DELETE endpoints)
"""
import uuid

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

MODULES = [
    "product", "projects", "pipeline", "backlog", "tasks", "agents",
    "artifacts", "governance", "forgerouter", "kanboard", "obsidian",
    "foundation", "crons", "deploy", "database", "users", "profiles",
]


class Profile(Base, TimestampMixin):
    """Named access profile — owns a set of ProfilePermission rows."""

    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    permissions: Mapped[list["ProfilePermission"]] = relationship(
        "ProfilePermission", back_populates="profile", cascade="all, delete-orphan"
    )


class ProfilePermission(Base, TimestampMixin):
    """One row per (profile, module) pair with the four permission flags."""

    __tablename__ = "profile_permissions"
    __table_args__ = (
        UniqueConstraint("profile_id", "module", name="uq_profile_module"),
        {"schema": None},  # inherits schema from Base metadata
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    module: Mapped[str] = mapped_column(String(100), nullable=False)
    can_view: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    can_query: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    can_write: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_delete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    profile: Mapped["Profile"] = relationship("Profile", back_populates="permissions")

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
    "artifacts", "governance", "forgerouter", "obsidian",
    "foundation", "crons", "deploy", "database", "users", "profiles",
]

SENSITIVE_ACTIONS = (
    "planning.concept.view", "planning.concept.edit", "planning.concept.submit",
    "planning.concept.decide", "planning.blueprint.edit", "planning.blueprint.approve",
    "planning.delivery.authorize", "planning.delivery.generate_artifacts",
    "planning.progress.view", "planning.progress.manage",
    "planning.stage.complete", "governance.approval.view",
    "planning.execution.view", "planning.execution.manage",
    "planning.execution.release", "planning.execution.dispatch", "planning.execution.cancel",
    "governance.approval.decide", "governance.delegation.manage",
    # 2026-08-05, see docs/architecture/CHANNEL_AGENT_ROLES_AND_ORCHESTRATION.md
    # -- lets a delegated agent-orchestrator (e.g. Athos) set/edit another
    # channel member's function, same governed-authority mechanism as the
    # governance.* actions above (grantable via AuthorityDelegation to an
    # agent, or via ProfileActionPermission to a non-admin human).
    "channel.member.role.assign",
    # Distinct from role.assign above -- deciding who is in the room
    # (add/remove) vs. adjusting an existing member's function are
    # different trust boundaries (2026-08-05, Marcelo: "o orquestrador pode
    # adicionar agentes que não foram colocados no canal").
    "channel.member.manage",
    # 2026-08-06 -- the channel itself (rename/archive/orchestrator
    # designation, delete), distinct from channel.member.manage above
    # (who's in the room) and channel.member.role.assign (their function).
    "channel.manage",
)


class Profile(Base, TimestampMixin):
    """Named access profile — owns a set of ProfilePermission rows."""

    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    permissions: Mapped[list["ProfilePermission"]] = relationship(
        "ProfilePermission", back_populates="profile", cascade="all, delete-orphan"
    )
    action_permissions: Mapped[list["ProfileActionPermission"]] = relationship(
        "ProfileActionPermission", back_populates="profile", cascade="all, delete-orphan"
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


class ProfileActionPermission(Base, TimestampMixin):
    """Deny-by-default permission for a sensitive domain command."""

    __tablename__ = "profile_action_permissions"
    __table_args__ = (
        UniqueConstraint("profile_id", "action_key", name="uq_profile_action_permission"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.profiles.id", ondelete="CASCADE"), nullable=False
    )
    action_key: Mapped[str] = mapped_column(String(150), nullable=False)
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    profile: Mapped["Profile"] = relationship("Profile", back_populates="action_permissions")

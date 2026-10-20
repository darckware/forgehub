"""CronScript model — registry of every Hermes ecosystem script.

Backs the Crons/Scripts catalog page. The filesystem is the source of truth
for script *content*; the DB is the source of truth for *metadata* (agent
ownership, category, description, active flag). A POST /api/v1/scripts/sync
upserts rows from the mounted script directories into this table.

Conventions: UUID PK (Python-side default), TimestampMixin.
"""
import uuid

from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

SCRIPT_CATEGORIES = (
    "foundation",
    "ecosystem",
    "monitor",
    "pipeline",
    "database",
    "memory",
    "dashboard",
    "maintenance",
    "utility",
)

# Legacy pre-2026-07-06 location values ('main' = /hermes-scripts,
# 'central' = /hermes-cron, 'profile' = generic per-agent dir). Since the
# central dirs were migrated into the athos profile, `location` holds the
# owning PROFILE NAME; the legacy values may linger in old rows until the
# next POST /api/v1/scripts/sync re-points them (no CheckConstraint on the
# column, so no migration is needed).
LEGACY_SCRIPT_LOCATIONS = ("main", "central", "profile")


class CronScript(Base, TimestampMixin):
    """One registered script in the Hermes ecosystem.

    `location` is the owning profile's name (e.g. 'athos' --
    /profiles/<profile>/scripts is the only place the hermes scheduler
    executes scripts from; legacy rows may still carry the values in
    LEGACY_SCRIPT_LOCATIONS until the next sync). `name` is the bare
    filename (unique across the full catalog). `path` is the container-side
    absolute path used by the content-read endpoint.
    """

    __tablename__ = "cron_scripts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    location: Mapped[str] = mapped_column(String(50), nullable=False, default="main")
    agent: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    executable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Runtime health fields — updated by sync
    exists_on_disk: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_symlink: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    symlink_target: Mapped[str | None] = mapped_column(String(512), nullable=True)

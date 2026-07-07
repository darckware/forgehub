"""Tool-versions domain models: tool_version_status, tool_sync_setting.

Backs the Dashboard's tool-version card (Hermes/Claude/Codex/Antigravity/
PI/Opencode CLIs, plus the Kanboard container). The actual version checks
and update commands run on the HOST via the chat bridge (host-bridge/
app.py's /v1/tool-versions endpoints, same reasoning as the chat/terminal
domains -- the backend container has no access to those CLIs, nor to the
docker CLI that the Kanboard check needs); this module only persists the
last-known result per tool and the on/off state of the periodic background
poll, so the Dashboard has something to render without round-tripping to
the host on every page load.

Conventions: same as every other domain (UUID PK with Python-side default,
TimestampMixin for created_at/updated_at).
"""
import uuid

from sqlalchemy import Boolean, CheckConstraint, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

# Fixed set of tools this card monitors -- not user-configurable, so a plain
# CheckConstraint (not a separate lookup table) is enough. All but kanboard
# are host CLIs; kanboard is the Docker container from
# /root/.hermes/kanboard/docker-compose.yml (see host-bridge/app.py).
MONITORED_TOOLS = ("hermes", "claude", "codex", "antigravity", "pi", "opencode", "kanboard")


class ToolVersionStatus(Base, TimestampMixin):
    """Last-known version/update-available result for one monitored CLI."""

    __tablename__ = "tool_version_status"
    __table_args__ = (
        # Written as a literal SQL string, not derived from MONITORED_TOOLS
        # via f-string/repr, per every other domain model's CheckConstraint
        # convention (see db/models/product.py).
        CheckConstraint(
            "tool IN ('hermes', 'claude', 'codex', 'antigravity', 'pi', 'opencode', 'kanboard')",
            name="ck_tool_version_status_tool",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tool: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    installed_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    latest_version: Mapped[str | None] = mapped_column(String(255), nullable=True)
    update_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


# Fixed id for the single tool_sync_setting row -- lets get_or_create use the
# primary key's own uniqueness to resolve a concurrent first-create race
# (two callers attempting to insert the same id -> one succeeds, the other
# gets an IntegrityError and re-selects) instead of a random uuid4 letting
# two "singleton" rows slip in side by side.
SYNC_SETTING_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class ToolSyncSetting(Base, TimestampMixin):
    """Singleton row: whether the periodic background version-check poll is
    enabled. A single row is created lazily on first read/write rather than
    via a migration seed, same as any other "settings" singleton would be."""

    __tablename__ = "tool_sync_setting"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=lambda: SYNC_SETTING_ID)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

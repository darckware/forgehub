"""MCP server catalog: register a server once, assign it to agents/projects
from one place, instead of retyping the same command/args/env into every
agent's own config file by hand (the per-agent editor, `core/agent_mcp.py`
+ `/mcp`, still exists and is unchanged -- this is a layer on top of it, not
a replacement).

`McpCatalogServer` is the reusable definition. `McpCatalogAssignment` records
where it's actually been applied -- polymorphic target (agent or project),
same (entity_type, entity_id)-without-a-real-FK shape as
`governance.Approval`/`AuditEvent`, since a catalog server can be assigned to
either kind of target and neither shares a table with the other.

`apply_to_all_agents=True` on a server means "every eligible agent, including
ones registered later" -- applied immediately to every agent whose runtime
supports MCP today, and re-applied automatically whenever a new agent is
created or an existing one's runtime_type is filled in for the first time
(see api/routes/agent.py's create route and core/agent_runtime_sync.py's
plan_for_agent). "Eligible" mirrors api/routes/agent.py's
`_require_mcp_target` -- a runtime with no MCP format, or an agent with no
resolvable home path, is skipped, not errored.

The actual per-target file write still goes through the same engine as
everything else that touches these files: `core/agent_mcp.write_server` for
an agent target, `core/project_mcp.write_server` for a project target (both
now backed by the shared `core/mcp_config_io.py`).
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

MCP_CATALOG_ASSIGNMENT_TARGET_TYPES = ("agent", "project")


class McpCatalogServer(Base, TimestampMixin):
    """One reusable MCP server definition -- cadastro único (name/description/
    command/args/env/url), assigned to zero or more agents/projects via
    McpCatalogAssignment below."""

    __tablename__ = "mcp_catalog_servers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    transport: Mapped[str] = mapped_column(String(10), nullable=False, default="stdio")
    command: Mapped[str | None] = mapped_column(String(500), nullable=True)
    args: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    env: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Marks a server as "known" (part of the built-in seed of popular MCP
    # servers -- Notion, Google Drive, GitHub, ...) vs. one the operator
    # created themselves. Seed rows can be edited/deleted like any other --
    # this is a display hint (e.g. a badge), not a protection flag.
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    apply_to_all_agents: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    __table_args__ = (
        CheckConstraint("transport IN ('stdio', 'http')", name="ck_mcp_catalog_servers_transport"),
    )


class McpCatalogAssignment(Base, TimestampMixin):
    """One (catalog server, target) pairing -- the actual "installed on X"
    record. `last_synced_at`/`last_sync_error` mirror
    `ProjectForgeRouterConfig.configured_at`'s role: the DB row is desired
    state, these two fields are the last-known outcome of trying to make the
    real file match it."""

    __tablename__ = "mcp_catalog_assignments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    catalog_server_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.mcp_catalog_servers.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            f"target_type IN {MCP_CATALOG_ASSIGNMENT_TARGET_TYPES!r}",
            name="ck_mcp_catalog_assignments_target_type",
        ),
        UniqueConstraint(
            "catalog_server_id", "target_type", "target_id", name="uq_mcp_catalog_assignments_target"
        ),
    )

"""Project-scoped MCP server configuration -- the code/dev-tool counterpart
of the Product-scoped background testing in `web_automation.py`.

Unlike per-agent MCP (`core/agent_mcp.py`, which keeps no ForgeHub copy of the
config -- it edits the runtime's own file directly), a project has no single
"runtime" the way an agent does, and not every runtime even has a
project-local MCP mechanism to point at (confirmed 2026-07-28: Claude Code's
`.mcp.json` at the project root is the only one -- Codex's own CLI only
manages a global `~/.codex/config.toml`, and Hermes/agy/OpenClaw have no
project-local config file at all). So this DB row is the durable "desired
state" (mirroring `ProjectForgeRouterConfig`'s same reasoning), and
`last_synced_at`/`last_sync_error` record the outcome of the last attempt to
make the real `.mcp.json` match it -- the file itself, resolved via
`core/project_mcp.py`, stays the source of truth for what a Claude Code
session in that project actually loads.

`runtime_type` is a column (not hardcoded) so a second runtime can be added
later without a schema change, once its own project-local mechanism is
confirmed live -- never assumed from documentation alone.
"""
import uuid

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from app.db.base import Base, TimestampMixin
from app.core.mcp_config_io import SERVER_NAME_RE  # noqa: F401 -- re-exported for the route layer

# Only Claude Code has a confirmed project-local MCP mechanism (.mcp.json).
# Extend only after confirming a runtime's own CLI genuinely reads a
# project-local MCP file -- see this module's docstring.
PROJECT_MCP_RUNTIME_TYPES = ("claude",)


class ProjectMcpServer(Base, TimestampMixin):
    __tablename__ = "project_mcp_servers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.projects.id", ondelete="CASCADE"), nullable=False
    )
    runtime_type: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    transport: Mapped[str] = mapped_column(String(10), nullable=False, default="stdio")
    command: Mapped[str | None] = mapped_column(String(500), nullable=True)
    args: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    env: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        # Built as a joined list rather than `{tuple!r}` -- a single-element
        # tuple's Python repr ("('claude',)") carries a trailing comma that
        # is invalid inside a SQL IN(...) list.
        CheckConstraint(
            "runtime_type IN (" + ", ".join(f"'{v}'" for v in PROJECT_MCP_RUNTIME_TYPES) + ")",
            name="ck_project_mcp_servers_runtime_type",
        ),
        UniqueConstraint("project_id", "runtime_type", "name", name="uq_project_mcp_servers_target"),
    )

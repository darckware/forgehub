"""Pydantic schemas for project-scoped MCP servers (Claude Code's
`.mcp.json` today -- see `db/models/project_mcp.py`'s module docstring for
why other runtimes aren't supported yet).

Field shape deliberately mirrors `schemas/agent.py`'s
`AgentMcpServerOut`/`AgentMcpServerIn` -- same concept (name/command/args/
env/url/enabled), different target (a project's working directory instead
of an agent's home)."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectMcpServerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    runtime_type: str
    name: str
    transport: str
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    enabled: bool = True
    last_synced_at: datetime | None = None
    last_sync_error: str | None = None
    created_at: datetime
    updated_at: datetime


class ProjectMcpServerIn(BaseModel):
    """Upsert payload. Either `command` (stdio) or `url` (HTTP), not both --
    same rule as the per-agent upsert."""

    runtime_type: str = "claude"
    transport: str = "stdio"
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    enabled: bool = True


class ProjectMcpServerLiveEntry(BaseModel):
    name: str
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None


class ProjectMcpServersLiveOut(BaseModel):
    """Live filesystem read of a project's `.mcp.json`, independent of the
    DB-stored ProjectMcpServer rows -- mirrors
    ProjectForgeRouterStatusOut's disk-truth role."""

    project_path: str
    config_path: str
    config_exists: bool
    servers: list[ProjectMcpServerLiveEntry] = Field(default_factory=list)

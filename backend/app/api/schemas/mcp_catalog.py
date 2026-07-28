"""Pydantic schemas for the MCP catalog (db/models/mcp_catalog.py) --
register a server once, assign it to agents/projects from one place."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class McpCatalogServerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None = None
    transport: str
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    is_builtin: bool = False
    apply_to_all_agents: bool = False
    created_at: datetime
    updated_at: datetime


class McpCatalogServerIn(BaseModel):
    name: str
    description: str | None = None
    transport: str = "stdio"
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    apply_to_all_agents: bool = False


class McpCatalogAssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    catalog_server_id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    enabled: bool
    last_synced_at: datetime | None = None
    last_sync_error: str | None = None


class McpCatalogAssignIn(BaseModel):
    target_type: str
    target_id: uuid.UUID
    # Only meaningful (and required) for target_type="project" -- an agent's
    # own runtime_type is used instead. Defaults to "claude" since that is
    # the only project-scoped runtime supported today (see
    # db/models/project_mcp.py).
    runtime_type: str = "claude"

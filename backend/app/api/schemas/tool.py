"""Pydantic schemas for the Tool domain (agent-built tool registry)."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ToolCreate(BaseModel):
    agent_id: uuid.UUID
    name: str = Field(min_length=1, max_length=150)
    description: str = Field(min_length=1)
    file_path: str = Field(min_length=1)
    category: str = Field(default="general", min_length=1, max_length=100)
    status: str = Field(default="active", max_length=20)


class ToolUpdate(BaseModel):
    agent_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = Field(default=None, min_length=1)
    file_path: str | None = Field(default=None, min_length=1)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    status: str | None = Field(default=None, max_length=20)


class ToolScanOut(BaseModel):
    """Result of POST /api/v1/tools/scan."""

    scanned: int
    created: int
    skipped: int


class ToolContentIn(BaseModel):
    """Body of PUT /api/v1/tools/{id}/content."""

    content: str


class ToolContentOut(BaseModel):
    """File content of a tool; content is None when the file is missing."""

    file_path: str
    content: str | None
    exists: bool


class ToolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    # Convenience for list/table views — resolved via join in the routes,
    # not stored on the row.
    agent_name: str | None = None
    name: str
    description: str
    file_path: str
    category: str
    status: str
    created_at: datetime
    updated_at: datetime

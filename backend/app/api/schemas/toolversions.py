"""Pydantic schemas for the tool-versions domain (Dashboard CLI version card)."""
import uuid
from datetime import datetime

from pydantic import BaseModel


class ToolVersionOut(BaseModel):
    id: uuid.UUID
    tool: str
    installed_version: str | None
    latest_version: str | None
    update_available: bool
    last_error: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ToolUpdateResult(BaseModel):
    """Returned by POST .../{tool}/update -- the raw outcome of running the
    real update command on the host, plus the tool's refreshed status row."""

    success: bool
    output: str
    error: str | None
    status: ToolVersionOut


class ToolInstallResult(BaseModel):
    """Returned by POST .../{tool}/install -- the raw outcome of running the
    real install command on the host, plus the tool's refreshed status row."""

    success: bool
    output: str
    error: str | None
    status: ToolVersionOut


class ToolSyncSettingOut(BaseModel):
    enabled: bool


class ToolSyncSettingUpdate(BaseModel):
    enabled: bool

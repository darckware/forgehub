"""Temporary direct remote access: the admin's opening and the agent's command."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.schemas.host_execution import MAX_TARGETS, ExecShell


class DirectAccessOpen(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: uuid.UUID
    server_ids: list[uuid.UUID] = Field(default_factory=list, max_length=MAX_TARGETS)
    group_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    reason: str = Field(min_length=5, max_length=2000)
    purpose: Literal["development", "support"]
    duration_hours: Literal[1, 4, 24]
    allow_elevation: bool = False
    confirm_sensitive: bool = False

    @field_validator("reason")
    @classmethod
    def reason_has_text(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 5:
            raise ValueError("A reason is required")
        return value


class DirectAccessMachine(BaseModel):
    id: uuid.UUID
    name: str
    sensitive: bool


class DirectAccessOut(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    agent_name: str
    purpose: str
    allow_elevation: bool
    reason: str | None
    machines: list[DirectAccessMachine]
    granted_by: str | None
    opened_at: datetime
    expires_at: datetime


class DirectAccessClosed(BaseModel):
    id: uuid.UUID
    closed_at: datetime
    # Machines still running a command of this access when it closed.
    running_commands: int
    notice: str


class DirectCommandCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    server_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_TARGETS)
    command: str = Field(min_length=1, max_length=100_000)
    reason: str = Field(min_length=5, max_length=2000)
    message_number: int = Field(ge=1)
    shell: ExecShell = "sh"
    timeout_seconds: int = Field(default=120, ge=5, le=1800)

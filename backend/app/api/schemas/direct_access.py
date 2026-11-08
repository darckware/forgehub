"""Temporary direct remote access: the admin's opening and the agent's command."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.schemas.host_execution import MAX_TARGETS, ExecShell


class DirectAgentConfigure(BaseModel):
    """Human-confirmed configuration. Groups are resolved to a machine snapshot."""
    model_config = ConfigDict(extra="forbid")

    all_machines: bool = True
    server_ids: list[uuid.UUID] = Field(default_factory=list, max_length=MAX_TARGETS)
    group_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    reason: str | None = Field(default=None, max_length=2000)
    purpose: Literal["development", "support"] | None = None
    duration_hours: Literal[0, 1, 4, 24] = 0
    allow_elevation: bool = False
    confirm_sensitive: bool = False

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str | None) -> str | None:
        return (value or "").strip() or None


class DirectAccessMachine(BaseModel):
    id: uuid.UUID
    name: str
    sensitive: bool


class DirectAccessOut(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    agent_name: str
    purpose: str | None
    allow_elevation: bool
    reason: str | None
    machines: list[DirectAccessMachine]
    granted_by: str | None
    opened_at: datetime
    expires_at: datetime | None
    open_ended: bool
    all_machines: bool
    duration_hours: Literal[0, 1, 4, 24]


class DirectAccessClosed(BaseModel):
    id: uuid.UUID
    closed_at: datetime
    # Machines still running a command of this access when it closed.
    running_commands: int
    notice: str


class DirectAgentOut(BaseModel):
    id: uuid.UUID
    name: str
    runtime_type: str | None
    allowed: bool
    # Why it can't use a direct access: a code the screen words. None = it can.
    unsupported_reason: str | None
    configuration: DirectAccessOut | None = None


class DirectAgentRemoved(BaseModel):
    agent_id: uuid.UUID
    closed_accesses: int
    # Machines still running a command of the closed accesses.
    running_commands: int
    notice: str


class AgentAccessControlOut(BaseModel):
    paused: bool
    paused_at: datetime | None
    paused_by: str | None
    reason: str | None


class AgentAccessPause(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=2000)


class DirectCommandCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    server_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_TARGETS)
    command: str = Field(min_length=1, max_length=100_000)
    reason: str = Field(min_length=5, max_length=2000)
    message_number: int = Field(ge=1)
    shell: ExecShell = "sh"
    timeout_seconds: int = Field(default=120, ge=5, le=1800)

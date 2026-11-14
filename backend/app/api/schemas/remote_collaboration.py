"""Collaborative execution in an active session with Marcelo (inactive by default)."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.schemas.host_execution import MAX_TARGETS, ExecShell


def _not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


class CollaborationSessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: uuid.UUID
    message_number: int = Field(ge=1)
    server_id: uuid.UUID
    operation: str = Field(min_length=1, max_length=2000)
    allow_elevation: bool = False
    duration_minutes: int = Field(default=60, ge=1, le=240)

    @field_validator("operation")
    @classmethod
    def clean_operation(cls, value: str) -> str:
        return _not_blank(value).strip()


class CollaborationCommandCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Stored byte for byte: the agent must send exactly this text.
    command: str = Field(min_length=1, max_length=100_000)
    shell: ExecShell = "sh"
    allow_elevation: bool = False

    @field_validator("command")
    @classmethod
    def command_not_blank(cls, value: str) -> str:
        return _not_blank(value)


class CollaborationEnd(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=2000)


class CollaborativeCommandRun(BaseModel):
    """The agent's request: one authorized command, sent back exactly as authorized."""
    model_config = ConfigDict(extra="forbid")

    session_id: uuid.UUID
    command_id: uuid.UUID
    command: str = Field(min_length=1, max_length=100_000)
    shell: ExecShell = "sh"
    timeout_seconds: int = Field(default=120, ge=5, le=1800)
    message_number: int = Field(ge=1)
    # Must be exactly the session's machine; checked by the validator (COLLABORATION_MACHINE_MISMATCH).
    server_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_TARGETS)
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str) -> str:
        return _not_blank(value).strip()


class CollaborationCommandOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    command: str
    shell: str
    command_sha256: str
    allow_elevation: bool
    status: str
    authorized_by: str
    created_at: datetime
    used_at: datetime | None = None
    execution_id: uuid.UUID | None = None


class CollaborationSessionOut(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    agent_name: str | None
    message_number: int | None
    agent_run_id: str
    server_id: uuid.UUID | None
    server_name: str | None
    operation: str
    allow_elevation: bool
    status: str
    expires_at: datetime
    created_at: datetime
    ended_at: datetime | None = None
    ended_by: str | None = None
    end_reason: str | None = None
    commands: list[CollaborationCommandOut] = Field(default_factory=list)
    # "active" only when the validator would still accept it; "inactive" for a
    # session recorded active that can no longer be used (see dead_reason).
    effective_status: str
    dead_reason: str | None = None

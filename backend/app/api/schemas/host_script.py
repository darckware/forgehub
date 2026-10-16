"""Schemas for the script library and schedules (Remote Access plan step 1)."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Platform = Literal["windows", "linux", "macos"]
Risk = Literal["read", "change", "destructive"]


class ScriptParameter(BaseModel):
    name: str = Field(min_length=1, max_length=41)
    label: str | None = Field(default=None, max_length=120)
    required: bool = False
    default: str | None = None
    # Masked in stored command/output.
    secret: bool = False


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    label: str
    description: str | None


class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=2, max_length=120)
    description: str | None = None


class ScriptCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=160)
    category_id: uuid.UUID
    description: str | None = None
    platform: Platform
    risk: Risk = "read"
    timeout_seconds: int = Field(default=300, ge=5, le=1800)
    parameters: list[ScriptParameter] = Field(default_factory=list, max_length=30)
    content: str = Field(min_length=1, max_length=100_000)


class ScriptUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=160)
    category_id: uuid.UUID | None = None
    description: str | None = None
    risk: Risk | None = None
    timeout_seconds: int | None = Field(default=None, ge=5, le=1800)
    parameters: list[ScriptParameter] | None = Field(default=None, max_length=30)
    content: str | None = Field(default=None, min_length=1, max_length=100_000)
    # Why this version changed (stored on the new version).
    note: str | None = Field(default=None, max_length=500)


class ScriptVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version: int
    content: str
    parameters: list
    changed_by: str
    note: str | None
    created_at: datetime


class ScriptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    category_id: uuid.UUID
    description: str | None
    platform: Platform
    risk: Risk
    timeout_seconds: int
    parameters: list
    content: str
    current_version: int
    is_system: bool
    system_key: str | None = None
    archived: bool
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime


class ScriptDetail(ScriptOut):
    versions: list[ScriptVersionOut] = Field(default_factory=list)


class ScheduleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=160)
    script_id: uuid.UUID
    parameter_values: dict[str, str | None] = Field(default_factory=dict)
    server_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)
    group_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    kind: Literal["once", "weekly"]
    run_at: datetime | None = None
    weekdays: list[int] | None = None
    time_of_day: str | None = None
    timezone: str = "America/Sao_Paulo"
    window_minutes: int = Field(default=120, ge=5, le=24 * 60)


class ScheduleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=160)
    parameter_values: dict[str, str | None] | None = None
    server_ids: list[uuid.UUID] | None = Field(default=None, max_length=200)
    group_ids: list[uuid.UUID] | None = Field(default=None, max_length=50)
    kind: Literal["once", "weekly"] | None = None
    run_at: datetime | None = None
    weekdays: list[int] | None = None
    time_of_day: str | None = None
    timezone: str | None = None
    window_minutes: int | None = Field(default=None, ge=5, le=24 * 60)
    enabled: bool | None = None


class ScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    script_id: uuid.UUID
    script_name: str | None = None
    parameter_values: dict
    server_ids: list
    group_ids: list
    kind: Literal["once", "weekly"]
    run_at: datetime | None
    weekdays: list | None
    time_of_day: str | None
    timezone: str
    window_minutes: int
    enabled: bool
    next_run_at: datetime | None
    last_run_at: datetime | None
    last_execution_id: uuid.UUID | None
    created_by: str
    agent_id: uuid.UUID | None
    created_at: datetime


class ScriptRenderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parameter_values: dict[str, str | None] = Field(default_factory=dict)


class ScriptRendered(BaseModel):
    script_id: uuid.UUID
    version: int
    shell: Literal["sh", "powershell"]
    script: str

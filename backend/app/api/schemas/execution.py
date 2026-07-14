"""Contracts for governed execution waves and durable CLI runs."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ExecutionWaveCreate(BaseModel):
    baseline_id: uuid.UUID
    pipeline_stage_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=200)
    task_ids: list[uuid.UUID] = Field(min_length=1)
    wip_limit: int = Field(default=1, ge=1, le=50)
    budget_limit: float | None = Field(default=None, ge=0)
    expires_at: datetime | None = None
    idempotency_key: str = Field(min_length=8, max_length=255)


class WaveTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    task_id: uuid.UUID
    release_order: int
    released_at: datetime | None


class ExecutionWaveOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    project_id: uuid.UUID
    baseline_id: uuid.UUID
    pipeline_stage_id: uuid.UUID | None
    name: str
    status: str
    wip_limit: int
    budget_limit: float | None
    preflight_snapshot: dict | None
    preflight_hash: str | None
    starts_at: datetime | None
    expires_at: datetime | None
    paused_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class WaveDetailOut(ExecutionWaveOut):
    tasks: list[WaveTaskOut]


class WavePreflightOut(BaseModel):
    wave_id: uuid.UUID
    eligible: bool
    input_hash: str
    tasks: list[dict]


class WorkPackageCreate(BaseModel):
    assignment_id: uuid.UUID
    runtime_profile_id: uuid.UUID
    allowed_paths: list[str] = Field(default_factory=list)
    denied_paths: list[str] = Field(default_factory=lambda: [".env", ".git"])
    verification_commands: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    definition_of_done: list[str] = Field(default_factory=list)
    input_artifact_ids: list[uuid.UUID] = Field(default_factory=list)
    prompt_addendum: str | None = Field(default=None, max_length=4000)
    max_seconds: int = Field(default=1800, ge=30, le=7200)
    idempotency_key: str = Field(min_length=8, max_length=255)


class WorkPackageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    task_id: uuid.UUID
    assignment_id: uuid.UUID
    runtime_profile_id: uuid.UUID
    execution_wave_id: uuid.UUID
    baseline_id: uuid.UUID
    revision: int
    contract_version: str
    payload: dict
    payload_hash: str
    status: str
    validation_errors: list
    issued_at: datetime | None
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


class DispatchOut(BaseModel):
    execution_id: uuid.UUID
    work_package_id: uuid.UUID
    lease_id: uuid.UUID
    run_id: str
    status: str
    runtime_type: str


class ReworkCreate(BaseModel):
    feedback: str = Field(min_length=1, max_length=10000)
    idempotency_key: str = Field(min_length=8, max_length=255)


class ExecutionEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    task_execution_id: uuid.UUID
    sequence: int
    event_type: str
    occurred_at: datetime
    payload: dict


class ExecutionRuntimeOut(BaseModel):
    execution_id: uuid.UUID
    status: str
    run: dict
    result: dict | None = None


class RunnerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    runner_key: str
    status: str
    adapter_version: str | None
    capabilities: dict
    last_heartbeat_at: datetime | None
    disabled: bool

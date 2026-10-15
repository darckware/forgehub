"""Pydantic schemas for command executions on machines (Remote Access phase 4)."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ExecShell = Literal["sh", "powershell"]

MAX_TARGETS = 200


class HostExecutionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: str = Field(min_length=1, max_length=100_000)
    shell: ExecShell
    server_ids: list[uuid.UUID] = Field(default_factory=list, max_length=MAX_TARGETS)
    group_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    timeout_seconds: int = Field(default=300, ge=5, le=1800)


class HostExecutionFollowUp(BaseModel):
    """Run another command on the machines where the parent failed."""

    model_config = ConfigDict(extra="forbid")

    command: str = Field(min_length=1, max_length=100_000)
    shell: ExecShell
    timeout_seconds: int = Field(default=300, ge=5, le=1800)


class HostExecutionResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    server_id: uuid.UUID | None
    server_name: str
    status: Literal["pending", "running", "succeeded", "failed", "skipped"]
    failure: str | None
    skip_reason: str | None
    exit_code: int | None
    stdout: str | None
    stderr: str | None
    truncated: bool
    duration_ms: int | None
    started_at: datetime | None
    finished_at: datetime | None


class HostExecutionCounts(BaseModel):
    total: int = 0
    pending: int = 0
    running: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0


class HostExecutionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    parent_execution_id: uuid.UUID | None
    shell: str
    command: str
    timeout_seconds: int
    status: Literal["running", "completed", "cancelled"]
    requested_by: str
    target_summary: str | None
    started_at: datetime
    finished_at: datetime | None
    counts: HostExecutionCounts = Field(default_factory=HostExecutionCounts)
    # "succeeded" only when every machine that ran succeeded and nothing is
    # still pending; "failed" as soon as any machine failed.
    verdict: Literal["running", "succeeded", "failed", "nothing_ran"] = "running"


class HostExecutionDetail(HostExecutionSummary):
    results: list[HostExecutionResultOut] = Field(default_factory=list)
    follow_up_ids: list[uuid.UUID] = Field(default_factory=list)

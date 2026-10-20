"""Pydantic schemas for command executions on machines (Remote Access phase 4)."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ExecShell = Literal["sh", "powershell"]

MAX_TARGETS = 200


class HostExecutionCreate(BaseModel):
    """Either a library script (`script_id` + `parameter_values`) or an ad-hoc
    `command` + `shell`."""

    model_config = ConfigDict(extra="forbid")

    script_id: uuid.UUID | None = None
    parameter_values: dict[str, str | None] = Field(default_factory=dict)
    command: str | None = Field(default=None, min_length=1, max_length=100_000)
    shell: ExecShell | None = None
    server_ids: list[uuid.UUID] = Field(default_factory=list, max_length=MAX_TARGETS)
    group_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    timeout_seconds: int = Field(default=300, ge=5, le=1800)
    # A login for the machines ForgeHub has no access to yet (no SSH login of
    # its own there): used for this run only, never stored, masked in output.
    login_user: str | None = Field(default=None, min_length=1, max_length=100)
    login_password: str | None = Field(default=None, min_length=1, max_length=256, repr=False)
    # Maintenance record: why it runs and the client ticket/demand it serves.
    reason: str | None = Field(default=None, max_length=2000)
    darckware_item_kind: Literal["ticket", "demand"] | None = None
    darckware_item_id: str | None = Field(default=None, min_length=1, max_length=64)


class HostExecutionFollowUp(BaseModel):
    """Run a library script or another command on the machines where the
    parent failed."""

    model_config = ConfigDict(extra="forbid")

    script_id: uuid.UUID | None = None
    parameter_values: dict[str, str | None] = Field(default_factory=dict)
    command: str | None = Field(default=None, min_length=1, max_length=100_000)
    shell: ExecShell | None = None
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
    trigger: Literal["manual", "schedule", "agent"] = "manual"
    agent_id: uuid.UUID | None = None
    agent_name: str | None = None
    schedule_id: uuid.UUID | None = None
    script_id: uuid.UUID | None = None
    script_name: str | None = None
    script_version: int | None = None
    retry_until: datetime | None = None
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
    reason: str | None = None
    darckware_item_kind: str | None = None
    darckware_item_id: str | None = None
    agent_demand_id: uuid.UUID | None = None


class HostExecutionDetail(HostExecutionSummary):
    results: list[HostExecutionResultOut] = Field(default_factory=list)
    follow_up_ids: list[uuid.UUID] = Field(default_factory=list)


class AgentExecutionCreate(BaseModel):
    """An agent's maintenance run (MCP): a library script only, on machines
    ForgeHub already has its own login on, always with the reason."""

    model_config = ConfigDict(extra="forbid")

    script_id: uuid.UUID
    parameter_values: dict[str, str | None] = Field(default_factory=dict)
    server_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_TARGETS)
    reason: str = Field(min_length=5, max_length=2000)
    # The Messages task (its #number) this run answers. Required for agents:
    # the run must fit what that task allowed (machines, scripts).
    message_number: int | None = Field(default=None, ge=1)
    darckware_item_kind: Literal["ticket", "demand"] | None = None
    darckware_item_id: str | None = Field(default=None, min_length=1, max_length=64)


class AgentMachineOut(BaseModel):
    id: uuid.UUID
    name: str
    kind: str
    os_family: str | None
    darckware_client_name: str | None
    location: str | None
    # Whether ForgeHub can run a script there now (its own SSH login works).
    runnable: bool
    status: str


class AgentScriptOut(BaseModel):
    id: uuid.UUID
    name: str
    category: str | None
    platform: str
    risk: str
    description: str | None
    parameters: list


class AgentRequestScript(BaseModel):
    model_config = ConfigDict(extra="forbid")

    script_id: uuid.UUID
    parameter_values: dict[str, str | None] = Field(default_factory=dict)


class AgentRequestCreate(BaseModel):
    """"Pedir ao agente" (2026-10-19): a maintenance task for one or more
    authorized agents on chosen machines -- one Messages task per agent."""

    model_config = ConfigDict(extra="forbid")

    agent_ids: list[uuid.UUID] = Field(min_length=1, max_length=10)
    server_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_TARGETS)
    instruction: str = Field(min_length=5, max_length=8000)
    # When given, the agent is told to run only these, with these values.
    scripts: list[AgentRequestScript] = Field(default_factory=list, max_length=10)
    darckware_item_kind: Literal["ticket", "demand"] | None = None
    darckware_item_id: str | None = Field(default=None, min_length=1, max_length=64)


class AgentRequestOut(BaseModel):
    agent_id: uuid.UUID
    agent_name: str
    demand_id: uuid.UUID
    demand_number: int | None = None

"""Versioned API contracts for the Agent Activity operational read model.

These DTOs deliberately carry only scalar, UUID, timestamp, and explicitly
typed nested data.  Aggregation may read canonical ORM records, but ORM
objects themselves never cross this API boundary.
"""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ActivityRecordLinkOut(BaseModel):
    """A stable link back to one canonical ForgeHub record."""

    source_type: str
    source_id: uuid.UUID
    canonical_path: str
    label: str | None = None


class ActivityCheckpointOut(BaseModel):
    """The most recent recoverable progress checkpoint for an execution."""

    id: uuid.UUID
    execution_id: uuid.UUID
    occurred_at: datetime
    status: str
    resume_from_step_key: str | None = None
    summary: str | None = None
    evidence_summary: str | None = None
    verification_summary: str | None = None
    error_code: str | None = None
    blocker_code: str | None = None
    canonical_path: str


class ActivityProfileSummaryOut(BaseModel):
    """Safe profile-health metadata; never profile or memory contents."""

    status: Literal["healthy", "warning", "error", "unavailable"]
    checked_at: datetime
    runtime_native: bool
    canonical_path: str
    profile_path: str | None = None
    last_heartbeat_at: datetime | None = None
    issues: list[str] = Field(default_factory=list)


class ActivityCurrentWorkOut(BaseModel):
    """Canonical project, task, and execution context currently owned by an agent."""

    project_id: uuid.UUID | None = None
    project_name: str | None = None
    project_path: str | None = None
    task_id: uuid.UUID | None = None
    task_title: str | None = None
    task_path: str | None = None
    assignment_id: uuid.UUID | None = None
    work_package_id: uuid.UUID | None = None
    execution_id: uuid.UUID | None = None
    execution_path: str | None = None
    action: str | None = None
    branch: str | None = None
    working_directory_path: str | None = None
    requested_by_agent_id: uuid.UUID | None = None
    source_message_id: uuid.UUID | None = None
    source_message_path: str | None = None


class ActivityAgentOut(BaseModel):
    """One agent node and its currently authoritative operational context."""

    id: uuid.UUID
    name: str
    profile_slug: str | None = None
    runtime_type: str
    availability: Literal["available", "busy", "degraded", "unavailable", "unknown"]
    availability_reason: str | None = None
    last_heartbeat_at: datetime | None = None
    canonical_path: str
    current_work: ActivityCurrentWorkOut | None = None
    latest_checkpoint: ActivityCheckpointOut | None = None
    profile_summary: ActivityProfileSummaryOut

    @property
    def current_execution_id(self) -> uuid.UUID | None:
        """Compatibility accessor for aggregation consumers; API JSON uses current_work."""
        return self.current_work.execution_id if self.current_work else None


class ActivityMessageEdgeOut(BaseModel):
    """A directed edge from one canonical Messages record."""

    message_id: uuid.UUID
    from_agent_id: uuid.UUID | None = None
    from_agent_name: str | None = None
    target_agent_id: uuid.UUID | None = None
    target_agent_name: str | None = None
    reply_to_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    subject: str | None = None
    dispatch_status: str
    requires_response: bool = False
    response_status: str | None = None
    waiting_for_response: bool = False
    waiting_on_agent_id: uuid.UUID | None = None
    sent_at: datetime
    updated_at: datetime
    responded_at: datetime | None = None
    canonical_path: str


class ActivityIncidentOut(BaseModel):
    """An operational concern derived from a canonical source record."""

    key: str
    kind: Literal[
        "execution_failed",
        "heartbeat_lost",
        "runtime_limit",
        "blocked",
        "approval_pending",
        "source_unavailable",
    ]
    severity: Literal["info", "warning", "error", "critical"]
    title: str
    occurred_at: datetime
    source_type: str
    source_id: uuid.UUID
    affected_agent_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    execution_id: uuid.UUID | None = None
    checkpoint_id: uuid.UUID | None = None
    resume_from_step_key: str | None = None
    error_code: str | None = None
    blocker_code: str | None = None
    summary: str | None = None
    recommended_action: Literal[
        "request_athos_monitoring",
        "open_approval",
        "open_message",
        "inspect_execution",
    ]
    prior_attempts: list[dict[str, Any]] = Field(default_factory=list)
    last_observed_at: datetime | None = None
    impact: str | None = None
    runtime_type: str | None = None
    provider: str | None = None
    current_owner_agent_id: uuid.UUID | None = None
    canonical_path: str | None = None
    related_records: list[ActivityRecordLinkOut] = Field(default_factory=list)


class ActivityTimelineEventOut(BaseModel):
    """A chronological event with a stable key and a canonical source link."""

    key: str
    kind: str
    occurred_at: datetime
    source_type: str
    source_id: uuid.UUID
    title: str
    canonical_path: str
    summary: str | None = None
    agent_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    execution_id: uuid.UUID | None = None
    checkpoint_id: uuid.UUID | None = None
    approval_id: uuid.UUID | None = None
    notification_id: uuid.UUID | None = None
    related_records: list[ActivityRecordLinkOut] = Field(default_factory=list)


class ActivitySourceFreshnessOut(BaseModel):
    """Availability evidence for each source used to assemble the read model."""

    name: str
    status: Literal["fresh", "stale", "unavailable"]
    checked_at: datetime
    observed_at: datetime | None = None
    age_seconds: int | None = Field(default=None, ge=0)
    detail: str | None = None
    error_code: str | None = None


class AgentActivityOut(BaseModel):
    """The versioned, read-only Agent Activity response."""

    contract_version: Literal["forge-agent-activity/v1"] = "forge-agent-activity/v1"
    generated_at: datetime
    project_id: uuid.UUID | None
    agents: list[ActivityAgentOut]
    message_edges: list[ActivityMessageEdgeOut]
    incidents: list[ActivityIncidentOut]
    timeline: list[ActivityTimelineEventOut]
    source_freshness: list[ActivitySourceFreshnessOut]


class RequestAthosMonitoringIn(BaseModel):
    """Body for an idempotent Athos monitoring request for one incident."""

    execution_id: uuid.UUID
    idempotency_key: str = Field(min_length=1, max_length=255)


class RequestAthosMonitoringOut(BaseModel):
    """Canonical Messages/Notifications records created or reused by the command."""

    message_id: uuid.UUID
    message_number: int
    notification_id: uuid.UUID
    created: bool

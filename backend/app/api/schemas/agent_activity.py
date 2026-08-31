"""Versioned API contracts for the Agent Activity operational read model.

These DTOs deliberately carry only scalar, UUID, timestamp, and explicitly
typed nested data.  Aggregation may read canonical ORM records, but ORM
objects themselves never cross this API boundary.
"""

import uuid
from datetime import datetime
from typing import Literal

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


class ActivityContextOut(BaseModel):
    """One canonical Conception or Delivery context projected into operations."""

    context_kind: Literal["conception", "project"]
    context_id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    development_request_id: uuid.UUID | None = None
    concept_id: uuid.UUID | None = None
    concept_revision_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    project_name: str | None = None
    working_directory_path: str | None = None
    title: str
    status: str
    canonical_path: str
    created_at: datetime
    updated_at: datetime


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
    context_kind: Literal["conception", "project"] | None = None
    context_id: uuid.UUID | None = None
    development_request_id: uuid.UUID | None = None
    concept_id: uuid.UUID | None = None
    concept_revision_id: uuid.UUID | None = None


class ActivityAgentOut(BaseModel):
    """One agent node and its currently authoritative operational context."""

    id: uuid.UUID
    name: str
    avatar_data_url: str | None = None
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


class ActivityProjectOut(BaseModel):
    """One canonical project rendered as a topology node."""

    id: uuid.UUID
    name: str
    status: str
    canonical_path: str


class ActivityResourceOut(BaseModel):
    """A configured infrastructure resource used by visible projects."""

    key: str
    kind: Literal["database"]
    label: str
    detail: str | None = None
    status: Literal["available", "degraded", "unavailable"]


class ActivityTopologyRelationOut(BaseModel):
    """A typed, text-labelled relationship between topology objects."""

    key: str
    kind: Literal["current_work", "membership", "persistence"]
    from_type: Literal["agent", "project"]
    from_id: str
    to_type: Literal["project", "resource"]
    to_id: str
    label: str


class ActivityMessageEdgeOut(BaseModel):
    """A directed edge from one canonical Messages record."""

    message_id: uuid.UUID
    from_agent_id: uuid.UUID | None = None
    from_agent_name: str | None = None
    target_agent_id: uuid.UUID | None = None
    target_agent_name: str | None = None
    reply_to_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    development_request_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
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
    factory_context_path: str | None = None


class ActivityPriorAttemptOut(BaseModel):
    """One prior execution attempt linked to the canonical execution record."""

    id: uuid.UUID
    execution_id: uuid.UUID
    attempt_number: int = Field(ge=1)
    started_at: datetime
    completed_at: datetime | None = None
    outcome: str
    error_code: str | None = None
    summary: str | None = None
    canonical_path: str
    related_records: list[ActivityRecordLinkOut] = Field(default_factory=list)


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
    prior_attempts: list[ActivityPriorAttemptOut] = Field(default_factory=list)
    last_observed_at: datetime | None = None
    impact: str | None = None
    runtime_type: str | None = None
    provider: str | None = None
    current_owner_agent_id: uuid.UUID | None = None
    canonical_path: str | None = None
    related_records: list[ActivityRecordLinkOut] = Field(default_factory=list)
    context_kind: Literal["conception", "project"] | None = None
    context_id: uuid.UUID | None = None
    development_request_id: uuid.UUID | None = None
    concept_id: uuid.UUID | None = None
    concept_revision_id: uuid.UUID | None = None


ActivityFlowStage = Literal[
    "incoming",
    "planning",
    "queued",
    "executing",
    "verifying",
    "completed",
    "attention",
    "archived",
]


class ActivityFlowItemOut(BaseModel):
    """One canonical record normalized into the read-only operational flow."""

    key: str
    stage: ActivityFlowStage
    source_type: str
    source_id: uuid.UUID
    source_status: str
    title: str
    occurred_at: datetime
    updated_at: datetime
    canonical_path: str
    agent_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    execution_id: uuid.UUID | None = None
    context_kind: Literal["conception", "project"] | None = None
    context_id: uuid.UUID | None = None
    development_request_id: uuid.UUID | None = None
    concept_id: uuid.UUID | None = None
    concept_revision_id: uuid.UUID | None = None


class ActivityTimelineEventOut(BaseModel):
    """A chronological event with a stable key and a canonical source link."""

    key: str
    kind: str
    occurred_at: datetime
    source_type: str
    source_id: uuid.UUID
    source_status: str
    lane: Literal["communication", "planning", "execution", "checkpoint", "governance"]
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
    context_kind: Literal["conception", "project"] | None = None
    context_id: uuid.UUID | None = None
    development_request_id: uuid.UUID | None = None
    concept_id: uuid.UUID | None = None
    concept_revision_id: uuid.UUID | None = None


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
    contexts: list[ActivityContextOut] = Field(default_factory=list)
    projects: list[ActivityProjectOut] = Field(default_factory=list)
    resources: list[ActivityResourceOut] = Field(default_factory=list)
    topology_relations: list[ActivityTopologyRelationOut] = Field(default_factory=list)
    flow_items: list[ActivityFlowItemOut] = Field(default_factory=list)
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

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


class ActivityLiveStateOut(BaseModel):
    """What the agent is doing right now, from its runtime's own lifecycle events
    (``core/agent_live_state.py``). Metadata only: no message text ever reaches it."""

    state: Literal["executing", "thinking", "conversing", "waiting", "degraded", "idle"]
    since: datetime | None = None
    # runtime = pushed by the agent runtime; workspace = a ForgeHub chat turn;
    # messages = an on-demand external agent running a dispatched message.
    source: Literal["runtime", "workspace", "messages"] | None = None
    platform: str | None = None
    counterpart_kind: Literal["owner", "human", "agent", "system"] | None = None
    counterpart_ref: str | None = None
    model: str | None = None
    tool_name: str | None = None
    session_id: str | None = None
    turn_id: str | None = None
    last_event_at: datetime | None = None
    reason: str | None = None
    message_number: int | None = None
    turns_last_hour: int = 0
    tools_last_hour: int = 0
    failures_last_hour: int = 0
    pending_count: int = 0


class AgentLiveSnapshotItemOut(BaseModel):
    agent_id: uuid.UUID
    live: ActivityLiveStateOut | None = None
    # turn + tool starts per 5-minute bucket over the last hour, oldest first
    spark: list[int]
    tokens_last_hour: int = 0
    cost_today: float = 0.0


class ActivityPulseOut(BaseModel):
    """Page-wide "what is happening now" numbers for the Agent Activity pulse strip."""

    agents_total: int
    agents_reporting: int
    agents_active: int
    agents_in_turn: int
    agents_degraded: int
    turns_last_hour: int
    tools_last_hour: int
    failures_last_hour: int
    pending_total: int
    # None = ForgeRouter unreachable (shown as "—", never as zero)
    llm_calls_last_hour: int | None = None
    tokens_last_hour: int | None = None
    cost_today: float | None = None
    # turn starts per minute over the last hour, oldest first
    turns_per_minute: list[int]


class ActivityLinkOut(BaseModel):
    """One interaction drawn on the constellation: who reached which agent, through what.

    Only real, recent activity (``LINK_WINDOW``) -- never a static "may talk to" relation.
    ``source_type`` owner/human/system are the outer-ring nodes; ``agent`` is another agent
    (a Messages message), identified by ``source_agent_id``.
    """

    key: str
    kind: Literal["conversation", "workspace", "message"]
    source_type: Literal["owner", "human", "system", "agent"]
    source_agent_id: uuid.UUID | None = None
    target_agent_id: uuid.UUID
    channel: str | None = None
    active: bool
    last_at: datetime
    count: int = 1
    message_number: int | None = None


class AgentLiveSnapshotOut(BaseModel):
    """One frame of GET /api/v1/agent-activity/stream (core/agent_activity_stream.py)."""

    generated_at: datetime
    agents: list[AgentLiveSnapshotItemOut]
    pulse: ActivityPulseOut
    links: list[ActivityLinkOut] = []


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
    # None when this agent's runtime has never reported (e.g. not wired yet).
    live: ActivityLiveStateOut | None = None

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
    kind: Literal["database", "platform", "gateway", "vault", "portal", "site"]
    label: str
    detail: str | None = None
    status: Literal["available", "degraded", "unavailable"]


class ActivityTopologyRelationOut(BaseModel):
    """A typed, text-labelled relationship between topology objects."""

    key: str
    kind: Literal[
        "current_work",
        "membership",
        "persistence",
        "transition",
        "orchestration",
        "ai_routing",
        "vault_sync",
        "portal_sync",
    ]
    from_type: Literal["agent", "project", "conception"]
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
        # phase 5 runtime alerts (core/agent_activity_alerts.py)
        "turn_stuck",
        "adapter_fatal",
        "cron_failing",
        "provider_error",
        "usage_anomaly",
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
        "open_agent",
        "open_crons",
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


# --- Phase 4: traceability (lanes, event table, replay) -------------------------------


class TimelineToolOut(BaseModel):
    """One tool call inside a turn, drawn as a tick on the agent's lane."""

    start: datetime
    end: datetime | None = None
    tool_name: str | None = None
    status: str | None = None
    duration_ms: int | None = None


class TimelineBlockOut(BaseModel):
    """A span of work on an agent's lane.

    ``turn`` = a runtime turn (start/end pair pushed by the agent's runtime);
    ``dispatch`` = a Messages dispatch running for the agent; ``workspace`` = a ForgeHub
    Workspace chat turn. ``end`` None means still open at the window's end;
    ``status="abandoned"`` marks a runtime turn that never reported its end within
    ``TURN_STALE_MINUTES`` (its end is then its last known event).
    """

    key: str
    kind: Literal["turn", "dispatch", "workspace"]
    start: datetime
    end: datetime | None = None
    platform: str | None = None
    counterpart_kind: Literal["owner", "human", "agent", "system"] | None = None
    counterpart_ref: str | None = None
    counterpart_agent_id: uuid.UUID | None = None
    model: str | None = None
    status: str | None = None
    error_type: str | None = None
    session_id: str | None = None
    turn_id: str | None = None
    message_number: int | None = None
    tools: list[TimelineToolOut] = []
    canonical_path: str | None = None


class TimelineLaneOut(BaseModel):
    agent_id: uuid.UUID
    blocks: list[TimelineBlockOut]


class TimelineMessageOut(BaseModel):
    """A Messages message between two agents, drawn as an arrow across their lanes."""

    id: uuid.UUID
    number: int | None = None
    at: datetime
    from_agent_id: uuid.UUID
    target_agent_id: uuid.UUID
    subject: str | None = None
    canonical_path: str


class TimelineEventOut(BaseModel):
    """One row of the event table: the raw record behind the lanes."""

    key: str
    occurred_at: datetime
    agent_id: uuid.UUID | None = None
    profile: str | None = None
    source: Literal["runtime", "messages", "workspace"]
    kind: str
    platform: str | None = None
    counterpart_kind: str | None = None
    counterpart_ref: str | None = None
    model: str | None = None
    tool_name: str | None = None
    status: str | None = None
    error_type: str | None = None
    duration_ms: int | None = None
    session_id: str | None = None
    turn_id: str | None = None
    message_number: int | None = None
    canonical_path: str | None = None


class AgentActivityTimelineOut(BaseModel):
    """GET /api/v1/agent-activity/timeline -- everything that happened in a window."""

    start: datetime
    end: datetime
    generated_at: datetime
    lanes: list[TimelineLaneOut]
    messages: list[TimelineMessageOut]
    events: list[TimelineEventOut]
    # True when the event table hit its cap; lanes are still complete.
    truncated: bool = False

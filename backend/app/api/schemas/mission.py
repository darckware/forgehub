"""Pydantic schemas for the Mission domain (M0.0, MCP_MISSION_TOOLS_SPEC.md §2-§3.1)."""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.orchestration import ProjectAgentMembershipOut

from app.db.models.mission import MISSION_RISK_LEVELS, MISSION_STATES, PLANNING_STAGES, REVIEW_LAYERS


class MissionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_version_id: uuid.UUID
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    # M0.2a (§5.1, create_internal_project): the same route also registers a
    # creation/maintenance project (through project.py's build_project) and
    # takes the MCP's idempotency key. Mission-only fields are refused for
    # the other two types.
    project_type: Literal["mission", "maintenance", "creation"] = "mission"
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=150)
    # Required for a mission created by a person; an agent caller defaults to itself.
    orchestrator_agent_id: uuid.UUID | None = None
    priority: int = Field(default=100, ge=1, le=1000)
    # Validated by the route (422 AUTONOMY_LEVEL_NOT_ALLOWED) so the refusal
    # carries the mission error contract rather than a generic schema error.
    autonomy_level: str = "N0"
    brief_artifact_id: uuid.UUID | None = None
    deadline_at: datetime | None = None
    budget_limit: Decimal | None = Field(default=None, ge=0)
    working_directory_path: str | None = Field(default=None, max_length=1024)
    executor_project_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)


class MissionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_row_version: int
    priority: int | None = Field(default=None, ge=1, le=1000)
    autonomy_level: str | None = None
    brief_artifact_id: uuid.UUID | None = None
    deadline_at: datetime | None = None
    budget_limit: Decimal | None = Field(default=None, ge=0)
    risk_level: str | None = Field(default=None, pattern=f"^({'|'.join(MISSION_RISK_LEVELS)})$")
    required_review_layers: list[str] | None = None
    reason: str | None = Field(default=None, max_length=4000)


class MissionTransitionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to: str = Field(pattern=f"^({'|'.join(MISSION_STATES)})$")
    reason: str | None = Field(default=None, max_length=4000)
    expected_row_version: int


class PlanningAdvanceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to: str = Field(pattern=f"^({'|'.join(PLANNING_STAGES)})$")
    reason: str = Field(min_length=1, max_length=4000)
    idempotency_key: str = Field(min_length=1, max_length=150)
    expected_row_version: int | None = None


class MissionOut(BaseModel):
    project_id: uuid.UUID
    name: str
    project_type: str
    project_status: str
    state: str
    paused_from_state: str | None
    planning_stage: str | None
    risk_level: str | None
    required_review_layers: list[str]
    priority: int
    orchestrator_agent_id: uuid.UUID
    autonomy_level: str
    brief_artifact_id: uuid.UUID | None
    current_baseline_id: uuid.UUID | None
    deadline_at: datetime | None
    budget_limit: Decimal | None
    paused_seconds: int
    state_changed_at: datetime
    state_reason: str | None
    row_version: int
    executor_project_ids: list[uuid.UUID]


MISSION_ONLY_CREATE_FIELDS = frozenset({
    "orchestrator_agent_id", "priority", "autonomy_level", "brief_artifact_id", "deadline_at", "budget_limit",
    "executor_project_ids",
})


class InternalProjectOut(BaseModel):
    """POST /api/v1/missions response (§5.1). For a mission it carries every
    MissionOut field too (unchanged M0.0 shape); for creation/maintenance the
    mission fields are null."""

    project_id: uuid.UUID
    name: str
    project_type: str
    project_status: str
    mission_state: str | None = None
    created: bool = True
    state: str | None = None
    paused_from_state: str | None = None
    planning_stage: str | None = None
    risk_level: str | None = None
    required_review_layers: list[str] | None = None
    priority: int | None = None
    orchestrator_agent_id: uuid.UUID | None = None
    autonomy_level: str | None = None
    brief_artifact_id: uuid.UUID | None = None
    current_baseline_id: uuid.UUID | None = None
    deadline_at: datetime | None = None
    budget_limit: Decimal | None = None
    paused_seconds: int | None = None
    state_changed_at: datetime | None = None
    state_reason: str | None = None
    row_version: int | None = None
    executor_project_ids: list[uuid.UUID] = Field(default_factory=list)


class MemberOperation(BaseModel):
    """One op of manage_project_members (§5.2). Roles are validated by the
    route, so an unknown one is reported as a MEMBER_RULE_VIOLATION item."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["add", "update", "suspend", "release"]
    agent_id: uuid.UUID
    role: str | None = Field(default=None, max_length=40)
    can_review: bool | None = None
    can_approve: bool | None = None
    responsibilities: str | None = Field(default=None, max_length=2000)
    valid_to: date | None = None


class MembersApplyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operations: list[MemberOperation] = Field(min_length=1, max_length=20)
    idempotency_key: str = Field(min_length=1, max_length=150)


class MembersApplyOut(BaseModel):
    project_id: uuid.UUID
    memberships: list[ProjectAgentMembershipOut]
    applied: list[dict] = Field(default_factory=list)
    violations: list[dict] = Field(default_factory=list)


class PlanningAdvanceOut(BaseModel):
    mission: MissionOut
    decision_id: uuid.UUID
    replayed: bool = False
    not_evaluated: list[dict] = Field(default_factory=list)


REVIEW_LAYER_SET = frozenset(REVIEW_LAYERS)


# ---------------------------------------------------------------------------
# M0.2d (§5.8-§5.10): documents, my role, my tasks
# ---------------------------------------------------------------------------
DOCUMENT_ENTITY_TYPES = ("project", "planning_item", "project_task", "mission_criterion")


class MissionDocumentAttachIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: Literal["project", "planning_item", "project_task", "mission_criterion"]
    entity_id: uuid.UUID
    # Relative to the Docs tree, under missions/<slug>/ or projects/<slug>/
    # (core/mission_documents.py); the route refuses anything else.
    doc_path: str = Field(min_length=1, max_length=500)
    register_artifact: bool = False
    artifact_type: str | None = Field(default=None, max_length=50)
    idempotency_key: str = Field(min_length=1, max_length=150)


class MissionDocumentOut(BaseModel):
    project_id: uuid.UUID
    doc_link_id: uuid.UUID
    doc_path: str
    entity_type: str
    entity_id: uuid.UUID
    content_hash: str
    link_created: bool
    artifact_id: uuid.UUID | None = None
    artifact_version_id: uuid.UUID | None = None
    artifact_version_number: int | None = None
    artifact_version_created: bool = False


class MyTaskItem(BaseModel):
    project_id: uuid.UUID
    task_id: uuid.UUID
    number: int
    title: str
    status: str
    # Status of the task's latest TaskExecution; None before the first one.
    execution_state: str | None = None
    # How the caller relates to the task: executor (active assignment) and/or reviewer.
    relations: list[Literal["executor", "reviewer"]]


class MyReviewItem(BaseModel):
    review_id: uuid.UUID
    execution_id: uuid.UUID
    task_id: uuid.UUID
    status: str


class MissionOrchestratorRef(BaseModel):
    agent_id: uuid.UUID
    name: str


class MyMissionRoleOut(BaseModel):
    project_id: uuid.UUID
    project_type: str
    mission_state: str | None = None
    membership_id: uuid.UUID
    role: str
    can_review: bool
    responsibilities: str | None = None
    orchestrator: MissionOrchestratorRef | None = None
    my_tasks: list[MyTaskItem] = Field(default_factory=list)
    my_reviews: list[MyReviewItem] = Field(default_factory=list)


class MyTasksOut(BaseModel):
    state: str
    tasks: list[MyTaskItem] = Field(default_factory=list)

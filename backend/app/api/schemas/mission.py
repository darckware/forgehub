"""Pydantic schemas for the Mission domain (M0.0, MCP_MISSION_TOOLS_SPEC.md §2-§3.1)."""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.orchestration import ProjectAgentMembershipOut
from app.db.models.mission import (
    MISSION_RISK_LEVELS,
    MISSION_STATES,
    PLAN_REVIEW_KINDS,
    PLAN_VERIFICATION_RESULTS,
    PLANNING_STAGES,
    REVIEW_DISPOSITIONS,
    REVIEW_LAYERS,
)


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


def _one_of(values: tuple[str, ...]) -> str:
    return f"^({'|'.join(values)})$"


# ---------------------------------------------------------------------------
# Planning records (§2.6, M0.0b). No body field names the reviewer, verifier
# or decider: it is always the authenticated principal (extra="forbid").
# ---------------------------------------------------------------------------
class MissionPlanCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    scope_summary: str | None = None
    estimated_start_date: date | None = None
    estimated_end_date: date | None = None
    estimated_cost: Decimal | None = Field(default=None, ge=0)


class MissionPlanVersionOut(BaseModel):
    project_plan_id: uuid.UUID
    name: str
    status: str
    author_type: str
    author_id: uuid.UUID
    author_name: str
    planning_stage: str | None
    created_at: datetime


class PlanReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_plan_id: uuid.UUID
    kind: str = Field(pattern=_one_of(PLAN_REVIEW_KINDS))
    layer: str = Field(pattern=_one_of(REVIEW_LAYERS))
    artifact_version_id: uuid.UUID
    summary: str | None = Field(default=None, max_length=20000)


class PlanReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_plan_id: uuid.UUID
    kind: str
    layer: str
    reviewer_agent_id: uuid.UUID
    artifact_version_id: uuid.UUID
    summary: str | None
    created_at: datetime


class ReviewItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=20000)
    needs_marcelo_decision: bool = False


class ReviewItemDisposeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disposition: str = Field(pattern=_one_of(REVIEW_DISPOSITIONS))
    reason: str = Field(min_length=1, max_length=4000)
    needs_marcelo_decision: bool | None = None


class ReviewItemDecideIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str = Field(pattern=_one_of(REVIEW_DISPOSITIONS))
    reason: str = Field(min_length=1, max_length=4000)


class ReviewItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    review_id: uuid.UUID
    text: str
    disposition: str | None
    disposition_reason: str | None
    disposed_by: str | None
    disposed_at: datetime | None
    needs_marcelo_decision: bool
    marcelo_decision: str | None
    marcelo_reason: str | None
    marcelo_decided_by: str | None
    marcelo_decided_at: datetime | None
    created_at: datetime


class ReviewWaiverCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_plan_id: uuid.UUID
    layer: str = Field(pattern=_one_of(REVIEW_LAYERS))
    reason: str = Field(min_length=1, max_length=4000)


class ReviewWaiverOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_plan_id: uuid.UUID
    layer: str
    reason: str
    decided_by: str
    created_at: datetime


class PlanVerificationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_plan_id: uuid.UUID
    sampled_item_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)
    result: str = Field(pattern=_one_of(PLAN_VERIFICATION_RESULTS))
    notes: str | None = Field(default=None, max_length=20000)


class PlanVerificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_plan_id: uuid.UUID
    verifier_agent_id: uuid.UUID
    sampled_item_ids: list[uuid.UUID]
    result: str
    notes: str | None
    created_at: datetime


class DossierCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_version_id: uuid.UUID
    file_sha256: str = Field(pattern="^[0-9a-fA-F]{64}$")


class DossierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    artifact_version_id: uuid.UUID
    file_sha256: str
    registered_by_type: str
    registered_by: str
    created_at: datetime


class PlanningRecordsOut(BaseModel):
    project_plan_id: uuid.UUID | None
    author: MissionPlanVersionOut | None
    reviews: list[PlanReviewOut]
    items: list[ReviewItemOut]
    waivers: list[ReviewWaiverOut]
    verifications: list[PlanVerificationOut]
    dossiers: list[DossierOut]


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


# ---------------------------------------------------------------------------
# Governed plan approval (M0.2b, §5.3, §7). The submitter is the authenticated
# principal and the decider is Marcelo on :decide: no approver token, name or
# `approved` flag exists here, and extra="forbid" turns any such field into a 422.
# ---------------------------------------------------------------------------
class PlanFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    scope_summary: str | None = Field(default=None, max_length=20000)
    estimated_start_date: date | None = None
    estimated_end_date: date | None = None
    estimated_cost: Decimal | None = Field(default=None, ge=0)


class PlanSubmitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Initial baseline: optional, and when given it must equal the reviewed
    # version's fields. Change request: required (a new plan version).
    plan: PlanFields | None = None
    task_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    change_request_id: uuid.UUID | None = None
    idempotency_key: str = Field(min_length=1, max_length=150)


class PlanCheck(BaseModel):
    key: str
    status: Literal["passed", "failed", "not_evaluated"]
    passed: bool | None
    detail: str | list[dict] | None = None


class PlanSubmitOut(BaseModel):
    plan_id: uuid.UUID
    approval_request_id: uuid.UUID
    plan_hash: str
    checks: list[PlanCheck]
    status: Literal["pending_approval"] = "pending_approval"
    change_request_id: uuid.UUID | None = None
    task_ids: list[uuid.UUID]


class PlanWithdrawIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=4000)


class PlanWithdrawOut(BaseModel):
    plan_id: uuid.UUID
    approval_request_id: uuid.UUID
    status: str
    plan_status: str
    withdrawn_at: datetime | None
    withdrawn_by: str | None
    withdrawn_reason: str | None


# ---------------------------------------------------------------------------
# M0.2c: assign, report, request review, return (§5.5, §5.7, §5.11, §5.12)
# ---------------------------------------------------------------------------
class TaskAssignIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: uuid.UUID
    reason: str = Field(min_length=1, max_length=2000)
    idempotency_key: str = Field(min_length=1, max_length=150)


class TaskAssignOut(BaseModel):
    task_id: uuid.UUID
    assignment_id: uuid.UUID
    membership_id: uuid.UUID
    agent_id: uuid.UUID
    previous_assignment_id: uuid.UUID | None = None
    task_status: str
    changed: bool


class TaskReportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Never verified/completed: only the evidence verification pass promotes
    # reported -> verified (§5.7).
    status: Literal["reported", "failed", "blocked"]
    summary: str = Field(min_length=1, max_length=10000)
    evidence: list[str] = Field(min_length=1, max_length=20)
    idempotency_key: str = Field(min_length=1, max_length=150)


class TaskReportOut(BaseModel):
    task_id: uuid.UUID
    execution_id: uuid.UUID
    status: str
    evidence_ref: str
    evidence: list[str]
    verification: Literal["queued", "not_applicable"]


class ReviewRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_id: uuid.UUID
    reviewer_agent_id: uuid.UUID
    idempotency_key: str = Field(min_length=1, max_length=150)


class ReviewRequestOut(BaseModel):
    task_id: uuid.UUID
    execution_id: uuid.UUID
    review_id: uuid.UUID
    reviewer_membership_id: uuid.UUID
    reviewer_agent_id: uuid.UUID
    status: str
    demand_id: uuid.UUID
    demand_number: int


class TaskReturnIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_id: uuid.UUID
    reason: str = Field(min_length=1, max_length=4000)
    idempotency_key: str = Field(min_length=1, max_length=150)


class TaskReturnOut(BaseModel):
    task_id: uuid.UUID
    execution_id: uuid.UUID
    task_status: str
    review_id: uuid.UUID | None = None
    review_status: str | None = None

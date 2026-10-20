"""Schemas for project-agent orchestration and bounded engineering loops."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.models.orchestration import (
    LOOP_PHASES,
    FORGEROUTER_ROUTING_GROUPS,
    MEMBERSHIP_STATUSES,
    PROJECT_AGENT_ROLES,
    REVIEW_STATUSES,
    RUNTIME_PURPOSES,
    RUNTIME_TYPES,
)


class ForgeRouterVirtualModelOut(BaseModel):
    id: str
    routing_group: str
    description: str
    is_recommended_default: bool = False


class AgentRuntimeProfileCreate(BaseModel):
    agent_id: uuid.UUID | None = None
    sub_agent_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=150)
    runtime_type: str
    model_ref: str = Field(default="forgerouter/auto", min_length=1, max_length=255)
    routing_group: str = "auto"
    purpose: str = "general"
    intelligence_level: int = Field(default=3, ge=1, le=5)
    capability_scope: dict | list | None = None
    max_budget_usd: Decimal | None = Field(default=None, ge=0)
    is_default: bool = False
    is_active: bool = True

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_runtime(cls, value):
        if isinstance(value, dict) and value.get("runtime_type") == "antigravity":
            value = {**value, "runtime_type": "agy"}
        return value

    @model_validator(mode="after")
    def validate_profile(self):
        if bool(self.agent_id) == bool(self.sub_agent_id):
            raise ValueError("exactly one of agent_id or sub_agent_id must be set")
        if self.runtime_type not in RUNTIME_TYPES:
            raise ValueError(f"runtime_type must be one of {RUNTIME_TYPES}")
        if self.purpose not in RUNTIME_PURPOSES:
            raise ValueError(f"purpose must be one of {RUNTIME_PURPOSES}")
        if self.routing_group not in FORGEROUTER_ROUTING_GROUPS:
            raise ValueError(f"routing_group must be one of {FORGEROUTER_ROUTING_GROUPS}")
        return self


class AgentRuntimeProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    runtime_type: str | None = None
    model_ref: str | None = Field(default=None, min_length=1, max_length=255)
    routing_group: str | None = None
    purpose: str | None = None
    intelligence_level: int | None = Field(default=None, ge=1, le=5)
    capability_scope: dict | list | None = None
    max_budget_usd: Decimal | None = Field(default=None, ge=0)
    is_default: bool | None = None
    is_active: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_runtime(cls, value):
        if isinstance(value, dict) and value.get("runtime_type") == "antigravity":
            value = {**value, "runtime_type": "agy"}
        return value

    @model_validator(mode="after")
    def validate_profile(self):
        if self.runtime_type is not None and self.runtime_type not in RUNTIME_TYPES:
            raise ValueError(f"runtime_type must be one of {RUNTIME_TYPES}")
        if self.purpose is not None and self.purpose not in RUNTIME_PURPOSES:
            raise ValueError(f"purpose must be one of {RUNTIME_PURPOSES}")
        if self.routing_group is not None and self.routing_group not in FORGEROUTER_ROUTING_GROUPS:
            raise ValueError(f"routing_group must be one of {FORGEROUTER_ROUTING_GROUPS}")
        return self


class AgentRuntimeProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID | None
    sub_agent_id: uuid.UUID | None
    name: str
    runtime_type: str
    model_ref: str
    routing_group: str
    purpose: str
    intelligence_level: int
    capability_scope: dict | list | None
    max_budget_usd: Decimal | None
    is_default: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ProjectAgentMembershipCreate(BaseModel):
    agent_id: uuid.UUID | None = None
    sub_agent_id: uuid.UUID | None = None
    role: str
    status: str = "active"
    responsibilities: str | None = None
    allowed_runtimes: list[str] | None = None
    allocation_percent: Decimal = Field(default=Decimal("100.00"), gt=0, le=100)
    max_concurrent_tasks_override: int | None = Field(default=None, ge=1)
    can_review: bool = False
    can_approve: bool = False
    valid_from: date | None = None
    valid_to: date | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_runtimes(cls, value):
        if isinstance(value, dict) and value.get("allowed_runtimes"):
            value = {**value, "allowed_runtimes": ["agy" if item == "antigravity" else item for item in value["allowed_runtimes"]]}
        return value

    @model_validator(mode="after")
    def validate_membership(self):
        if bool(self.agent_id) == bool(self.sub_agent_id):
            raise ValueError("exactly one of agent_id or sub_agent_id must be set")
        if self.role not in PROJECT_AGENT_ROLES:
            raise ValueError(f"role must be one of {PROJECT_AGENT_ROLES}")
        if self.status not in MEMBERSHIP_STATUSES:
            raise ValueError(f"status must be one of {MEMBERSHIP_STATUSES}")
        if self.allowed_runtimes:
            invalid = sorted(set(self.allowed_runtimes) - set(RUNTIME_TYPES))
            if invalid:
                raise ValueError(f"unsupported allowed_runtimes: {invalid}")
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("valid_to cannot be before valid_from")
        return self


class ProjectAgentMembershipUpdate(BaseModel):
    role: str | None = None
    status: str | None = None
    responsibilities: str | None = None
    allowed_runtimes: list[str] | None = None
    allocation_percent: Decimal | None = Field(default=None, gt=0, le=100)
    max_concurrent_tasks_override: int | None = Field(default=None, ge=1)
    can_review: bool | None = None
    can_approve: bool | None = None
    valid_from: date | None = None
    valid_to: date | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_runtimes(cls, value):
        if isinstance(value, dict) and value.get("allowed_runtimes"):
            value = {**value, "allowed_runtimes": ["agy" if item == "antigravity" else item for item in value["allowed_runtimes"]]}
        return value

    @model_validator(mode="after")
    def validate_membership(self):
        if self.role is not None and self.role not in PROJECT_AGENT_ROLES:
            raise ValueError(f"role must be one of {PROJECT_AGENT_ROLES}")
        if self.status is not None and self.status not in MEMBERSHIP_STATUSES:
            raise ValueError(f"status must be one of {MEMBERSHIP_STATUSES}")
        if self.allowed_runtimes:
            invalid = sorted(set(self.allowed_runtimes) - set(RUNTIME_TYPES))
            if invalid:
                raise ValueError(f"unsupported allowed_runtimes: {invalid}")
        return self


class ProjectAgentMembershipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    agent_id: uuid.UUID | None
    sub_agent_id: uuid.UUID | None
    role: str
    status: str
    responsibilities: str | None
    allowed_runtimes: list | None
    allocation_percent: Decimal
    max_concurrent_tasks_override: int | None
    can_review: bool
    can_approve: bool
    valid_from: date | None
    valid_to: date | None
    created_at: datetime
    updated_at: datetime


class ProjectLoopPolicyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    phase: str
    producer_membership_id: uuid.UUID
    reviewer_membership_id: uuid.UUID
    producer_runtime_profile_id: uuid.UUID
    reviewer_runtime_profile_id: uuid.UUID
    max_iterations: int = Field(default=3, ge=1, le=20)
    min_review_score: int = Field(default=80, ge=0, le=100)
    requires_human_approval: bool = True
    auto_dispatch: bool = False
    is_active: bool = True

    @model_validator(mode="after")
    def validate_policy(self):
        if self.phase not in LOOP_PHASES:
            raise ValueError(f"phase must be one of {LOOP_PHASES}")
        if self.producer_membership_id == self.reviewer_membership_id:
            raise ValueError("producer and reviewer memberships must be different")
        return self


class ProjectLoopPolicyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    phase: str | None = None
    producer_membership_id: uuid.UUID | None = None
    reviewer_membership_id: uuid.UUID | None = None
    producer_runtime_profile_id: uuid.UUID | None = None
    reviewer_runtime_profile_id: uuid.UUID | None = None
    max_iterations: int | None = Field(default=None, ge=1, le=20)
    min_review_score: int | None = Field(default=None, ge=0, le=100)
    requires_human_approval: bool | None = None
    auto_dispatch: bool | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_policy(self):
        if self.phase is not None and self.phase not in LOOP_PHASES:
            raise ValueError(f"phase must be one of {LOOP_PHASES}")
        return self


class ProjectLoopPolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    phase: str
    producer_membership_id: uuid.UUID
    reviewer_membership_id: uuid.UUID
    producer_runtime_profile_id: uuid.UUID
    reviewer_runtime_profile_id: uuid.UUID
    max_iterations: int
    min_review_score: int
    requires_human_approval: bool
    auto_dispatch: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TaskExecutionReviewCreate(BaseModel):
    reviewer_membership_id: uuid.UUID
    runtime_profile_id: uuid.UUID | None = None
    status: str = "pending"
    score: int | None = Field(default=None, ge=0, le=100)
    feedback: str | None = None
    evidence_ref: str | None = Field(default=None, max_length=500)
    runtime_session_ref: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_review(self):
        if self.status not in REVIEW_STATUSES:
            raise ValueError(f"status must be one of {REVIEW_STATUSES}")
        if self.status in {"approved", "changes_requested", "rejected"} and not self.feedback:
            raise ValueError("feedback is required for a review decision")
        return self


class TaskExecutionReviewUpdate(BaseModel):
    status: str | None = None
    score: int | None = Field(default=None, ge=0, le=100)
    feedback: str | None = None
    evidence_ref: str | None = Field(default=None, max_length=500)
    runtime_session_ref: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_review(self):
        if self.status is not None and self.status not in REVIEW_STATUSES:
            raise ValueError(f"status must be one of {REVIEW_STATUSES}")
        return self


class TaskExecutionReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    execution_id: uuid.UUID
    reviewer_membership_id: uuid.UUID
    runtime_profile_id: uuid.UUID | None
    status: str
    score: int | None
    feedback: str | None
    evidence_ref: str | None
    runtime_session_ref: str | None
    decided_at: datetime | None
    created_at: datetime
    updated_at: datetime


class EligibleMembershipOut(BaseModel):
    membership: ProjectAgentMembershipOut
    eligible: bool
    reasons: list[str]


class TaskDispatchCreate(BaseModel):
    assignment_id: uuid.UUID
    runtime_profile_id: uuid.UUID
    loop_policy_id: uuid.UUID | None = None
    mode: str = Field(default="execute", pattern="^(plan|execute)$")
    prompt_addendum: str | None = Field(default=None, max_length=4000)
    max_seconds: int = Field(default=1800, ge=30, le=7200)


class TaskDispatchOut(BaseModel):
    execution_id: uuid.UUID
    run_id: str
    status: str
    runtime_type: str
    model_ref: str
    loop_iteration: int

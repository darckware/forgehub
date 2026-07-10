"""Pydantic schemas for the Task domain (project_tasks, task_dependencies,
task_required_skills, task_assignments, task_executions).
"""
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.models.task import TASK_STATUSES as _TASK_STATUSES_TUPLE

# --------------------------------------------------------------------------
# ProjectTask
# --------------------------------------------------------------------------

TASK_TYPES = {
    "feature",
    "bug",
    "improvement",
    "technical_debt",
    "refactoring",
    "security_fix",
    "research",
    "documentation",
    "other",
}
# Re-exported from the model so the DB CheckConstraint and this schema-layer
# validation can never drift apart -- see db/models/task.py for the
# rationale behind each status, notably "done" vs "deployed".
TASK_STATUSES = set(_TASK_STATUSES_TUPLE)
TASK_PRIORITIES = {"low", "medium", "high", "critical"}


class ProjectTaskBase(BaseModel):
    # At least one source (planning_item_id or change_request_id) is required
    # on create -- enforced at the API layer (routes/task.py) rather than here
    # so the error message can be domain-specific.
    planning_item_id: uuid.UUID | None = None
    change_request_id: uuid.UUID | None = None
    parent_task_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    task_type: str = "feature"
    priority: str = "medium"
    estimated_cost: float | None = None
    planned_start_date: date | None = None
    planned_end_date: date | None = None
    policy_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _validate_choices(self) -> "ProjectTaskBase":
        if self.task_type not in TASK_TYPES:
            raise ValueError(f"task_type must be one of {sorted(TASK_TYPES)}")
        if self.priority not in TASK_PRIORITIES:
            raise ValueError(f"priority must be one of {sorted(TASK_PRIORITIES)}")
        if (
            self.planned_start_date
            and self.planned_end_date
            and self.planned_end_date < self.planned_start_date
        ):
            raise ValueError("planned_end_date cannot be before planned_start_date")
        return self


class ProjectTaskCreate(ProjectTaskBase):
    pass


class ProjectTaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    task_type: str | None = None
    status: str | None = None
    priority: str | None = None
    estimated_cost: float | None = None
    actual_cost: float | None = None
    planned_start_date: date | None = None
    planned_end_date: date | None = None
    parent_task_id: uuid.UUID | None = None
    planning_item_id: uuid.UUID | None = None
    change_request_id: uuid.UUID | None = None
    policy_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _validate_choices(self) -> "ProjectTaskUpdate":
        if self.task_type is not None and self.task_type not in TASK_TYPES:
            raise ValueError(f"task_type must be one of {sorted(TASK_TYPES)}")
        if self.status is not None and self.status not in TASK_STATUSES:
            raise ValueError(f"status must be one of {sorted(TASK_STATUSES)}")
        if self.priority is not None and self.priority not in TASK_PRIORITIES:
            raise ValueError(f"priority must be one of {sorted(TASK_PRIORITIES)}")
        return self


class ProjectTaskOut(ProjectTaskBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    planning_item_id: uuid.UUID | None = None
    change_request_id: uuid.UUID | None = None
    policy_id: uuid.UUID | None = None
    status: str
    actual_cost: float | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    kanboard_task_id: int | None = None
    created_at: datetime
    updated_at: datetime


class ProjectTaskKanboardSyncOut(ProjectTaskOut):
    """Response for POST /tasks/{id}/sync-kanboard -- adds the browser-facing
    card URL, which is computed (KANBOARD_PUBLIC_URL + id), not a stored
    column."""

    kanboard_url: str | None = None


# --------------------------------------------------------------------------
# TaskDependency
# --------------------------------------------------------------------------

DEPENDENCY_TYPES = {"finish_to_start", "start_to_start", "finish_to_finish", "start_to_finish"}


class TaskDependencyCreate(BaseModel):
    task_id: uuid.UUID
    depends_on_task_id: uuid.UUID
    dependency_type: str = "finish_to_start"

    @model_validator(mode="after")
    def _validate(self) -> "TaskDependencyCreate":
        if self.dependency_type not in DEPENDENCY_TYPES:
            raise ValueError(f"dependency_type must be one of {sorted(DEPENDENCY_TYPES)}")
        if self.task_id == self.depends_on_task_id:
            raise ValueError("a task cannot depend on itself")
        return self


class TaskDependencyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    depends_on_task_id: uuid.UUID
    dependency_type: str
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------
# TaskRequiredSkill
# --------------------------------------------------------------------------


class TaskRequiredSkillCreate(BaseModel):
    task_id: uuid.UUID
    skill_id: uuid.UUID
    is_mandatory: bool = True
    minimum_proficiency: str | None = None


class TaskRequiredSkillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    skill_id: uuid.UUID
    is_mandatory: bool
    minimum_proficiency: str | None = None
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------
# TaskAssignment
# --------------------------------------------------------------------------

ASSIGNMENT_STATUSES = {"active", "released", "revoked"}


class TaskAssignmentCreate(BaseModel):
    task_id: uuid.UUID
    agent_id: uuid.UUID | None = None
    sub_agent_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _validate(self) -> "TaskAssignmentCreate":
        if bool(self.agent_id) == bool(self.sub_agent_id):
            raise ValueError("exactly one of agent_id or sub_agent_id must be set")
        return self


class TaskAssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    agent_id: uuid.UUID | None = None
    sub_agent_id: uuid.UUID | None = None
    status: str
    assigned_at: datetime
    unassigned_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------
# TaskExecution
# --------------------------------------------------------------------------

EXECUTOR_TYPES = {"agent", "sub_agent", "human", "system"}
EXECUTION_STATUSES = {"pending", "running", "failed", "retried", "verified", "completed"}
EXECUTION_TERMINAL_STATUSES = {"verified", "completed"}


class TaskExecutionCreate(BaseModel):
    assignment_id: uuid.UUID | None = None
    executor_type: str = "agent"
    status: str = "pending"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    outcome_summary: str | None = None
    evidence_ref: str | None = None
    actual_cost: float | None = None

    @model_validator(mode="after")
    def _validate(self) -> "TaskExecutionCreate":
        if self.executor_type not in EXECUTOR_TYPES:
            raise ValueError(f"executor_type must be one of {sorted(EXECUTOR_TYPES)}")
        if self.status not in EXECUTION_STATUSES:
            raise ValueError(f"status must be one of {sorted(EXECUTION_STATUSES)}")
        # Business rule 6.4.3: every execution must have evidence -- enforced
        # once the execution reaches a terminal (verified/completed) status.
        if self.status in EXECUTION_TERMINAL_STATUSES and not self.evidence_ref:
            raise ValueError(
                f"evidence_ref is required when status is one of {sorted(EXECUTION_TERMINAL_STATUSES)}"
            )
        return self


class TaskExecutionUpdate(BaseModel):
    status: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    outcome_summary: str | None = None
    evidence_ref: str | None = None
    actual_cost: float | None = None

    @model_validator(mode="after")
    def _validate(self) -> "TaskExecutionUpdate":
        if self.status is not None and self.status not in EXECUTION_STATUSES:
            raise ValueError(f"status must be one of {sorted(EXECUTION_STATUSES)}")
        # NOTE: the evidence-required-on-terminal-status rule (6.4.3) is
        # intentionally NOT enforced here. This is a partial-update DTO --
        # a caller may legitimately PATCH only {"status": "completed"} when
        # evidence_ref was already set by an earlier PATCH, and this schema
        # has no visibility into that existing row state. The route layer
        # (see update_task_execution in app/api/routes/task.py) re-checks
        # the rule against the *merged* existing+incoming state and returns
        # 400 there, which is the authoritative enforcement point for this
        # rule on updates.
        return self


class TaskExecutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    assignment_id: uuid.UUID | None = None
    attempt_number: int
    executor_type: str
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    outcome_summary: str | None = None
    evidence_ref: str | None = None
    actual_cost: float | None = None
    created_at: datetime
    updated_at: datetime

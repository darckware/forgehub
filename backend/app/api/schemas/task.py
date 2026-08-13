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
    # The HOW (approach/acceptance criteria/context for whichever agent
    # dispatches this), distinct from description (the WHAT). Never
    # required; included in the dispatch message body when set.
    plan_brief: str | None = None
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


class TaskSubmitIn(BaseModel):
    """Body for POST /tasks/submit -- lets any Hermes agent on the host
    (bridge token, same trust boundary as demand.py's /submit) log a task
    directly, without a human triaging it through the Inbox first. Creates
    a minimal PlanningItem + the task under it in one call (core/conversions.
    py's convert_to_quick_task -- same "task avulsa" shortcut the Inbox's
    quick_task convert target already uses), since a task can never exist
    without a planning item per the core traceability invariant."""

    project_id: uuid.UUID
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    item_type: str | None = None
    # Free-text, e.g. a Hermes profile slug -- purely for the audit trail
    # (prefixed onto the description), not resolved against a real Agent
    # row the way demand.py's from_agent_id is.
    from_agent: str | None = None


class ProjectTaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    plan_brief: str | None = None
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
    # Server-assigned display number -- see ProjectTask.number's docstring.
    number: int
    planning_item_id: uuid.UUID | None = None
    change_request_id: uuid.UUID | None = None
    policy_id: uuid.UUID | None = None
    # Computed, read-only -- ProjectTask has no project_id column of its own
    # (a task traces to a project only indirectly, via planning_item_id or
    # change_request_id). The route layer resolves and attaches this before
    # returning (see _attach_project_ids in routes/task.py); it is never
    # accepted on create/update (absent from ProjectTaskBase) since the
    # frontend used to send it and the backend silently discarded it --
    # every task looked unlinked from its project on screen (found during
    # the Planning end-to-end test, 2026-07-16).
    project_id: uuid.UUID | None = None
    # Computed, read-only, same pattern as project_id above -- see
    # core/task_health.py's module docstring for what each value means.
    # The route layer attaches this via _attach_task_health before
    # returning; never accepted on create/update.
    health: str = "ok"
    status: str
    actual_cost: float | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


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
    membership_id: uuid.UUID | None = None

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
    membership_id: uuid.UUID | None = None
    status: str
    assigned_at: datetime
    unassigned_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------
# TaskExecution
# --------------------------------------------------------------------------

EXECUTOR_TYPES = {"agent", "sub_agent", "human", "system"}
RUNTIME_TYPES = {"claude", "codex", "agy", "antigravity"}
EXECUTION_STATUSES = {
    "pending", "running", "blocked", "paused", "reconciling", "recovering",
    "failed", "retried", "verified", "completed",
}
EXECUTION_TERMINAL_STATUSES = {"verified", "completed"}


class TaskExecutionCreate(BaseModel):
    assignment_id: uuid.UUID | None = None
    runtime_profile_id: uuid.UUID | None = None
    loop_policy_id: uuid.UUID | None = None
    parent_execution_id: uuid.UUID | None = None
    executor_type: str = "agent"
    runtime_type: str | None = None
    runtime_session_ref: str | None = Field(default=None, max_length=255)
    loop_iteration: int = Field(default=1, ge=1, le=20)
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
        if self.runtime_type is not None and self.runtime_type not in RUNTIME_TYPES:
            raise ValueError(f"runtime_type must be one of {sorted(RUNTIME_TYPES)}")
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
    runtime_profile_id: uuid.UUID | None = None
    loop_policy_id: uuid.UUID | None = None
    parent_execution_id: uuid.UUID | None = None
    attempt_number: int
    executor_type: str
    runtime_type: str | None = None
    runtime_session_ref: str | None = None
    work_package_id: uuid.UUID | None = None
    adapter_version: str | None = None
    process_ref: str | None = None
    exit_code: int | None = None
    loop_iteration: int = 1
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    outcome_summary: str | None = None
    evidence_ref: str | None = None
    actual_cost: float | None = None
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------
# Task dispatch (via the Inbox message process)
# --------------------------------------------------------------------------
class TaskInboxDispatchIn(BaseModel):
    """Body for POST /tasks/{task_id}/dispatch.

    `target_agent_id` is optional: when omitted the route resolves the
    agent from the task's own active assignment, so the common path is a
    body-less dispatch of an already-assigned task.
    """

    target_agent_id: uuid.UUID | None = None
    # Extra instruction prepended to the task context in the prompt, same
    # role as AgentDemand.command_text in an Inbox dispatch.
    command_text: str | None = None
    # Whether the agent's reply should come back as a linked Inbox item.
    requires_response: bool = True


class TaskInboxDispatchOut(BaseModel):
    """What the caller needs to follow the run: the task's new status plus
    the Inbox message that actually carries the execution."""

    task_id: uuid.UUID
    task_status: str
    demand_id: uuid.UUID
    demand_number: int
    target_agent_id: uuid.UUID
    dispatch_status: str | None = None
    agent_run_id: str | None = None

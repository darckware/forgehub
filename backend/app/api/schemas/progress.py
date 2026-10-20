"""API contracts for progress checkpoints, recovery, and stage completion."""
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProgressCheckpointCreate(BaseModel):
    pipeline_stage_id: uuid.UUID | None = None
    checkpoint_type: str = "progress"
    step_key: str = Field(min_length=1, max_length=150)
    step_label: str = Field(min_length=1, max_length=255)
    state_snapshot: dict[str, Any] = Field(default_factory=dict)
    completed_requirement_keys: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    resume_from_step_key: str | None = Field(default=None, max_length=150)
    blocker_code: str | None = Field(default=None, max_length=100)
    error_code: str | None = Field(default=None, max_length=100)
    message: str | None = None
    idempotency_key: str = Field(min_length=8, max_length=255)

    @model_validator(mode="after")
    def validate_reason(self):
        if self.checkpoint_type == "blocked" and not self.blocker_code:
            raise ValueError("blocker_code is required for a blocked checkpoint")
        if self.checkpoint_type == "failed" and not self.error_code:
            raise ValueError("error_code is required for a failed checkpoint")
        return self


class ProgressCheckpointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    project_id: uuid.UUID
    pipeline_stage_id: uuid.UUID | None
    task_id: uuid.UUID | None
    task_execution_id: uuid.UUID | None
    sequence: int
    checkpoint_type: str
    step_key: str
    step_label: str
    state_snapshot: dict[str, Any]
    completed_requirement_keys: list[str]
    evidence_refs: list[str]
    last_confirmed_at: datetime
    resume_from_step_key: str | None
    blocker_code: str | None
    error_code: str | None
    message: str | None
    actor_type: str
    actor_id: uuid.UUID | None
    actor_name: str
    idempotency_key: str
    created_at: datetime


class ExecutionActionIn(BaseModel):
    step_key: str = Field(min_length=1, max_length=150)
    step_label: str = Field(min_length=1, max_length=255)
    message: str | None = None
    blocker_code: str | None = Field(default=None, max_length=100)
    error_code: str | None = Field(default=None, max_length=100)
    resume_from_step_key: str | None = Field(default=None, max_length=150)
    evidence_refs: list[str] = Field(default_factory=list)
    observed_state: str | None = None
    idempotency_key: str = Field(min_length=8, max_length=255)


class ExecutionActionOut(BaseModel):
    execution_id: uuid.UUID
    execution_status: str
    checkpoint: ProgressCheckpointOut
    resumed_execution_id: uuid.UUID | None = None


class StageCompletionAssessmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    pipeline_stage_id: uuid.UUID
    stage_revision: int
    baseline_id: uuid.UUID | None
    policy_version_id: uuid.UUID | None
    input_hash: str
    result: str
    requirement_results: list[dict[str, Any]]
    missing_requirements: list[dict[str, Any]]
    blocking_reasons: list[dict[str, Any]]
    evidence_refs: list[str]
    evaluator_version: str
    evaluated_at: datetime
    evaluated_by_type: str
    evaluated_by_id: uuid.UUID | None
    evaluated_by_name: str


class CompleteStageIn(BaseModel):
    assessment_id: uuid.UUID
    idempotency_key: str = Field(min_length=8, max_length=255)


class CompleteStageOut(BaseModel):
    stage_id: uuid.UUID
    status: str
    revision: int
    assessment_id: uuid.UUID
    checkpoint: ProgressCheckpointOut


class StageProgressOut(BaseModel):
    stage_id: uuid.UUID
    pipeline_id: uuid.UUID
    stage_name: str
    order_index: int
    effective_status: str
    requirement_total: int
    requirement_completed: int
    missing_requirements: list[dict[str, Any]]
    last_checkpoint: ProgressCheckpointOut | None
    stopped_reason: str | None
    resume_from: str | None
    completion_assessment: StageCompletionAssessmentOut | None


class ProjectProgressOut(BaseModel):
    project_id: uuid.UUID
    macroflow: str
    pipeline_id: uuid.UUID | None
    current_stage_id: uuid.UUID | None
    stages: list[StageProgressOut]
    last_confirmed_at: datetime | None
    stopped_at: dict[str, Any] | None
    first_safe_action: str | None

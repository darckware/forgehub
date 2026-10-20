"""Pydantic schemas for the Pipeline domain."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------------------------------------------------------------------------
# PipelineTemplate
# ---------------------------------------------------------------------------


class PipelineTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    is_active: bool = True


class PipelineTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    is_active: bool | None = None


class PipelineTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# PipelineTemplateStage
# ---------------------------------------------------------------------------


class PipelineTemplateStageCreate(BaseModel):
    template_id: uuid.UUID
    name: str = Field(min_length=1, max_length=255)
    stage_type: str = Field(min_length=1, max_length=100)
    order_index: int = Field(ge=0)
    requires_approval: bool = False
    requires_verification: bool = False


class PipelineTemplateStageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    template_id: uuid.UUID
    name: str
    stage_type: str
    order_index: int
    requires_approval: bool
    requires_verification: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# PipelineTemplateRequiredArtifact
# ---------------------------------------------------------------------------


class PipelineTemplateRequiredArtifactCreate(BaseModel):
    template_stage_id: uuid.UUID
    artifact_type: str = Field(min_length=1, max_length=100)
    is_mandatory: bool = True


class PipelineTemplateRequiredArtifactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    template_stage_id: uuid.UUID
    artifact_type: str
    is_mandatory: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# PipelineStageDependency (nested under stage creation)
# ---------------------------------------------------------------------------


class PipelineStageDependencyCreate(BaseModel):
    depends_on_stage_id: uuid.UUID


class PipelineStageDependencyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    stage_id: uuid.UUID
    depends_on_stage_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# PipelineStageRequiredArtifact (nested under stage creation)
# ---------------------------------------------------------------------------


class PipelineStageRequiredArtifactCreate(BaseModel):
    artifact_type: str = Field(min_length=1, max_length=100)
    is_mandatory: bool = True
    artifact_id: uuid.UUID | None = None
    is_fulfilled: bool = False


class PipelineStageRequiredArtifactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    stage_id: uuid.UUID
    artifact_type: str
    is_mandatory: bool
    artifact_id: uuid.UUID | None
    is_fulfilled: bool
    created_at: datetime
    updated_at: datetime


class PipelineStageRequiredArtifactUpdate(BaseModel):
    artifact_id: uuid.UUID | None = None
    is_fulfilled: bool | None = None


# ---------------------------------------------------------------------------
# PipelineStageGate (nested under stage creation)
# ---------------------------------------------------------------------------


class PipelineStageGateCreate(BaseModel):
    gate_type: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    is_mandatory: bool = True


class PipelineStageGateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    stage_id: uuid.UUID
    gate_type: str
    name: str
    is_mandatory: bool
    status: str
    approved_by: str | None
    created_at: datetime
    updated_at: datetime


class PipelineStageGateUpdate(BaseModel):
    status: str = Field(description="pending | approved | rejected")
    approved_by: str | None = None


# ---------------------------------------------------------------------------
# PipelineStage
# ---------------------------------------------------------------------------


class PipelineStageCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    stage_type: str = Field(min_length=1, max_length=100)
    order_index: int = Field(ge=0)
    status: str = "pending"
    requires_approval: bool = False
    requires_verification: bool = False
    required_artifacts: list[PipelineStageRequiredArtifactCreate] = Field(default_factory=list)
    gates: list[PipelineStageGateCreate] = Field(default_factory=list)
    depends_on_stage_ids: list[uuid.UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def prevent_unassessed_completion(self):
        if self.status == "completed":
            raise ValueError("A stage must be completed through the governed completion command")
        return self


class PipelineStageUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    stage_type: str | None = Field(default=None, min_length=1, max_length=100)
    order_index: int | None = Field(default=None, ge=0)
    status: str | None = None
    requires_approval: bool | None = None
    requires_verification: bool | None = None


class PipelineStageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pipeline_id: uuid.UUID
    name: str
    stage_type: str
    order_index: int
    status: str
    revision: int
    requires_approval: bool
    requires_verification: bool
    created_at: datetime
    updated_at: datetime
    required_artifacts: list[PipelineStageRequiredArtifactOut] = Field(default_factory=list)
    gates: list[PipelineStageGateOut] = Field(default_factory=list)
    dependencies: list[PipelineStageDependencyOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# ProjectPipeline (primary entity)
# ---------------------------------------------------------------------------


class ProjectPipelineCreate(BaseModel):
    project_id: uuid.UUID
    template_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    status: str = "active"
    is_active: bool = True
    stages: list[PipelineStageCreate] = Field(default_factory=list)


class ProjectPipelineUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: str | None = None
    is_active: bool | None = None


class ProjectPipelineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    template_id: uuid.UUID | None
    name: str
    status: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    stages: list[PipelineStageOut] = Field(default_factory=list)

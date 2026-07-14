"""Schemas for conception, System Blueprint, and Project Scope."""
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


JsonValue = dict[str, Any] | list[Any]


class IdeaCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    problem_statement: str = Field(min_length=1)
    vision: str | None = None
    scope_summary: str | None = None
    requested_by: str | None = Field(default=None, max_length=255)
    priority: Literal["low", "medium", "high", "critical"] = "medium"


class DevelopmentRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    product_id: uuid.UUID
    request_type: str
    title: str
    description: str
    source_type: str
    source_ref: str | None
    requested_by: str | None
    priority: str
    status: str
    triage_result: dict | None
    created_at: datetime
    updated_at: datetime


class ConceptRevisionCreate(BaseModel):
    problem_statement: str = Field(min_length=1)
    vision: str | None = None
    stakeholders: JsonValue | None = None
    personas: JsonValue | None = None
    objectives: JsonValue | None = None
    success_metrics: JsonValue | None = None
    constraints: JsonValue | None = None
    assumptions: JsonValue | None = None
    risks: JsonValue | None = None
    scope_summary: str | None = None
    created_by: str | None = Field(default=None, max_length=255)


class ConceptRevisionOut(ConceptRevisionCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    concept_id: uuid.UUID
    revision: int
    content_hash: str
    created_at: datetime
    updated_at: datetime


class ProductConceptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    product_id: uuid.UUID
    status: str
    current_revision_id: uuid.UUID | None
    created_by: str | None
    created_at: datetime
    updated_at: datetime


class ConceptDetailOut(BaseModel):
    concept: ProductConceptOut
    current_revision: ConceptRevisionOut | None
    revisions: list[ConceptRevisionOut]


class BlueprintRevisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    blueprint_id: uuid.UUID
    revision: int
    status: str
    concept_revision_id: uuid.UUID | None
    product_version_id: uuid.UUID | None
    content_hash: str | None
    created_by: str | None
    created_at: datetime
    updated_at: datetime


class SystemBlueprintOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    product_id: uuid.UUID
    name: str
    current_revision_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class BlueprintDetailOut(BaseModel):
    blueprint: SystemBlueprintOut
    current_revision: BlueprintRevisionOut | None
    revisions: list[BlueprintRevisionOut]


class BlueprintRevisionCreate(BaseModel):
    created_by: str | None = Field(default=None, max_length=255)
    clone_from_revision_id: uuid.UUID | None = None


class SystemElementCreate(BaseModel):
    stable_key: str = Field(min_length=1, max_length=160, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    family: str = Field(min_length=1, max_length=30)
    element_type: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    lifecycle_status: Literal["proposed", "active", "deprecated", "removed"] = "proposed"
    criticality: Literal["low", "standard", "high", "critical"] = "standard"
    owner_ref: str | None = Field(default=None, max_length=255)
    parent_id: uuid.UUID | None = None
    spec_snapshot: dict[str, Any] = Field(default_factory=dict)
    source_ref: str | None = Field(default=None, max_length=500)


class SystemElementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    product_id: uuid.UUID
    stable_key: str
    family: str
    element_type: str
    name: str
    description: str | None
    lifecycle_status: str
    criticality: str
    owner_ref: str | None
    parent_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ElementRevisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    system_element_id: uuid.UUID
    blueprint_revision_id: uuid.UUID
    spec_snapshot: dict
    source_ref: str | None
    content_hash: str
    status: str
    created_at: datetime
    updated_at: datetime


class ElementWithRevisionOut(BaseModel):
    element: SystemElementOut
    revision: ElementRevisionOut


class SystemElementRelationCreate(BaseModel):
    from_element_id: uuid.UUID
    to_element_id: uuid.UUID
    relation_type: str = Field(min_length=1, max_length=40)
    attributes: dict[str, Any] | None = None


class SystemElementRelationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    blueprint_revision_id: uuid.UUID
    from_element_id: uuid.UUID
    to_element_id: uuid.UUID
    relation_type: str
    attributes: dict | None
    created_at: datetime
    updated_at: datetime


class BlueprintGraphOut(BaseModel):
    revision: BlueprintRevisionOut
    elements: list[ElementWithRevisionOut]
    relations: list[SystemElementRelationOut]


class ValidationIssue(BaseModel):
    severity: Literal["error", "warning"]
    code: str
    message: str
    element_id: uuid.UUID | None = None


class BlueprintValidationOut(BaseModel):
    valid: bool
    issues: list[ValidationIssue]


class ConceptDecision(BaseModel):
    decision: Literal["approved", "rework", "hold", "rejected"]
    decided_by: str = Field(min_length=1, max_length=255)
    comments: str | None = None


class AuthorizeDeliveryPlanning(BaseModel):
    version: str = Field(min_length=1, max_length=50)
    project_name: str = Field(min_length=1, max_length=255)
    project_description: str | None = None
    owner: str | None = Field(default=None, max_length=255)
    working_directory_path: str | None = Field(default=None, max_length=1024)


class DeliveryPlanningAuthorizationOut(BaseModel):
    product_id: uuid.UUID
    product_version_id: uuid.UUID
    project_id: uuid.UUID
    project_scope_id: uuid.UUID
    blueprint_revision_id: uuid.UUID


class ProjectScopeCreate(BaseModel):
    blueprint_base_revision_id: uuid.UUID
    created_by: str | None = Field(default=None, max_length=255)


class ProjectScopeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    project_id: uuid.UUID
    blueprint_base_revision_id: uuid.UUID
    revision: int
    status: str
    content_hash: str | None
    created_by: str | None
    created_at: datetime
    updated_at: datetime


class AcceptanceCriterionCreate(BaseModel):
    criterion: str = Field(min_length=1)
    verification_type: str = Field(default="test", min_length=1, max_length=50)
    required: bool = True
    order_index: int = Field(default=0, ge=0)


class AcceptanceCriterionOut(AcceptanceCriterionCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    project_scope_item_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ProjectScopeItemCreate(BaseModel):
    system_element_id: uuid.UUID
    base_element_revision_id: uuid.UUID | None = None
    target_element_revision_id: uuid.UUID | None = None
    change_type: Literal["add", "modify", "remove", "deprecate", "verify"]
    applicability: Literal["required", "optional", "not_applicable"] = "required"
    rationale: str | None = None
    acceptance_criteria: list[AcceptanceCriterionCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_not_applicable(self):
        if self.applicability == "not_applicable" and not self.rationale:
            raise ValueError("rationale is required when applicability is not_applicable")
        return self


class ProjectScopeItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    project_scope_id: uuid.UUID
    system_element_id: uuid.UUID
    base_element_revision_id: uuid.UUID | None
    target_element_revision_id: uuid.UUID | None
    change_type: str
    applicability: str
    rationale: str | None
    created_at: datetime
    updated_at: datetime
    acceptance_criteria: list[AcceptanceCriterionOut] = Field(default_factory=list)


class IdeaCreatedOut(BaseModel):
    product_id: uuid.UUID
    request: DevelopmentRequestOut
    concept: ProductConceptOut
    concept_revision: ConceptRevisionOut
    blueprint: SystemBlueprintOut
    blueprint_revision: BlueprintRevisionOut

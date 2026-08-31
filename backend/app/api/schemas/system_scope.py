"""Schemas for conception, System Blueprint, and Project Scope."""
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


JsonValue = dict[str, Any] | list[Any]


TechStackLayer = Literal[
    "frontend",
    "mobile",
    "backend",
    "database",
    "cache",
    "messaging",
    "auth",
    "storage",
    "search",
    "api_gateway",
    "deploy_infra",
    "cicd",
    "observability",
    "testing",
    "documentation",
]


class TechStackDecision(BaseModel):
    layer: TechStackLayer
    decision: str = Field(min_length=1, max_length=255)
    rationale: str | None = None


class TechStackOptionOut(BaseModel):
    id: uuid.UUID
    layer: TechStackLayer
    name: str
    description: str | None
    source: Literal["org_standard", "custom"]
    # Only meaningful for layer="frontend" -- a frontend scenario/toolchain,
    # not a separate layer. Null for every other layer and for an
    # unclassified frontend option (see TECH_STACK_OPTION_PLATFORMS's docstring).
    platform: Literal["web_app", "landing_page", "institutional_site", "pwa", "mobile"] | None = None
    model_config = ConfigDict(from_attributes=True)


class TechStackOptionCreate(BaseModel):
    layer: TechStackLayer
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    platform: Literal["web_app", "landing_page", "institutional_site", "pwa", "mobile"] | None = None


class IdeaCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    problem_statement: str = Field(min_length=1)
    vision: str | None = None
    scope_summary: str | None = None
    requested_by: str | None = Field(default=None, max_length=255)
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    project_description: str | None = None
    working_directory_path: str | None = Field(default=None, max_length=1024)
    tech_stack_decisions: list[TechStackDecision] | None = None


class DevelopmentRequestUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    requested_by: str | None = Field(default=None, max_length=255)


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
    project_description: str | None = None
    working_directory_path: str | None = Field(default=None, max_length=1024)
    tech_stack_decisions: list[TechStackDecision] | None = None
    created_by: str | None = Field(default=None, max_length=255)


class ConceptRevisionOut(ConceptRevisionCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    concept_id: uuid.UUID
    revision: int
    content_hash: str
    created_at: datetime
    updated_at: datetime


class ConceptDocumentSummary(BaseModel):
    filename: str
    size: int
    updated_at: datetime


class ConceptDocumentOut(BaseModel):
    filename: str
    content: str
    updated_at: datetime


class ConceptDocumentWrite(BaseModel):
    content: str


class ConceptDeliveryMetadataUpdate(BaseModel):
    """Project setup metadata (where the code will live, chosen stack) --
    unlike problem_statement/vision/scope_summary, this is not part of the
    content a governed decision approves, so it can be edited in place on
    the current revision regardless of concept status (draft, in_review,
    approved...) without opening a new revision or disturbing content_hash."""
    project_description: str | None = None
    working_directory_path: str | None = Field(default=None, max_length=1024)
    tech_stack_decisions: list[TechStackDecision] | None = None


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


class SystemElementUpdate(BaseModel):
    spec_snapshot: dict[str, Any] | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    family: str | None = Field(default=None, min_length=1, max_length=30)
    element_type: str | None = Field(default=None, min_length=1, max_length=40)
    stable_key: str | None = Field(default=None, min_length=1, max_length=160, pattern=r"^[a-z0-9][a-z0-9._-]*$")


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


class BlueprintSummaryOut(BaseModel):
    summary: str


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


class ProjectSpec(BaseModel):
    """One Project to create/reuse under the authorized ProductVersion --
    :authorize-delivery-planning accepts a list of these so a single
    Concept approval can produce one Project per application type (2026-08-01
    decision, see docs/architecture/PLANNING_DELIVERY_ARCHITECTURE.md section
    2.2's note and docs/modules/01_CONCEPTION_AND_SYSTEM_SCOPE.md)."""
    solution_type: Literal[
        "web_app",
        "mobile_app",
        "api_service",
        "database",
        "deploy",
        "automation",
        "data_migration",
        "data_analysis",
        "reporting",
    ]
    project_name: str = Field(min_length=1, max_length=255)
    project_description: str | None = None
    owner: str | None = Field(default=None, max_length=255)
    working_directory_path: str | None = Field(default=None, max_length=1024)
    # When set: a ProjectAgentMembership is created for this agent on the new
    # Project (role derived from solution_type), and every ProjectTask this
    # authorization creates in that Project's scope gets an automatic
    # TaskAssignment to the same agent (2026-08-01 Pacote 3 decision).
    responsible_agent_id: uuid.UUID | None = None
    # creation | maintenance -- whether this Project stands up something new
    # or evolves something already shipped (2026-08-15, Marcelo: "o ciclo é
    # o mesmo para os dois, finalizado pelos controles de versão"). Kept
    # per-project, not per-submission, since one idea can produce a new
    # web app alongside a maintenance change to an existing API.
    project_type: Literal["creation", "maintenance"] = "creation"


class AuthorizeDeliveryPlanning(BaseModel):
    version: str = Field(min_length=1, max_length=50)
    projects: list[ProjectSpec] = Field(min_length=1)
    # Chosen once for the whole submission (Conception's Pipeline/Template
    # section is presented first and "drives" the idea, 2026-08-15) and
    # applied to every Project this call creates -- unlike project_type,
    # this is deliberately not per-spec so it's never asked twice.
    pipeline_template_id: uuid.UUID | None = None


class ProjectAuthorizationResult(BaseModel):
    project_id: uuid.UUID
    project_scope_id: uuid.UUID
    solution_type: str
    scope_items_created: int = 0
    tasks_created: int = 0


class DeliveryPlanningAuthorizationOut(BaseModel):
    product_id: uuid.UUID
    product_version_id: uuid.UUID
    blueprint_revision_id: uuid.UUID
    projects: list[ProjectAuthorizationResult]


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


class ScreenAttribute(BaseModel):
    """One data field a screen exposes -- the input `derive-database` reads
    to propose `table`/`field` elements (see api/routes/system_scope.py's
    `derive_database`). Edited directly by the operator, no agent call."""
    name: str = Field(min_length=1, max_length=120)
    type: Literal["string", "number", "boolean", "date", "relation"] = "string"
    required: bool = False
    description: str | None = None
    relation_target_screen_id: uuid.UUID | None = None


class ScreenSpec(BaseModel):
    """Stored verbatim as a screen element's spec_snapshot. Two independent,
    optional prototype modes (a conceptual mockup, never the final
    implementation): free-form HTML (`prototype_html`/`css_framework`) for
    app-style screens, or `template_ref`/`image_refs` for site-style screens
    that point at a ready template + reference images instead."""
    attributes: list[ScreenAttribute] = Field(default_factory=list)
    prototype_html: str | None = None
    css_framework: str | None = None
    template_ref: str | None = None
    image_refs: list[str] = Field(default_factory=list)


class ScreenCreate(BaseModel):
    stable_key: str | None = Field(default=None, max_length=160, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    spec: ScreenSpec = Field(default_factory=ScreenSpec)


class ScreenUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    # Shallow merge onto the existing spec_snapshot (same idiom as
    # update_system_element's spec_snapshot merge) -- only the top-level
    # keys present here are replaced, so a client can patch just
    # `attributes` without resending prototype_html/css_framework/etc.
    spec: dict[str, Any] | None = None


class ScreenOut(BaseModel):
    scope_item_id: uuid.UUID
    element: SystemElementOut
    revision: ElementRevisionOut


class BusinessRuleOut(BaseModel):
    content: str
    updated_at: datetime | None = None
    file_path: str | None = None
    abs_path: str | None = None


class BusinessRuleWrite(BaseModel):
    content: str


class ArtifactSyncOut(BaseModel):
    project_id: uuid.UUID
    files_written: list[str] = Field(default_factory=list)


class DeriveDatabaseOut(BaseModel):
    revision_id: uuid.UUID
    tables_created: int = 0
    tables_updated: int = 0
    fields_written: int = 0


class IdeaCreatedOut(BaseModel):
    product_id: uuid.UUID
    request: DevelopmentRequestOut
    concept: ProductConceptOut
    concept_revision: ConceptRevisionOut
    blueprint: SystemBlueprintOut
    blueprint_revision: BlueprintRevisionOut


class ColumnCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    sql_type: str = Field(default="text")
    is_pk: bool = False
    is_fk: bool = False
    fk_ref_table: str = ""
    nullable: bool = True


class TableCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    stable_key: str | None = None
    initial_columns: list[ColumnCreate] | None = None

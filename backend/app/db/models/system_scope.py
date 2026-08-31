"""Conception, System Blueprint, and Project Scope domain models."""
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


DEVELOPMENT_REQUEST_TYPES = (
    "new_product", "feature", "bug", "maintenance", "research", "compliance", "incident_follow_up"
)
DEVELOPMENT_REQUEST_STATUSES = ("received", "triaging", "accepted", "rejected", "converted", "cancelled")
CONCEPT_STATUSES = ("draft", "in_review", "approved", "rework", "hold", "rejected", "superseded")
BLUEPRINT_REVISION_STATUSES = ("draft", "in_review", "approved", "superseded")
ELEMENT_LIFECYCLE_STATUSES = ("proposed", "active", "deprecated", "removed")
ELEMENT_FAMILIES = (
    "business", "process", "experience", "interface", "domain", "application", "data", "runtime", "assurance"
)
ELEMENT_TYPES = (
    "capability", "module", "persona",
    "journey", "process", "process_step", "use_case",
    "application", "channel", "route", "screen", "form", "report", "ui_component",
    "api", "endpoint", "command", "query", "event", "webhook", "integration",
    "domain_entity", "value_object", "business_rule", "authorization_rule",
    "service", "handler", "class", "method", "workflow", "job",
    "datastore", "schema", "table", "field", "index", "view", "procedure", "migration",
    "runtime_component", "queue", "cache", "deployment_unit", "environment_target",
    "test_scenario", "metric", "log_signal", "alert", "slo", "health_check",
)
RELATION_TYPES = (
    "contains", "precedes", "navigates_to", "invokes", "implements", "governed_by",
    "reads", "writes", "emits", "consumes", "depends_on", "persists_as", "runs_on",
    "deployed_to", "verified_by",
)
PROJECT_SCOPE_STATUSES = ("draft", "in_review", "baselined", "superseded")
SCOPE_CHANGE_TYPES = ("add", "modify", "remove", "deprecate", "verify")
SCOPE_APPLICABILITY = ("required", "optional", "not_applicable")
TECH_STACK_LAYERS = (
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
)
TECH_STACK_OPTION_SOURCES = ("org_standard", "custom")
TECH_STACK_OPTION_PLATFORMS = ("web_app", "landing_page", "institutional_site", "pwa", "mobile")


class DevelopmentRequest(Base, TimestampMixin):
    __tablename__ = "development_requests"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.products.id", ondelete="CASCADE"), nullable=False
    )
    request_type: Mapped[str] = mapped_column(String(40), nullable=False, default="new_product")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")
    source_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    requested_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="received")
    triage_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    __table_args__ = (
        CheckConstraint(f"request_type IN {DEVELOPMENT_REQUEST_TYPES!r}", name="ck_development_requests_type"),
        CheckConstraint(f"status IN {DEVELOPMENT_REQUEST_STATUSES!r}", name="ck_development_requests_status"),
    )


class ProductConcept(Base, TimestampMixin):
    __tablename__ = "product_concepts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.products.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    current_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "company.product_concept_revisions.id",
            name="fk_product_concepts_current_revision",
            ondelete="SET NULL",
            use_alter=True,
        ),
        nullable=True,
    )
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    __table_args__ = (
        CheckConstraint(f"status IN {CONCEPT_STATUSES!r}", name="ck_product_concepts_status"),
    )


class ProductConceptRevision(Base, TimestampMixin):
    __tablename__ = "product_concept_revisions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    concept_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.product_concepts.id", ondelete="CASCADE"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    problem_statement: Mapped[str] = mapped_column(Text, nullable=False)
    vision: Mapped[str | None] = mapped_column(Text, nullable=True)
    stakeholders: Mapped[list | dict | None] = mapped_column(JSONB, nullable=True)
    personas: Mapped[list | dict | None] = mapped_column(JSONB, nullable=True)
    objectives: Mapped[list | dict | None] = mapped_column(JSONB, nullable=True)
    success_metrics: Mapped[list | dict | None] = mapped_column(JSONB, nullable=True)
    constraints: Mapped[list | dict | None] = mapped_column(JSONB, nullable=True)
    assumptions: Mapped[list | dict | None] = mapped_column(JSONB, nullable=True)
    risks: Mapped[list | dict | None] = mapped_column(JSONB, nullable=True)
    scope_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Staged ahead of Project creation -- copied onto Project.description /
    # Project.working_directory_path by :authorize-delivery-planning, so the
    # Conception wizard can capture "what is this system and where does its
    # code live" before a real Project row exists (see AuthorizeDeliveryPlanning
    # schema, which already accepted these two fields with no UI to fill them).
    project_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    working_directory_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # List of {layer, decision, rationale} dicts, one per TECH_STACK_LAYERS
    # entry -- kept as JSONB like the sibling stakeholders/personas/etc.
    # fields above rather than a separate table, since it's the same
    # "flexible per-revision structured data" shape as those.
    tech_stack_decisions: Mapped[list | dict | None] = mapped_column(JSONB, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    __table_args__ = (
        UniqueConstraint("concept_id", "revision", name="uq_concept_revisions_concept_revision"),
    )


class SystemBlueprint(Base, TimestampMixin):
    __tablename__ = "system_blueprints"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.products.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    current_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "company.system_blueprint_revisions.id",
            name="fk_system_blueprints_current_revision",
            ondelete="SET NULL",
            use_alter=True,
        ),
        nullable=True,
    )


class SystemBlueprintRevision(Base, TimestampMixin):
    __tablename__ = "system_blueprint_revisions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    blueprint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.system_blueprints.id", ondelete="CASCADE"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    concept_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.product_concept_revisions.id", ondelete="SET NULL"), nullable=True
    )
    product_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.product_versions.id", ondelete="SET NULL"), nullable=True
    )
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    __table_args__ = (
        UniqueConstraint("blueprint_id", "revision", name="uq_blueprint_revisions_blueprint_revision"),
        CheckConstraint(f"status IN {BLUEPRINT_REVISION_STATUSES!r}", name="ck_blueprint_revisions_status"),
    )


class SystemElement(Base, TimestampMixin):
    __tablename__ = "system_elements"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.products.id", ondelete="CASCADE"), nullable=False
    )
    stable_key: Mapped[str] = mapped_column(String(160), nullable=False)
    family: Mapped[str] = mapped_column(String(30), nullable=False)
    element_type: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    lifecycle_status: Mapped[str] = mapped_column(String(30), nullable=False, default="proposed")
    criticality: Mapped[str] = mapped_column(String(20), nullable=False, default="standard")
    owner_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.system_elements.id", ondelete="SET NULL"), nullable=True
    )
    __table_args__ = (
        UniqueConstraint("product_id", "stable_key", name="uq_system_elements_product_stable_key"),
        CheckConstraint(f"family IN {ELEMENT_FAMILIES!r}", name="ck_system_elements_family"),
        CheckConstraint(f"element_type IN {ELEMENT_TYPES!r}", name="ck_system_elements_type"),
        CheckConstraint(f"lifecycle_status IN {ELEMENT_LIFECYCLE_STATUSES!r}", name="ck_system_elements_lifecycle"),
    )


class SystemElementRevision(Base, TimestampMixin):
    __tablename__ = "system_element_revisions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    system_element_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.system_elements.id", ondelete="CASCADE"), nullable=False
    )
    blueprint_revision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.system_blueprint_revisions.id", ondelete="CASCADE"), nullable=False
    )
    spec_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    source_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    __table_args__ = (
        UniqueConstraint("blueprint_revision_id", "system_element_id", name="uq_element_revisions_blueprint_element"),
    )


class SystemElementRelation(Base, TimestampMixin):
    __tablename__ = "system_element_relations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    blueprint_revision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.system_blueprint_revisions.id", ondelete="CASCADE"), nullable=False
    )
    from_element_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.system_elements.id", ondelete="CASCADE"), nullable=False
    )
    to_element_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.system_elements.id", ondelete="CASCADE"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(String(40), nullable=False)
    attributes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    __table_args__ = (
        UniqueConstraint(
            "blueprint_revision_id", "from_element_id", "to_element_id", "relation_type",
            name="uq_system_element_relations_revision_edge",
        ),
        CheckConstraint("from_element_id <> to_element_id", name="ck_system_element_relations_not_self"),
        CheckConstraint(f"relation_type IN {RELATION_TYPES!r}", name="ck_system_element_relations_type"),
    )


class ProjectScope(Base, TimestampMixin):
    __tablename__ = "project_scopes"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.projects.id", ondelete="CASCADE"), nullable=False
    )
    blueprint_base_revision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.system_blueprint_revisions.id", ondelete="RESTRICT"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    __table_args__ = (
        UniqueConstraint("project_id", "revision", name="uq_project_scopes_project_revision"),
        CheckConstraint(f"status IN {PROJECT_SCOPE_STATUSES!r}", name="ck_project_scopes_status"),
    )


class ProjectScopeItem(Base, TimestampMixin):
    __tablename__ = "project_scope_items"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_scope_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.project_scopes.id", ondelete="CASCADE"), nullable=False
    )
    system_element_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.system_elements.id", ondelete="RESTRICT"), nullable=False
    )
    base_element_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.system_element_revisions.id", ondelete="SET NULL"), nullable=True
    )
    target_element_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.system_element_revisions.id", ondelete="SET NULL"), nullable=True
    )
    change_type: Mapped[str] = mapped_column(String(30), nullable=False)
    applicability: Mapped[str] = mapped_column(String(30), nullable=False, default="required")
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (
        UniqueConstraint("project_scope_id", "system_element_id", name="uq_project_scope_items_scope_element"),
        CheckConstraint(f"change_type IN {SCOPE_CHANGE_TYPES!r}", name="ck_project_scope_items_change_type"),
        CheckConstraint(f"applicability IN {SCOPE_APPLICABILITY!r}", name="ck_project_scope_items_applicability"),
        CheckConstraint(
            "applicability <> 'not_applicable' OR rationale IS NOT NULL",
            name="ck_project_scope_items_na_rationale",
        ),
    )


class ScopeItemAcceptanceCriterion(Base, TimestampMixin):
    __tablename__ = "scope_item_acceptance_criteria"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_scope_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.project_scope_items.id", ondelete="CASCADE"), nullable=False
    )
    criterion: Mapped[str] = mapped_column(Text, nullable=False)
    verification_type: Mapped[str] = mapped_column(String(50), nullable=False, default="test")
    required: Mapped[bool] = mapped_column(nullable=False, default=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class TechStackOption(Base, TimestampMixin):
    """Catalog of pickable technology choices per TECH_STACK_LAYERS, backing
    Conception step 4's "Tech stack" fields. Replaces a free-text Input with a
    closed set the user picks from -- `source="org_standard"` rows are seeded
    from the org's architecture standard (stack/02-UI-DESIGN-SYSTEM-AND-
    TECHNOLOGY-SPEC.md §12/§17/§18) via migration; `source="custom"` rows are
    added ad hoc from the picker itself ("add to the catalog") and immediately
    reusable by any later concept. `decision`/`rationale` on
    ProductConceptRevision.tech_stack_decisions stay free-text JSON (a concept
    is a point-in-time record, not a live FK to this catalog) -- this table
    only feeds the picker's option list, it is never joined against."""
    __tablename__ = "tech_stack_options"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    layer: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="custom")
    # See TECH_STACK_OPTION_PLATFORMS -- only meaningful for layer="frontend".
    platform: Mapped[str | None] = mapped_column(String(20), nullable=True)
    __table_args__ = (
        UniqueConstraint("layer", "name", name="uq_tech_stack_options_layer_name"),
        CheckConstraint(f"layer IN {TECH_STACK_LAYERS!r}", name="ck_tech_stack_options_layer"),
        CheckConstraint(f"source IN {TECH_STACK_OPTION_SOURCES!r}", name="ck_tech_stack_options_source"),
        CheckConstraint(
            f"platform IS NULL OR platform IN {TECH_STACK_OPTION_PLATFORMS!r}", name="ck_tech_stack_options_platform"
        ),
    )

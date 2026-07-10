"""Backlog domain models: planning_items, feature_requests, bug_reports,
version_scope_items, triage_decisions.

Per SPEC.md section 4.4 / PRD.md section 4-5: a PlanningItem is the
generic entry point into version planning (feature, bug, hotfix,
improvement, technical_debt, refactoring, security_fix, research,
documentation). FeatureRequest and BugReport are specializations that
hold type-specific intake data and link 1:1 back to a PlanningItem once
triaged/converted (SPEC 8.1/8.2 flows: FeatureRequest/BugReport ->
PlanningItem -> version scope -> tasks).

Foreign keys to tables owned by OTHER domains (products, product_versions,
projects, agents/users) are declared as string references
("company.<table>.id") and NOT enforced via cross-module imports, per
foundation convention -- this avoids import-order coupling. SQLAlchemy
resolves them lazily once every domain's models are imported centrally
(app/db/models/__init__.py) by the wiring step.
"""
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

# Allowed planning item types (PRD 5.8 / SPEC 5.4).
PLANNING_ITEM_TYPES = (
    "feature",
    "bug",
    "hotfix",
    "improvement",
    "technical_debt",
    "refactoring",
    "security_fix",
    "research",
    "documentation",
)

# Lifecycle status for a planning item. Kept intentionally small: intake
# (new) -> triaged -> scoped into a version -> baselined -> in_progress ->
# done, with a terminal rejected/cancelled branch. Mirrors SPEC 6.3 (baseline
# rules) without gold-plating a full workflow engine.
PLANNING_ITEM_STATUSES = (
    "new",
    "triaged",
    "scoped",
    "baselined",
    "in_progress",
    "done",
    "rejected",
    "cancelled",
)

BUG_SEVERITIES = ("low", "medium", "high", "critical")

TRIAGE_OUTCOMES = ("accepted", "rejected", "deferred", "merged", "duplicate")


class PlanningItem(Base, TimestampMixin):
    """Generic entry point into version planning (SPEC 5.4, PRD 5.8).

    FeatureRequest and BugReport are specializations that point back to a
    PlanningItem (nullable FK on the specialization side) once an intake
    record has been triaged/converted -- see SPEC 8.1/8.2 flows.
    """

    __tablename__ = "planning_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    item_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="new", server_default="new"
    )
    priority: Mapped[str] = mapped_column(
        String(16), nullable=False, default="medium", server_default="medium"
    )

    # Other-domain FKs by string reference (no cross-module import).
    # project_id is required (core traceability invariant, CLAUDE.md /
    # SPEC 5.4) -- enforced at the API layer (app/api/routes/backlog.py),
    # not as a DB-level NOT NULL, per the foundation convention that
    # existence checks against another domain's table belong at the route
    # layer. target_version_id legitimately starts empty at intake and is
    # populated once the item is triaged/scoped into a version (SPEC 8.1
    # step 3), so it stays nullable here.
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.projects.id", ondelete="CASCADE"), nullable=True
    )
    target_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.product_versions.id", ondelete="SET NULL"), nullable=True
    )
    # Optional pointer to which part of the project's real structure
    # (Project domain's ProjectStructureNode) this planning item touches
    # -- e.g. a specific screen, module, or DB table.
    structure_node_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.project_structure_nodes.id", ondelete="SET NULL"), nullable=True
    )

    # Relative path (within the project's working_directory_path) where the
    # output of this planning item should be written -- e.g. "docs/api.md"
    # or "src/modules/auth/". Only meaningful for items that produce a
    # specific file/folder artifact (documentation, generated code, etc.).
    output_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Set once baseline approval happens (SPEC 6.3 rule 1: "Approved
    # planning becomes baseline"). Post-baseline edits should flow through
    # a Change Request in the Project domain, not a direct mutation here.
    baselined: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default="false"
    )

    __table_args__ = (
        CheckConstraint(
            f"item_type IN {PLANNING_ITEM_TYPES!r}", name="ck_planning_items_item_type"
        ),
        CheckConstraint(
            f"status IN {PLANNING_ITEM_STATUSES!r}", name="ck_planning_items_status"
        ),
    )


class FeatureRequest(Base, TimestampMixin):
    """Feature intake (SPEC 8.1 step 1). Converts into a PlanningItem."""

    __tablename__ = "feature_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    business_value: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Populated once converted into a PlanningItem (SPEC 8.1 step 2).
    planning_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.planning_items.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )


class BugReport(Base, TimestampMixin):
    """Bug intake (SPEC 8.2 step 1). Converts into a PlanningItem."""

    __tablename__ = "bug_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(
        String(16), nullable=False, default="medium", server_default="medium"
    )
    environment: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reproduction_steps: Mapped[str | None] = mapped_column(Text, nullable=True)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Other-domain FKs (product_versions) by string reference.
    detected_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.product_versions.id", ondelete="SET NULL"), nullable=True
    )
    # PRD 8.2 Bug Done: "fixed_in_version is populated" before closure.
    fixed_in_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.product_versions.id", ondelete="SET NULL"), nullable=True
    )

    # Populated once converted into a PlanningItem (SPEC 8.2 step 3).
    planning_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.planning_items.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )

    __table_args__ = (
        CheckConstraint(
            f"severity IN {BUG_SEVERITIES!r}", name="ck_bug_reports_severity"
        ),
    )


class VersionScopeItem(Base, TimestampMixin):
    """Scopes a PlanningItem into a specific product version (SPEC 8.1
    step 3: "Scope into a product version").

    A planning item may only be scoped into a given version once -- unique
    constraint on (planning_item_id, product_version_id).
    """

    __tablename__ = "version_scope_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    planning_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.planning_items.id", ondelete="CASCADE"), nullable=False
    )
    product_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.product_versions.id", ondelete="CASCADE"), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "planning_item_id",
            "product_version_id",
            name="uq_version_scope_items_planning_item_version",
        ),
    )


class TriageDecision(Base, TimestampMixin):
    """Records a triage decision made against a PlanningItem (SPEC 8.2
    step 2: "Triage severity and target fix version"; SPEC 5.4 generic
    triage for any planning item type).

    Kept append-only/auditable: one row per decision event rather than a
    single mutable "current decision" column on PlanningItem, so the
    decision history is preserved (SPEC 6.5 "every critical decision must
    be auditable" spirit applied to backlog triage as well).
    """

    __tablename__ = "triage_decisions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    planning_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.planning_items.id", ondelete="CASCADE"), nullable=False
    )
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        CheckConstraint(
            f"outcome IN {TRIAGE_OUTCOMES!r}", name="ck_triage_decisions_outcome"
        ),
    )

"""SQLAlchemy models for the Project domain.

Tables owned by this domain (per docs/SPEC.md section 4.2):
- projects
- project_plans
- plan_baselines
- change_requests

Business-rule context (SPEC.md section 6.3 Planning Rules):
1. Approved planning becomes baseline.
2. Post-baseline changes require a Change Request.
3. Change Requests must track scope, time, cost, feature additions/removals,
   critical bugs, agent changes, skill changes, architecture changes, and
   security changes.

Foreign keys into tables owned by OTHER domains (e.g. product_versions,
owned by the Product domain) are declared as string references
(``ForeignKey("company.product_versions.id")``) rather than importing the
other domain's model module, per the foundation's import-order convention.
SQLAlchemy resolves these lazily once every domain module has been imported
centrally (see app/db/models/__init__.py).
"""
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

PROJECT_STATUSES = ("planned", "active", "on_hold", "completed", "cancelled")

FORGEROUTER_TOOLS = ("claude", "codex", "antigravity")
PROJECT_PLAN_STATUSES = ("draft", "approved", "baselined", "superseded")
CHANGE_REQUEST_STATUSES = ("pending", "approved", "rejected", "applied")

# A ProjectStructureNode classifies one element of the project's real
# system/folder structure (e.g. a top-level folder, a module, a UI
# screen, a component, a DB table, a stored procedure) so it can be
# linked to a PlanningItem and, like an Artifact, flagged is_locked.
STRUCTURE_NODE_TYPES = (
    "folder",
    "module",
    "component",
    "screen",
    "table",
    "stored_procedure",
)


class Project(Base, TimestampMixin):
    """A bounded initiative associated with a product version.

    Example: "ForgeHub — Foundation MVP".
    """

    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(f"status IN {PROJECT_STATUSES!r}", name="ck_projects_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Product domain owns product_versions; referenced by string FK only.
    product_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.product_versions.id", ondelete="CASCADE"),
        nullable=False,
    )

    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # planned -> active -> on_hold -> completed -> cancelled
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="planned", server_default="planned"
    )

    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    target_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Where this project's real code/repo lives on disk, so ForgeHub (and
    # any agent consulting it) knows which working directory the
    # project's structure_nodes' `path` values are relative to.
    working_directory_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)


class ProjectPlan(Base, TimestampMixin):
    """Scope, schedule, baseline, and estimate planning for a project.

    A project may accumulate multiple plan revisions over time (e.g. an
    initial draft plan, later a revised plan after a change request), so
    this is a one-to-many from Project, not a 1:1.
    """

    __tablename__ = "project_plans"
    __table_args__ = (
        CheckConstraint(
            f"status IN {PROJECT_PLAN_STATUSES!r}", name="ck_project_plans_status"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.projects.id", ondelete="CASCADE"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    scope_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    estimated_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    estimated_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    estimated_cost: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)

    # draft -> approved -> baselined -> superseded
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="draft", server_default="draft"
    )

    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PlanBaseline(Base, TimestampMixin):
    """An immutable snapshot of an approved ProjectPlan.

    Business rule: a plan can only be baselined once it is approved
    (SPEC.md 6.3.1 "Approved planning becomes baseline"). Once a baseline
    exists for a plan, further plan mutation is expected to flow through a
    ChangeRequest (SPEC.md 6.3.2).
    """

    __tablename__ = "plan_baselines"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    project_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.project_plans.id", ondelete="CASCADE"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Frozen snapshot fields, captured at baseline time so later edits to
    # the live ProjectPlan row do not silently rewrite history.
    scope_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost_snapshot: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    end_date_snapshot: Mapped[date | None] = mapped_column(Date, nullable=True)

    frozen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )


class ChangeRequest(Base, TimestampMixin):
    """A registered post-baseline scope/time/cost deviation.

    Business rule (SPEC.md 6.3.3): Change Requests must track scope, time,
    cost, feature additions/removals, critical bugs, agent changes, skill
    changes, architecture changes, and security changes — modeled below as
    explicit boolean impact flags plus a free-text description/justification
    and numeric/date deltas.
    """

    __tablename__ = "change_requests"
    __table_args__ = (
        CheckConstraint(
            f"status IN {CHANGE_REQUEST_STATUSES!r}", name="ck_change_requests_status"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.projects.id", ondelete="CASCADE"),
        nullable=False,
    )

    plan_baseline_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.plan_baselines.id", ondelete="SET NULL"),
        nullable=True,
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Impact flags per SPEC 6.3.3.
    affects_scope: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    affects_schedule: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    affects_cost: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    adds_features: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    removes_features: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    introduces_critical_bug_fix: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    changes_agents: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    changes_skills: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    changes_architecture: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    changes_security: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Quantified deltas (optional — only filled in when the relevant impact
    # flag above is set).
    schedule_delta_days: Mapped[int | None] = mapped_column(nullable=True)
    cost_delta: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)

    # pending -> approved -> rejected -> applied
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending", server_default="pending"
    )

    requested_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProjectStructureNode(Base, TimestampMixin):
    """One element of a project's real system/folder structure.

    A self-referencing tree (via parent_node_id) documenting the actual
    working-directory layout of a project -- e.g. a top-level folder,
    a module, an individual screen/component, or a DB table/stored
    procedure -- so a PlanningItem (Backlog domain, string FK) can point
    at exactly which part of the system it touches, and a node can be
    flagged is_locked (mirrors Artifact.is_locked) to advise agents that
    this part of the system is finalized and must not be altered.
    """

    __tablename__ = "project_structure_nodes"
    __table_args__ = (
        CheckConstraint(
            f"node_type IN {STRUCTURE_NODE_TYPES!r}", name="ck_project_structure_nodes_node_type"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.projects.id", ondelete="CASCADE"), nullable=False
    )
    parent_node_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.project_structure_nodes.id", ondelete="SET NULL"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    node_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # Relative to the owning Project.working_directory_path.
    path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Advisory "do not touch" flag -- see Artifact.is_locked docstring.
    is_locked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )


class ProjectForgeRouterConfig(Base, TimestampMixin):
    """Per-project ForgeRouter integration state.

    One row per project (unique project_id FK). Created on first enable,
    kept through disable/re-enable cycles so configured_at history is
    preserved. Config files are written inside the project's
    working_directory_path (never in global user dirs).

    Tools:
      claude       → {project}/.claude/settings.local.json
      codex        → {project}/.codex/config.toml  (project-local override)
      antigravity  → {project}/.forgerouter/antigravity.env (shell-source)
    """

    __tablename__ = "project_forgerouter_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    api_key: Mapped[str | None] = mapped_column(String(500), nullable=True)

    claude_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    codex_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    antigravity_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    configured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

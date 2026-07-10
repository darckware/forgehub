"""Pydantic Create/Update/Read schemas for the Project domain.

Covers: Project (primary entity, full CRUD), ProjectPlan (nested under
Project, full CRUD), PlanBaseline (create/list + read), ChangeRequest
(create/list + read + status update).
"""
import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.models.project import (
    CHANGE_REQUEST_STATUSES,
    PROJECT_PLAN_STATUSES,
    PROJECT_STATUSES,
    STRUCTURE_NODE_TYPES,
)


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------
class ProjectBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    product_version_id: uuid.UUID
    owner: str | None = None
    status: str = "planned"
    start_date: date | None = None
    target_end_date: date | None = None
    working_directory_path: str | None = Field(default=None, max_length=1024)

    @model_validator(mode="after")
    def _validate_status(self) -> "ProjectBase":
        if self.status not in PROJECT_STATUSES:
            raise ValueError(f"status must be one of {PROJECT_STATUSES}")
        return self


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    owner: str | None = None
    status: str | None = None
    start_date: date | None = None
    target_end_date: date | None = None
    working_directory_path: str | None = Field(default=None, max_length=1024)

    @model_validator(mode="after")
    def _validate_status(self) -> "ProjectUpdate":
        if self.status is not None and self.status not in PROJECT_STATUSES:
            raise ValueError(f"status must be one of {PROJECT_STATUSES}")
        return self


class ProjectOut(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# ProjectPlan
# ---------------------------------------------------------------------------
class ProjectPlanBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    scope_summary: str | None = None
    estimated_start_date: date | None = None
    estimated_end_date: date | None = None
    estimated_cost: Decimal | None = None


class ProjectPlanCreate(ProjectPlanBase):
    pass


class ProjectPlanUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    scope_summary: str | None = None
    estimated_start_date: date | None = None
    estimated_end_date: date | None = None
    estimated_cost: Decimal | None = None
    status: str | None = None

    @model_validator(mode="after")
    def _validate_status(self) -> "ProjectPlanUpdate":
        if self.status is not None and self.status not in PROJECT_PLAN_STATUSES:
            raise ValueError(f"status must be one of {PROJECT_PLAN_STATUSES}")
        return self


class ProjectPlanOut(ProjectPlanBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    status: str
    approved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ProjectPlanApprove(BaseModel):
    """Body for POST /api/v1/projects/plans/{plan_id}/approve (no fields needed today,
    kept as an explicit model so the endpoint contract is stable if approval
    metadata — e.g. approver — is added later)."""

    pass


# ---------------------------------------------------------------------------
# PlanBaseline
# ---------------------------------------------------------------------------
class PlanBaselineBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class PlanBaselineCreate(PlanBaselineBase):
    project_plan_id: uuid.UUID


class PlanBaselineOut(PlanBaselineBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_plan_id: uuid.UUID
    scope_snapshot: str | None = None
    cost_snapshot: Decimal | None = None
    end_date_snapshot: date | None = None
    frozen_at: datetime
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# ChangeRequest
# ---------------------------------------------------------------------------
class ChangeRequestBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    justification: str | None = None
    affects_scope: bool = False
    affects_schedule: bool = False
    affects_cost: bool = False
    adds_features: bool = False
    removes_features: bool = False
    introduces_critical_bug_fix: bool = False
    changes_agents: bool = False
    changes_skills: bool = False
    changes_architecture: bool = False
    changes_security: bool = False
    schedule_delta_days: int | None = None
    cost_delta: Decimal | None = None
    requested_by: str | None = None


class ChangeRequestCreate(ChangeRequestBase):
    plan_baseline_id: uuid.UUID | None = None


class ChangeRequestUpdate(BaseModel):
    """Partial update for a ChangeRequest.

    Content fields (title/justification/impact flags/deltas/etc.) are only
    accepted by the route while the CR is still "pending" -- once a
    decision (approved/rejected/applied) has been recorded, content is
    frozen, mirroring the plan/baseline immutability rule (SPEC.md 6.3.2).
    `status` itself is always accepted (that's how a decision gets made).
    """

    title: str | None = Field(None, min_length=1, max_length=255)
    justification: str | None = None
    plan_baseline_id: uuid.UUID | None = None
    affects_scope: bool | None = None
    affects_schedule: bool | None = None
    affects_cost: bool | None = None
    adds_features: bool | None = None
    removes_features: bool | None = None
    introduces_critical_bug_fix: bool | None = None
    changes_agents: bool | None = None
    changes_skills: bool | None = None
    changes_architecture: bool | None = None
    changes_security: bool | None = None
    schedule_delta_days: int | None = None
    cost_delta: Decimal | None = None
    requested_by: str | None = None
    status: str | None = None

    @model_validator(mode="after")
    def _validate_status(self) -> "ChangeRequestUpdate":
        if self.status is not None and self.status not in CHANGE_REQUEST_STATUSES:
            raise ValueError(f"status must be one of {CHANGE_REQUEST_STATUSES}")
        return self


class ChangeRequestOut(ChangeRequestBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    plan_baseline_id: uuid.UUID | None = None
    status: str
    decided_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# ProjectStructureNode
# ---------------------------------------------------------------------------
class ProjectStructureNodeBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    node_type: str = Field(..., description=f"One of {STRUCTURE_NODE_TYPES}")
    parent_node_id: uuid.UUID | None = None
    path: str | None = Field(default=None, max_length=1024)
    description: str | None = None
    is_locked: bool = False

    @model_validator(mode="after")
    def _validate_node_type(self) -> "ProjectStructureNodeBase":
        if self.node_type not in STRUCTURE_NODE_TYPES:
            raise ValueError(f"node_type must be one of {STRUCTURE_NODE_TYPES}")
        return self


class ProjectStructureNodeCreate(ProjectStructureNodeBase):
    pass


class ProjectStructureNodeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    node_type: str | None = None
    parent_node_id: uuid.UUID | None = None
    path: str | None = Field(default=None, max_length=1024)
    description: str | None = None
    is_locked: bool | None = None

    @model_validator(mode="after")
    def _validate_node_type(self) -> "ProjectStructureNodeUpdate":
        if self.node_type is not None and self.node_type not in STRUCTURE_NODE_TYPES:
            raise ValueError(f"node_type must be one of {STRUCTURE_NODE_TYPES}")
        return self


class ProjectStructureNodeOut(ProjectStructureNodeBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Project working-directory file browser (proxied through the host chat
# bridge -- see api/routes/project.py's "Project file browser" section and
# host-bridge/app.py's /v1/fs/* routes). Every path here is relative to the
# owning Project.working_directory_path, never an absolute host path.
# ---------------------------------------------------------------------------
class ProjectFileEntry(BaseModel):
    name: str
    path: str
    type: str  # "file" | "dir"
    size: int | None = None


class ProjectFileListing(BaseModel):
    path: str
    entries: list[ProjectFileEntry]


class ProjectFileContent(BaseModel):
    path: str
    content: str


class ProjectFileContentUpdate(BaseModel):
    content: str


class ProjectFileCreate(BaseModel):
    path: str = Field(..., min_length=1, max_length=1024)


class ProjectFileRename(BaseModel):
    path: str = Field(..., min_length=1, max_length=1024)
    new_path: str = Field(..., min_length=1, max_length=1024)


# ---------------------------------------------------------------------------
# Project ForgeRouter integration
# ---------------------------------------------------------------------------
class ProjectForgeRouterConfigOut(BaseModel):
    """Per-project ForgeRouter integration state (DB-stored record)."""

    model_config = ConfigDict(from_attributes=True)

    project_id: uuid.UUID
    api_key: str | None
    claude_enabled: bool
    codex_enabled: bool
    antigravity_enabled: bool
    configured_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ProjectForgeRouterToggle(BaseModel):
    """Request body to enable/disable ForgeRouter for a project.

    `enabled=False` disables all tools and removes their config files.
    Per-tool flags only take effect when `enabled=True`.
    """

    enabled: bool
    api_key: str = ""
    claude: bool = True
    codex: bool = True
    antigravity: bool = False


class ProjectForgeRouterStatusOut(BaseModel):
    """Live file-system status of ForgeRouter config files for a project."""

    project_path: str
    claude: bool
    codex: bool
    antigravity: bool
    claude_config_path: str
    codex_config_path: str
    antigravity_env_path: str


class ForgeRouterGlobalAuditOut(BaseModel):
    """Result of scanning for global ForgeRouter configurations."""

    clean: bool
    findings: list[dict]

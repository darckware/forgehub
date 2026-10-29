"""Pydantic schemas for the Mission domain (M0.0, MCP_MISSION_TOOLS_SPEC.md §2-§3.1)."""
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.mission import MISSION_RISK_LEVELS, MISSION_STATES, PLANNING_STAGES, REVIEW_LAYERS


class MissionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_version_id: uuid.UUID
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    orchestrator_agent_id: uuid.UUID
    priority: int = Field(default=100, ge=1, le=1000)
    # Validated by the route (422 AUTONOMY_LEVEL_NOT_ALLOWED) so the refusal
    # carries the mission error contract rather than a generic schema error.
    autonomy_level: str = "N0"
    brief_artifact_id: uuid.UUID | None = None
    deadline_at: datetime | None = None
    budget_limit: Decimal | None = Field(default=None, ge=0)
    working_directory_path: str | None = Field(default=None, max_length=1024)
    executor_project_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)


class MissionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_row_version: int
    priority: int | None = Field(default=None, ge=1, le=1000)
    autonomy_level: str | None = None
    brief_artifact_id: uuid.UUID | None = None
    deadline_at: datetime | None = None
    budget_limit: Decimal | None = Field(default=None, ge=0)
    risk_level: str | None = Field(default=None, pattern=f"^({'|'.join(MISSION_RISK_LEVELS)})$")
    required_review_layers: list[str] | None = None
    reason: str | None = Field(default=None, max_length=4000)


class MissionTransitionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to: str = Field(pattern=f"^({'|'.join(MISSION_STATES)})$")
    reason: str | None = Field(default=None, max_length=4000)
    expected_row_version: int


class PlanningAdvanceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to: str = Field(pattern=f"^({'|'.join(PLANNING_STAGES)})$")
    reason: str = Field(min_length=1, max_length=4000)
    idempotency_key: str = Field(min_length=1, max_length=150)
    expected_row_version: int | None = None


class MissionOut(BaseModel):
    project_id: uuid.UUID
    name: str
    project_type: str
    project_status: str
    state: str
    paused_from_state: str | None
    planning_stage: str | None
    risk_level: str | None
    required_review_layers: list[str]
    priority: int
    orchestrator_agent_id: uuid.UUID
    autonomy_level: str
    brief_artifact_id: uuid.UUID | None
    current_baseline_id: uuid.UUID | None
    deadline_at: datetime | None
    budget_limit: Decimal | None
    paused_seconds: int
    state_changed_at: datetime
    state_reason: str | None
    row_version: int
    executor_project_ids: list[uuid.UUID]


class PlanningAdvanceOut(BaseModel):
    mission: MissionOut
    decision_id: uuid.UUID
    replayed: bool = False
    not_evaluated: list[dict] = Field(default_factory=list)


REVIEW_LAYER_SET = frozenset(REVIEW_LAYERS)

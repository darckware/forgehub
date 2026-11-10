"""Pydantic schemas for the orchestrator decision cycle (Plano Integrado M0.8).

Contract: docs/architecture/MISSION_ORCHESTRATOR_CYCLE_SPEC.md §2.3, §4, §5, §7.
"""
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.mission_cycle import N0_ACTIONS
from app.db.models.mission_cycle import SKILL_PROPOSAL_KINDS


class DecisionParams(BaseModel):
    """The action's own arguments; each action reads only its own."""

    model_config = ConfigDict(extra="forbid")

    execution_id: uuid.UUID | None = None
    reviewer_agent_id: uuid.UUID | None = None
    replace_review_id: uuid.UUID | None = None
    agent_id: uuid.UUID | None = None
    demand_id: uuid.UUID | None = None
    scheduled_at: datetime | None = None
    command_text: str | None = Field(default=None, max_length=4000)
    # ask_marcelo (§3.7)
    question: str | None = Field(default=None, max_length=4000)
    context: str | None = Field(default=None, max_length=4000)
    options: list[str] | None = Field(default=None, max_length=6)
    recommendation: str | None = Field(default=None, max_length=2000)
    default_action: str | None = Field(default=None, max_length=1000)
    default_reversible: bool | None = None
    answer_by: datetime | None = None
    dependent_task_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    urgent: bool = False
    reask_of: uuid.UUID | None = None


class DecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str = Field(pattern=f"^({'|'.join(N0_ACTIONS)})$")
    reason: str = Field(min_length=1, max_length=2000)
    idempotency_key: str = Field(min_length=1, max_length=140)
    cycle_id: uuid.UUID | None = None
    proposal_id: str | None = Field(default=None, max_length=32)
    task_id: uuid.UUID | None = None
    expected_context_version: int | None = Field(default=None, ge=0)
    params: DecisionParams = Field(default_factory=DecisionParams)


class DecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    mission_project_id: uuid.UUID
    cycle_id: uuid.UUID | None = None
    action: str
    status: str
    refusal_code: str | None = None
    reason: str
    facts: dict[str, Any] | None = None
    task_id: uuid.UUID | None = None
    demand_id: uuid.UUID | None = None
    review_id: uuid.UUID | None = None
    question_id: uuid.UUID | None = None
    actor_type: str
    actor_name: str
    authority_source: str
    undone_by_decision_id: uuid.UUID | None = None
    created_at: datetime


class CycleOut(BaseModel):
    project_id: uuid.UUID
    cycle_id: uuid.UUID | None = None
    mission_state: str
    autonomy_level: str
    locked: dict[str, Any] | None = None
    board: list[dict[str, Any]]
    board_hash: str
    proposals: list[dict[str, Any]]
    context_version: dict[str, Any] | None = None
    watchdog: list[dict[str, Any]]


class UndoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=2000)


class CycleLockIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=2000)
    until: datetime | None = None


class CycleUnlockIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=2000)


class CycleLockOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    mission_project_id: uuid.UUID
    task_id: uuid.UUID | None = None
    locked_by: str
    reason: str
    locked_until: datetime | None = None
    released_at: datetime | None = None
    released_by: str | None = None


class AvailabilityIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # None clears it (the agent is available again).
    until: datetime | None
    reason: str = Field(min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=1, max_length=150)


class AvailabilityOut(BaseModel):
    agent_id: uuid.UUID
    unavailable_until: datetime | None = None
    reason: str | None = None
    recorded_by: str | None = None


class SkillProposalIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(pattern=f"^({'|'.join(SKILL_PROPOSAL_KINDS)})$")
    task_id: uuid.UUID | None = None
    skill_id: uuid.UUID | None = None
    agent_id: uuid.UUID | None = None
    reason: str = Field(min_length=1, max_length=2000)
    idempotency_key: str = Field(min_length=1, max_length=140)
    cycle_id: uuid.UUID | None = None


class SkillProposalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    mission_project_id: uuid.UUID
    task_id: uuid.UUID | None = None
    kind: str
    skill_id: uuid.UUID | None = None
    agent_id: uuid.UUID | None = None
    owner_agent_id: uuid.UUID | None = None
    reason: str
    status: str
    demand_id: uuid.UUID | None = None


class MissionDependencyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    depends_on_mission_project_id: uuid.UUID
    reason: str = Field(min_length=1, max_length=2000)


class MissionDependencyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    mission_project_id: uuid.UUID
    depends_on_mission_project_id: uuid.UUID
    created_by: str

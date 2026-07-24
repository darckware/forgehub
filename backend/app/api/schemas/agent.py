"""Pydantic Create/Update/Read schemas for the Agent domain.

Covers: agents (primary, full CRUD + nested sub_agents/skills), sub_agents,
skills, agent_skills, sub_agent_skills, agent_cost_rates, agent_capacities.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models.agent import (
    AGENT_RUNTIME_TYPES,
    AGENT_STATUSES,
    AGENT_TYPES,
    COST_RATE_UNITS,
    SKILL_ORIGINS,
    SKILL_RISK_LEVELS,
)


def _validate_choice(value: str, choices: tuple[str, ...], field_name: str) -> str:
    if value not in choices:
        raise ValueError(f"{field_name} must be one of {choices}")
    return value


# ---------------------------------------------------------------------------
# Skill
# ---------------------------------------------------------------------------


class SkillBase(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    version: str = Field(min_length=1, max_length=50)
    description: str | None = None
    origin: str
    risk_level: str
    permissions: str = Field(min_length=1)

    @field_validator("origin")
    @classmethod
    def _check_origin(cls, v: str) -> str:
        return _validate_choice(v, SKILL_ORIGINS, "origin")

    @field_validator("risk_level")
    @classmethod
    def _check_risk_level(cls, v: str) -> str:
        return _validate_choice(v, SKILL_RISK_LEVELS, "risk_level")


class SkillCreate(SkillBase):
    # Skills cannot be self-approved at creation time (SPEC 6.5 rule 5/6).
    pass


class SkillUpdate(BaseModel):
    """Partial update. If the target skill is already approved, the route
    layer rejects any field here except is_approved/security_reviewed
    (SPEC 6.5 rule 8: approved skills must not change without a new
    version)."""

    name: str | None = Field(default=None, min_length=1, max_length=150)
    version: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = None
    origin: str | None = None
    risk_level: str | None = None
    permissions: str | None = Field(default=None, min_length=1)
    is_approved: bool | None = None
    security_reviewed: bool | None = None

    @field_validator("origin")
    @classmethod
    def _check_origin(cls, v: str | None) -> str | None:
        return v if v is None else _validate_choice(v, SKILL_ORIGINS, "origin")

    @field_validator("risk_level")
    @classmethod
    def _check_risk_level(cls, v: str | None) -> str | None:
        return (
            v if v is None else _validate_choice(v, SKILL_RISK_LEVELS, "risk_level")
        )


class SkillOut(SkillBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    is_approved: bool
    security_reviewed: bool
    created_at: datetime
    updated_at: datetime


class SkillAgentRef(BaseModel):
    """Agent granted a skill (via agent_skills), embedded in skill listings
    so the Skills page can show/filter by the agents that hold each skill
    without one request per skill."""

    agent_id: uuid.UUID
    agent_name: str


class SkillWithAgentsOut(SkillOut):
    agents: list[SkillAgentRef] = []


# ---------------------------------------------------------------------------
# AgentSkill / SubAgentSkill (associations)
# ---------------------------------------------------------------------------


class AgentSkillCreate(BaseModel):
    skill_id: uuid.UUID
    inheritable: bool = False


class AgentSkillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    skill_id: uuid.UUID
    inheritable: bool
    created_at: datetime
    updated_at: datetime


class SubAgentSkillCreate(BaseModel):
    skill_id: uuid.UUID


class SubAgentSkillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sub_agent_id: uuid.UUID
    skill_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# SubAgent
# ---------------------------------------------------------------------------


class SubAgentBase(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = None
    status: str = "active"
    permission_scope: str | None = None
    is_active: bool = True

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: str) -> str:
        return _validate_choice(v, AGENT_STATUSES, "status")


class SubAgentCreate(SubAgentBase):
    skill_ids: list[uuid.UUID] = Field(default_factory=list)


class SubAgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = None
    status: str | None = None
    permission_scope: str | None = None
    is_active: bool | None = None

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: str | None) -> str | None:
        return v if v is None else _validate_choice(v, AGENT_STATUSES, "status")


class SubAgentOut(SubAgentBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# AgentCostRate
# ---------------------------------------------------------------------------


class AgentCostRateBase(BaseModel):
    rate_unit: str
    rate_amount: float = Field(ge=0)
    currency: str = Field(default="USD", min_length=1, max_length=10)
    is_active: bool = True

    @field_validator("rate_unit")
    @classmethod
    def _check_rate_unit(cls, v: str) -> str:
        return _validate_choice(v, COST_RATE_UNITS, "rate_unit")


class AgentCostRateCreate(AgentCostRateBase):
    pass


class AgentCostRateOut(AgentCostRateBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# AgentCapacity
# ---------------------------------------------------------------------------


class AgentCapacityBase(BaseModel):
    max_concurrent_tasks: int = Field(default=1, ge=1)
    max_daily_tasks: int | None = Field(default=None, ge=1)
    notes: str | None = None


class AgentCapacityCreate(AgentCapacityBase):
    pass


class AgentCapacityUpdate(BaseModel):
    max_concurrent_tasks: int | None = Field(default=None, ge=1)
    max_daily_tasks: int | None = Field(default=None, ge=1)
    notes: str | None = None


class AgentCapacityOut(AgentCapacityBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Agent (primary entity)
# ---------------------------------------------------------------------------


class AgentBase(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = None
    agent_type: str = "executor"
    status: str = "active"
    is_active: bool = True

    @field_validator("agent_type")
    @classmethod
    def _check_agent_type(cls, v: str) -> str:
        return _validate_choice(v, AGENT_TYPES, "agent_type")

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: str) -> str:
        return _validate_choice(v, AGENT_STATUSES, "status")


class AgentCreate(AgentBase):
    forgerouter_api_key: str | None = Field(default=None, min_length=1, max_length=1000)


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = None
    agent_type: str | None = None
    status: str | None = None
    is_active: bool | None = None
    forgerouter_api_key: str | None = Field(default=None, min_length=1, max_length=1000)
    clear_forgerouter_api_key: bool = False
    runtime_type: str | None = None

    @field_validator("agent_type")
    @classmethod
    def _check_agent_type(cls, v: str | None) -> str | None:
        return v if v is None else _validate_choice(v, AGENT_TYPES, "agent_type")

    @field_validator("runtime_type")
    @classmethod
    def _check_runtime_type(cls, v: str | None) -> str | None:
        return v if v is None else _validate_choice(v, AGENT_RUNTIME_TYPES, "runtime_type")

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: str | None) -> str | None:
        return v if v is None else _validate_choice(v, AGENT_STATUSES, "status")


class AgentOut(AgentBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    # Hermes Foundation metadata -- read-only, populated/refreshed only by
    # POST /api/v1/agents/sync/hermes-foundation (app/core/hermes_sync.py).
    # Not part of AgentCreate/AgentUpdate.
    profile_slug: str | None = None
    layer: str | None = None
    runtime_tier: str | None = None
    telegram_required: bool = False
    has_profile: bool = False
    mission: str | None = None
    source_path: str | None = None
    department: str | None = None
    sector: str | None = None
    reports_to_profile_slug: str | None = None
    forgerouter_api_key_configured: bool = False
    # See AGENT_RUNTIME_TYPES (db/models/agent.py) -- only set for agents
    # with a stateless single-shot CLI dispatch mode (Inbox dispatch target
    # eligibility, api/routes/demand.py's /dispatch).
    runtime_type: str | None = None


class AgentListItemOut(AgentOut):
    """Agent as returned by the list endpoint -- includes sub_agents (for
    rendering the parent/child hierarchy in the Agents list) but, unlike
    AgentDetailOut, omits agent_skills/cost_rates/capacities to keep the
    list query light (an agent can have 100+ skill grants)."""

    sub_agents: list[SubAgentOut] = Field(default_factory=list)


class AgentDetailOut(AgentOut):
    """Agent with nested sub_agents and granted skills (agent_skills)."""

    sub_agents: list[SubAgentOut] = Field(default_factory=list)
    agent_skills: list[AgentSkillOut] = Field(default_factory=list)
    cost_rates: list[AgentCostRateOut] = Field(default_factory=list)
    capacities: list[AgentCapacityOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Hermes Foundation sync result
# ---------------------------------------------------------------------------


class SyncCounts(BaseModel):
    created: int = 0
    updated: int = 0


class HermesSyncResultOut(BaseModel):
    agents: SyncCounts
    sub_agents: SyncCounts
    skills: SyncCounts
    agent_skills: SyncCounts
    warnings: list[str] = Field(default_factory=list)

"""Pydantic schemas for the Operations domain (24x7 agent operation)."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.routine_schedule import validate_schedule

Escalation = Literal["telegram_direct", "via_athos"]
RoutineKind = Literal["monitoring", "maintenance", "improvement", "report", "coordination"]


class Coordination(BaseModel):
    agent: str = Field(min_length=1, max_length=50)
    purpose: str = Field(min_length=1)


class CharterIn(BaseModel):
    mission: str = Field(min_length=1)
    responsibilities: list[str] = []
    monitored_domains: list[str] = []
    coordinates_with: list[Coordination] = []
    never_does: list[str] = []
    daily_run_budget: int = Field(default=24, ge=0, le=500)
    daily_cost_budget: Decimal = Field(default=Decimal("2.00"), ge=0, le=1000)
    escalation: Escalation = "via_athos"


class CharterOut(CharterIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    agent_name: str | None = None
    # Derived from audit_checks.agent_profile, never edited by hand.
    owned_audit_checks: list[str] = []
    updated_at: datetime


class RoutineBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    instructions: str = Field(min_length=1)
    schedule: str = Field(min_length=9, max_length=100)
    timezone: str = Field(default="America/Sao_Paulo", max_length=50)
    kind: RoutineKind = "monitoring"
    expected_evidence: str | None = None
    linked_audit_checks: list[str] = []
    enabled: bool = True
    priority: int = Field(default=0, ge=-10, le=10)
    deadline_minutes: int = Field(default=60, ge=5, le=1440)


class RoutineCreate(RoutineBase):
    agent_id: uuid.UUID

    @model_validator(mode="after")
    def _check_schedule(self) -> "RoutineCreate":
        validate_schedule(self.schedule, self.timezone)
        return self


class RoutineUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    instructions: str | None = Field(default=None, min_length=1)
    schedule: str | None = Field(default=None, min_length=9, max_length=100)
    timezone: str | None = Field(default=None, max_length=50)
    kind: RoutineKind | None = None
    expected_evidence: str | None = None
    linked_audit_checks: list[str] | None = None
    enabled: bool | None = None
    priority: int | None = Field(default=None, ge=-10, le=10)
    deadline_minutes: int | None = Field(default=None, ge=5, le=1440)


class RoutineOut(RoutineBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    agent_name: str | None = None
    last_occurrence_at: datetime | None
    next_occurrences: list[datetime] = []
    created_at: datetime
    updated_at: datetime


class RoutineRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    routine_id: uuid.UUID
    routine_title: str | None = None
    agent_id: uuid.UUID | None = None
    agent_name: str | None = None
    occurrence_at: datetime
    status: str
    demand_id: uuid.UUID | None
    demand_number: int | None = None
    detail: str | None
    finished_at: datetime | None
    # Still waiting in the Messages queue past occurrence + deadline.
    overdue: bool = False


class PolicyIn(BaseModel):
    content: str = Field(min_length=1)
    change_reason: str | None = None


class PolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version: int
    content: str
    author: str
    change_reason: str | None
    created_at: datetime


class AgentOperationsSummary(BaseModel):
    agent_id: uuid.UUID
    agent_name: str
    profile_slug: str | None
    runtime_type: str | None
    has_charter: bool
    routines_enabled: int
    routines_total: int
    today: dict[str, int]
    daily_run_budget: int | None
    runs_counted_today: int


class OperationsOverview(BaseModel):
    agents: list[AgentOperationsSummary]
    policy_version: int | None


class QuestionAskIn(BaseModel):
    """Bridge-token body of the MCP `ask_marcelo` tool."""

    agent: str = Field(min_length=1, max_length=50)
    question: str = Field(min_length=1, max_length=4000)
    context: str | None = Field(default=None, max_length=8000)
    recommendation: str | None = Field(default=None, max_length=4000)
    blocking: bool = False
    urgent: bool = False
    # The Messages #number the agent was running when it asked, if any: the
    # answer task points back at it (reply_to_id).
    origin_message_number: int | None = None


class QuestionAnswerIn(BaseModel):
    answer: str = Field(min_length=1, max_length=8000)


class QuestionRelayAnswerIn(QuestionAnswerIn):
    # The agent whose Telegram conversation received Marcelo's reply.
    agent: str = Field(min_length=1, max_length=50)


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: int
    agent_id: uuid.UUID
    agent_name: str | None = None
    relay_agent_id: uuid.UUID | None
    relay_agent_name: str | None = None
    question: str
    context: str | None
    recommendation: str | None
    blocking: bool
    urgent: bool
    status: str
    notify_after: datetime
    telegram_sent_at: datetime | None
    telegram_error: str | None
    answer: str | None
    answered_at: datetime | None
    answered_via: str | None
    answered_by: str | None
    reply_demand_id: uuid.UUID | None
    created_at: datetime

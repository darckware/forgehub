"""Operations domain: 24x7 agent operation (spec
docs/superpowers/specs/2026-10-02-agent-operations-24x7-design.md).

Tables owned by this domain:
- agent_charters        one per agent: mission, standing duties, limits, budget
- agent_routines        recurring work an agent owes (cron schedule)
- agent_routine_runs    one row per occurrence, linked to the Messages task
- operations_policies   versioned shared instructions injected into every run
- agent_questions       an agent's question to Marcelo (MCP ask_marcelo), its
                        Telegram delivery and the answer routed back

Why it exists: on 2026-10-02 only Athos had any recurring job; every other
agent acted only when Marcelo asked ("inércia"). A routine never executes
anything itself -- each occurrence becomes an ordinary Messages Task
(AgentDemand, origin_type="task"), so Messages stays the single executor and
every run inherits its deadline, per-agent concurrency cap, failure
notification and Agent Activity visibility (see the "Every task is executed
through the Messages channel" rule in CLAUDE.md).

Idempotency is structural: (routine_id, occurrence_at) is UNIQUE, so a
generator pass that runs twice -- or two passes racing -- can never create
two tasks for the same occurrence.
"""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

CHARTER_ESCALATIONS = ("telegram_direct", "via_athos")
ROUTINE_KINDS = ("monitoring", "maintenance", "improvement", "report", "coordination")
ROUTINE_RUN_STATUSES = ("scheduled", "running", "completed", "failed", "missed", "skipped_budget")
ROUTINE_RUN_TERMINAL_STATUSES = ("completed", "failed", "missed", "skipped_budget")
QUESTION_STATUSES = ("pending", "answered", "cancelled")
QUESTION_ANSWER_CHANNELS = ("telegram", "screen")


class AgentCharter(Base, TimestampMixin):
    __tablename__ = "agent_charters"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agents.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    mission: Mapped[str] = mapped_column(Text, nullable=False)
    responsibilities: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    monitored_domains: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    # [{"agent": "<profile_slug>", "purpose": "..."}]
    coordinates_with: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    never_does: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    daily_run_budget: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    daily_cost_budget: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("2.00"))
    escalation: Mapped[str] = mapped_column(String(30), nullable=False, default="via_athos")

    __table_args__ = (
        CheckConstraint(f"escalation IN {CHARTER_ESCALATIONS!r}", name="ck_agent_charters_escalation"),
        CheckConstraint("daily_run_budget >= 0", name="ck_agent_charters_run_budget"),
        CheckConstraint("daily_cost_budget >= 0", name="ck_agent_charters_cost_budget"),
    )


class AgentRoutine(Base, TimestampMixin):
    __tablename__ = "agent_routines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    # Standard 5-field cron expression, evaluated in `timezone`.
    schedule: Mapped[str] = mapped_column(String(100), nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="America/Sao_Paulo")
    kind: Mapped[str] = mapped_column(String(30), nullable=False, default="monitoring")
    expected_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    linked_audit_checks: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deadline_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    # Generator cursor: the latest occurrence already materialized (or
    # skipped). NULL = never generated; the first pass starts from "now"
    # instead of back-filling every occurrence since the routine was created.
    last_occurrence_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    runs: Mapped[list["AgentRoutineRun"]] = relationship(back_populates="routine", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(f"kind IN {ROUTINE_KINDS!r}", name="ck_agent_routines_kind"),
        CheckConstraint("deadline_minutes > 0", name="ck_agent_routines_deadline"),
    )


class AgentRoutineRun(Base, TimestampMixin):
    __tablename__ = "agent_routine_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    routine_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agent_routines.id", ondelete="CASCADE"), nullable=False, index=True
    )
    occurrence_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="scheduled")
    demand_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agent_demands.id", ondelete="SET NULL"), nullable=True
    )
    # Why a run ended without executing (budget, missed window) or the
    # failure reason copied from the Messages task.
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    routine: Mapped[AgentRoutine] = relationship(back_populates="runs")

    __table_args__ = (
        UniqueConstraint("routine_id", "occurrence_at", name="uq_agent_routine_runs_occurrence"),
        CheckConstraint(f"status IN {ROUTINE_RUN_STATUSES!r}", name="ck_agent_routine_runs_status"),
    )


class OperationsPolicy(Base, TimestampMixin):
    """Shared instructions (communication, initiative, improvement, questions).
    Append-only: every edit is a new version, the highest one is in force, so
    the self-improvement loop can always restore an earlier text."""

    __tablename__ = "operations_policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str] = mapped_column(String(100), nullable=False, default="marcelo")
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class AgentQuestion(Base, TimestampMixin):
    """A question an agent needs Marcelo to answer (MCP `ask_marcelo`).

    Delivery is a column, not a log line: `telegram_sent_at` NULL on a
    pending question means the Telegram message is still owed, so a bridge
    outage or the 23:00-07:00 quiet window only delays it -- the delivery
    pass finds it again. `notify_after` holds that window: a non-urgent
    question asked at night waits for 07:00 instead of waking anyone.

    The answer reaches the agent as an ordinary Messages Task
    (`reply_demand_id`), so it resumes the blocked work through the same
    executor as everything else; that task's `reply_to_id` points back at the
    message the agent was running when it asked (`origin_demand_id`), when
    there was one.

    `relay_agent_id` is whose Telegram bot sent the question: the asker's own
    bot when its charter escalates `telegram_direct`, otherwise Athos's. A
    reply in Telegram arrives in *that* bot's conversation, so only that
    agent may record it (relay-answer route).
    """

    __tablename__ = "agent_questions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    number: Mapped[int] = mapped_column(Integer, Identity(always=False), unique=True, nullable=False)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relay_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agents.id", ondelete="SET NULL"), nullable=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    blocking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    urgent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    origin_demand_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agent_demands.id", ondelete="SET NULL"), nullable=True
    )
    notify_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    telegram_chat: Mapped[str | None] = mapped_column(String(100), nullable=True)
    telegram_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    telegram_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    answered_via: Mapped[str | None] = mapped_column(String(20), nullable=True)
    answered_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reply_demand_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agent_demands.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        CheckConstraint(f"status IN {QUESTION_STATUSES!r}", name="ck_agent_questions_status"),
        CheckConstraint(
            f"answered_via IS NULL OR answered_via IN {QUESTION_ANSWER_CHANNELS!r}",
            name="ck_agent_questions_answered_via",
        ),
        # An answered question always carries its answer; nothing else does.
        CheckConstraint(
            "(status = 'answered') = (answer IS NOT NULL AND answered_at IS NOT NULL)",
            name="ck_agent_questions_answer_present",
        ),
    )

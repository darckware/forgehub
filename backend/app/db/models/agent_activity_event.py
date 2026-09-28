"""AgentActivityEvent: one lifecycle event an agent runtime reported about itself.

Why this exists (2026-09-28, Marcelo: "O objetivo é o monitoramento completo dos
agentes... saber o que cada agente está fazendo, o que ele está processando, com quem
ele está conversando"): the Agent activity screen showed every agent as "Available"
because it only read TaskExecution/checkpoints, which almost no work goes through.
The real activity -- a turn in progress, the tool being run, the conversation it
belongs to -- only existed inside each runtime.

Hermes pushes it here through its native outbound webhooks (``hooks.outbound`` in each
profile's config.yaml -> ``POST /api/v1/agent-activity/events``, HMAC-signed), and this
table is ForgeHub's own record of it -- ForgeHub's Postgres is the system of record for
the ecosystem (Marcelo: "Use o banco de dados do forgehub, que é o responsável pelo
ecossistema"), so nothing reads a runtime's private session store.

Metadata only, by design: the webhook body carries the full conversation history, and
the route drops it. No message text, no tool arguments, no tool output is ever stored
-- Lara serves customers, and this screen is for operations, not for reading chats.
The counterpart is kept as a kind plus a masked reference (``···1234``).

Retention: ``AGENT_ACTIVITY_RETENTION_DAYS``, swept by ``run_agent_activity_retention``.
"""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

# Normalized from Hermes' hook names (pre_llm_call -> turn_started, ...), so a second
# runtime can report the same lifecycle without leaking Hermes' vocabulary.
AGENT_ACTIVITY_EVENT_KINDS = (
    "turn_started",
    "turn_ended",
    "tool_started",
    "tool_ended",
    "session_started",
)

AGENT_ACTIVITY_COUNTERPART_KINDS = ("owner", "human", "agent", "system")

AGENT_ACTIVITY_RETENTION_DAYS = 14


class AgentActivityEvent(Base, TimestampMixin):
    __tablename__ = "agent_activity_events"
    __table_args__ = (
        CheckConstraint(
            "kind IN (" + ", ".join(f"'{k}'" for k in AGENT_ACTIVITY_EVENT_KINDS) + ")",
            name="ck_agent_activity_events_kind",
        ),
        CheckConstraint(
            "counterpart_kind IS NULL OR counterpart_kind IN ("
            + ", ".join(f"'{k}'" for k in AGENT_ACTIVITY_COUNTERPART_KINDS)
            + ")",
            name="ck_agent_activity_events_counterpart_kind",
        ),
        Index("ix_agent_activity_events_agent_occurred", "agent_id", "occurred_at"),
        Index("ix_agent_activity_events_profile_occurred", "profile", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Nullable: an event from a profile no Agent row claims yet is still recorded (and
    # attributed by `profile`), rather than lost until someone registers the agent.
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agents.id", ondelete="SET NULL"), nullable=True
    )
    profile: Mapped[str] = mapped_column(String(100), nullable=False)
    runtime: Mapped[str] = mapped_column(String(30), nullable=False, default="hermes")

    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # The runtime's own ids, kept as opaque strings -- they correlate start/end pairs.
    session_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    turn_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # telegram | whatsapp | cli | tui | cron | api_server | kanban | subagent | ...
    platform: Mapped[str | None] = mapped_column(String(40), nullable=True)
    counterpart_kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    counterpart_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)

    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # tool_ended: ok | error ; turn_ended: completed | failed | interrupted
    status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # X-Hermes-Delivery: a webhook retry must not record the same event twice.
    delivery_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

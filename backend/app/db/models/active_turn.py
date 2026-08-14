"""ActiveTurn: the agent turn currently running for a chat session or a
channel, owned by the server rather than by whichever browser tab started it.

Why this exists (2026-08-13, Marcelo: "não é melhor eles trabalharem no
backend e posso fechar e abrir o frontend e ele voltar ao processamento e ao
contexto sem perder nada" / "não posso perder o contexto e o processamento
por um erro ou congelamento do frontend"):

The run already survives the client -- it is a subprocess on the host, held
in the bridge's own `_active_streams`. What did not survive was any *record*
of it: the processing bubble, the live text and the tool steps lived in React
state, so a reload, a crash or simply closing the tab left the screen blank
while the agent kept working. In a frozen frontend there is no chance to save
anything on the way out, which is exactly why the client cannot be the one
holding this.

Modelled on the Terminal, which already solves the same problem: a tmux
session on the host, a stable id, and `attach` to come back to it. This table
is the `tmux has-session` the chat never had -- the durable answer to "is
something running here, and what has it done so far?".

Deliberately one table for both surfaces (Marcelo: "um helper para os dois
chats conversation e channel"). They differ only in what they point at, which
is why the owner is a polymorphic (scope, scope_id) pair rather than two
nullable FKs -- the same convention governance.py's Approval/AuditEvent use
for the same reason.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

# Which surface owns the turn. "chat" -> ChatSession.id, "channel" ->
# ChatChannel.id. No real FK, on purpose: the target table is decided by
# this column, same convention as governance.py's (entity_type, entity_id).
ACTIVE_TURN_SCOPES = ("chat", "channel")

# running   -> the subprocess is alive and streaming
# completed -> finished normally; the reply is persisted as a real message
# failed    -> ended in error, or was found past its deadline
# cancelled -> the user stopped it
ACTIVE_TURN_STATUSES = ("running", "completed", "failed", "cancelled")

# How long a turn may stay "running" before a sweep declares it failed.
# The bridge holds its subprocess registry in memory, so a host-bridge
# restart loses the process while this row would still claim it is running --
# without a deadline those rows would stay "running" forever and every
# reconnect would wait on a stream nobody is producing. Same reasoning (and
# the same generous margin over the real limit) as the Messages domain's
# DISPATCH_TIMEOUT_MINUTES; the bridge's own CHAT_TIMEOUT_SECONDS is 600.
ACTIVE_TURN_TIMEOUT_MINUTES = 20


class ActiveTurn(Base, TimestampMixin):
    __tablename__ = "active_turns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    scope_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    # The bridge's own id for this run, minted per request by
    # hermes_stream.py and the key into `_active_streams`. This is what a
    # reconnecting client re-attaches by -- the equivalent of reusing the
    # tmux session name.
    stream_id: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")

    # What the user asked, kept so a client that reconnects can render the
    # pending bubble without having to guess which persisted message the
    # turn belongs to (it has none yet -- the reply is written at the end).
    prompt: Mapped[str] = mapped_column(Text, nullable=False)

    # Which agent is answering. Set for a chat turn, where exactly one agent
    # replies; NULL for a channel turn, where several run at once (see
    # `steps` below) and singling one out would be a lie.
    agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Mirrors the chat route's own `hidden` (an Assistant-panel priming turn,
    # never shown in the transcript). Needed so a turn ended by /turns/{id}/
    # stop -- which persists the partial reply itself, from this row, not
    # from the request that started the turn -- wraps it in the same
    # _HIDDEN_TURN markers the normal completion path would have used.
    # Without it, stopping a hidden turn mid-flight would leak its content
    # into the visible transcript.
    hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    # --- Particularidades de cada superfície ---
    # Chat only: a privileged-action approval the run is blocked on. A chat
    # turn can stop mid-stream waiting for a yes/no; reconnecting has to find
    # that prompt again, or the turn sits there forever waiting on an answer
    # the screen never asks for. Channels have no such pause.
    pending_approval: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # The trail so far: the tool steps accumulated while streaming. Written
    # as the turn progresses, not at the end -- this is what makes a
    # reconnect show *context* and not just a spinner, the same way `tmux
    # attach` repaints the pane instead of handing back an empty screen.
    # Shape mirrors the frontend's ChatQueueStep so no translation layer is
    # needed on either side.
    #
    # Every step carries `agent_id`, which is what keeps this table honest
    # for both surfaces: a chat turn has one agent and the field is
    # redundant, but a channel turn runs several in parallel (channel.py
    # gathers every mentioned agent at once, and `#all` broadcasts) and a
    # flat list without it would blend two agents' work into one trail with
    # no way to tell them apart.
    steps: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # Streamed reply text. Single-writer on chat; on a channel each agent
    # writes its own, so it is keyed by agent there -- see
    # core/active_turns.py's record_text, which owns that distinction so
    # callers on both sides stay identical.
    live_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    live_text_by_agent: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Cleared when the turn reaches a terminal state; a NULL deadline on a
    # "running" row means it predates this column, not that it never expires.
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # How many times a client re-attached. Not used for logic -- it is the
    # only way to tell "nobody ever came back" from "reconnected fine" when
    # diagnosing a report that the screen stayed empty.
    reattach_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        CheckConstraint(f"scope IN {ACTIVE_TURN_SCOPES}", name="ck_active_turns_scope"),
        CheckConstraint(f"status IN {ACTIVE_TURN_STATUSES}", name="ck_active_turns_status"),
        # The lookup every reconnect does: "what is running for this
        # session?". Partial, because only running rows are ever asked for
        # and finished ones are the overwhelming majority over time.
        Index(
            "ix_active_turns_running",
            "scope",
            "scope_id",
            postgresql_where=(status == "running"),
        ),
    )

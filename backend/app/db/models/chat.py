"""Chat domain models: chat_sessions, chat_messages.

A ChatSession pairs a ForgeHub Agent (which must have a profile_slug --
see app/db/models/agent.py) with a Hermes CLI session (hermes_session_id,
used for `hermes chat --resume <id>` so multi-turn context is preserved on
the real agent process, not just in this table). ChatMessage stores every
turn for the conversation history view; role distinguishes who sent it.

Conventions: same as every other domain (see app/db/models/agent.py
docstring) -- UUID PK with Python-side default, TimestampMixin for
created_at/updated_at, string-form FK to a sibling domain's table.
"""
import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

CHAT_MESSAGE_ROLES = ("user", "assistant")


class ChatSession(Base, TimestampMixin):
    """One conversation thread between a user and a single agent profile."""

    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agents.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(150), nullable=False, default="New chat")
    # Pinned chats sort to the top of the sidebar list, ahead of recency.
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Hermes CLI session id (e.g. "20260620_203829_9edb50"), captured from
    # the chat bridge's first reply and reused via --resume on every
    # subsequent turn. Null until the first message gets a reply.
    hermes_session_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    messages: Mapped[list["ChatMessage"]] = relationship(
        "ChatMessage", back_populates="session", cascade="all, delete-orphan", order_by="ChatMessage.created_at"
    )
    artifacts: Mapped[list["ChatArtifact"]] = relationship(
        "ChatArtifact", back_populates="session", cascade="all, delete-orphan", order_by="ChatArtifact.created_at"
    )
    participants: Mapped[list["ChatSessionParticipant"]] = relationship(
        "ChatSessionParticipant", back_populates="session", cascade="all, delete-orphan"
    )


class ChatMessage(Base, TimestampMixin):
    """A single turn in a ChatSession."""

    __tablename__ = "chat_messages"
    __table_args__ = (
        CheckConstraint(f"role IN {CHAT_MESSAGE_ROLES}", name="ck_chat_messages_role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.chat_sessions.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Original filename(s) attached by the user, comma-separated, for
    # display only -- the file's content/image bytes are never persisted
    # here, only forwarded to the chat bridge for that one turn.
    attachment_names: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Set only when this reply came from a "#Agente"-mentioned agent other
    # than the session's own agent_id (see ChatSessionParticipant) -- lets
    # the frontend show a name badge on cross-agent replies. Null for a
    # session's own agent (the common case, no badge shown).
    responding_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agents.id", ondelete="SET NULL"), nullable=True
    )
    # Wall-clock seconds between the stream opening and the agent's "done"
    # (or a Stop-button cancellation) -- assistant messages only. Powers
    # the "Pensou por mm:ss" label shown above the reply, both live
    # (ticking, frontend-only) and after the fact (this persisted value).
    thinking_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="messages")


class ChatArtifact(Base, TimestampMixin):
    """A file the agent created/edited during a ChatSession (write_file/patch
    tool calls), captured from hermes_stream.py's tool_complete event.

    Deliberately separate from the governance Artifact domain
    (db/models/artifact.py): these are ad-hoc files from a casual chat turn,
    not pipeline-stage deliverables requiring product/version/approval
    linkage -- forcing that traceability chain onto every scratch file the
    agent writes during a conversation would be unusable friction.
    """

    __tablename__ = "chat_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.chat_sessions.id"), nullable=False
    )
    # Absolute path on the host filesystem (as reported by the tool call) --
    # downloads re-read the file live via the bridge, nothing is copied here.
    path: Mapped[str] = mapped_column(String(1000), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="artifacts")


class ChatSessionParticipant(Base, TimestampMixin):
    """Tracks a "#Agente"-mentioned agent's own Hermes CLI session
    continuity within a ChatSession that's normally owned by a different
    agent (see stream_chat_message's target_agent_id handling).

    A ChatSession has exactly one *owning* agent (agent_id) with its
    continuity in ChatSession.hermes_session_id, same as before this
    feature existed. Mentioning a DIFFERENT agent creates a row here the
    first time, so that agent keeps its own memory across mentions in this
    same thread -- without it, every "#Agente ..." turn would look like the
    agent's first message ever, no context from its own prior replies here.
    Deliberately isolated (V1, no shared context): the mentioned agent only
    ever sees what was explicitly sent to it, never the owning agent's
    conversation.
    """

    __tablename__ = "chat_session_participants"
    __table_args__ = (
        UniqueConstraint("session_id", "agent_id", name="uq_chat_session_participants_session_agent"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agents.id", ondelete="CASCADE"), nullable=False
    )
    hermes_session_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="participants")

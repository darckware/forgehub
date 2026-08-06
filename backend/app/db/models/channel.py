"""ChatChannel: a real-time room where the human (Marcelo, resolved via the
authenticated login -- there is no multi-human concept to model yet, see
app/api/routes/auth.py's placeholder) and N registered Agents hold a single
shared conversation, distinct from a ChatSession's "1 human + 1 owning
agent" private conversation (app/db/models/chat.py).

Design decisions worth knowing before touching this file (see the plan
this domain was built from,
/root/.claude/plans/https-github-com-block-buzz-analise-e-qu-radiant-flute.md):

- Members are always an explicit choice made by the human -- at channel
  creation and afterwards -- never auto-derived/locked from a Project's
  ProjectAgentMembership. When a channel has a project_id, that project's
  active memberships are only ever offered as a *suggestion* in the
  member picker (app/api/routes/channel.py), never enforced.
- Attaching a Project to a channel (project_id) is independent of channel
  creation and mutable at any point in the conversation -- the same
  mental model as attaching an MCP server to a session, not a "mode"
  decided once and locked in.
- turn_policy governs when an agent-member actually generates a real
  response. Today only "mention_only" is a valid value: an agent speaks
  only when explicitly @mentioned (see channel.py's message-posting
  logic), sequential per mention, never on its own initiative. ForgeHub
  has no "agent watches and reacts autonomously" mechanism anywhere else
  in the system, and introducing one here first would add real risk of
  runaway agent-to-agent loops and uncontrolled dispatch cost with no
  existing safeguard to lean on. The column/CHECK exist from day one
  specifically so a future reactive policy is a CHECK-tuple migration,
  not a schema rework -- ChatChannelMember.muted already exists too, so a
  reactive policy can still let an individual member opt out later
  without another migration.
- A channel never duplicates the Messages domain's execution/audit
  machinery. When a channel message needs to actually dispatch an agent
  (run its CLI for real, not just produce a conversational reply), that
  goes through the *same* app/api/routes/demand.py::_execute_dispatch
  pipeline every other task dispatch uses -- ChatChannelMessage.
  triggered_demand_id is a pointer to the resulting AgentDemand, not a
  parallel copy of its state. See CLAUDE.md: "Every task is executed
  through the Messages channel."
- Same "narrate, don't duplicate" principle for lightweight tasks:
  ChatChannelTask is only the source of truth while project_task_id is
  NULL. Once promoted (via the existing "quick_task" conversion target
  in app/core/conversions.py -- no new task-creation logic), the real
  ProjectTask/PlanningItem chain takes over and this row just mirrors
  status for quick display in the channel stream.
"""
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
# Shared function/role vocabulary (not duplicated) -- see
# docs/architecture/CHANNEL_AGENT_ROLES_AND_ORCHESTRATION.md.
from app.db.models.orchestration import PROJECT_AGENT_ROLES

CHANNEL_MESSAGE_AUTHOR_TYPES = ("human", "agent", "system")

# Single valid value today -- see the module docstring for why this is a
# real column/CHECK from day one rather than a hardcoded assumption.
CHANNEL_TURN_POLICIES = ("mention_only",)

CHANNEL_TASK_STATUSES = ("todo", "doing", "done")


class ChatChannel(Base, TimestampMixin):
    """A shared room: the logged-in human + N Agent members, one transcript
    everyone sees. See module docstring for the project_id/turn_policy
    design decisions."""

    __tablename__ = "chat_channels"
    __table_args__ = (
        CheckConstraint(f"turn_policy IN {CHANNEL_TURN_POLICIES!r}", name="ck_chat_channels_turn_policy"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Mutable at any time via POST/DELETE /channels/{id}/project -- never a
    # creation-time-only choice. NULL means the channel is a free-standing
    # "idea" room with no formal Project behind it yet.
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.projects.id", ondelete="SET NULL"), nullable=True
    )
    # Same non-FK philosophy as ChatSession.working_directory_path
    # (app/db/models/chat.py) -- lets a channel's agent-members run their
    # terminal/tools against a real folder even when there's no registered
    # Project yet. Independent of project_id: a channel may have neither,
    # either, or both set.
    working_directory_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    turn_policy: Mapped[str] = mapped_column(String(20), nullable=False, default="mention_only")
    # Free-text snapshot of the authenticated user -- there is no real Users
    # domain yet (see CLAUDE.md's auth.py note), so this is display-only.
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Purely informational label -- "who Marcelo intends as the operational
    # coordinator among this channel's agent members" (2026-08-05, see
    # docs/architecture/CHANNEL_AGENT_ROLES_AND_ORCHESTRATION.md). This
    # column grants NO authority by itself and nothing checks it to decide
    # an Approval -- that stays 100% on governance.AuthorityDelegation, per
    # the plan's explicit "no second hierarchy" decision. Must reference a
    # current agent member of this channel (enforced at the API layer, like
    # every other cross-row rule in this codebase); SET NULL if that member
    # is later removed rather than silently pointing at a stranger.
    orchestrator_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agents.id", ondelete="SET NULL"), nullable=True
    )

    members: Mapped[list["ChatChannelMember"]] = relationship(
        "ChatChannelMember", back_populates="channel", cascade="all, delete-orphan"
    )
    messages: Mapped[list["ChatChannelMessage"]] = relationship(
        "ChatChannelMessage", back_populates="channel", cascade="all, delete-orphan", order_by="ChatChannelMessage.created_at"
    )
    artifacts: Mapped[list["ChatChannelArtifact"]] = relationship(
        "ChatChannelArtifact", back_populates="channel", cascade="all, delete-orphan"
    )
    tasks: Mapped[list["ChatChannelTask"]] = relationship(
        "ChatChannelTask", back_populates="channel", cascade="all, delete-orphan"
    )


class ChatChannelMember(Base, TimestampMixin):
    """N:N participant. Exactly one is_human=True row per channel (the
    logged-in user) plus one row per agent member -- both chosen explicitly
    by the human, at creation or afterwards (see module docstring: never
    auto-derived from a Project's team, even when project_id is set)."""

    __tablename__ = "chat_channel_members"
    __table_args__ = (
        CheckConstraint(
            "(is_human AND agent_id IS NULL) OR (NOT is_human AND agent_id IS NOT NULL)",
            name="ck_chat_channel_members_human_xor_agent",
        ),
        CheckConstraint(
            f"role IS NULL OR role IN {PROJECT_AGENT_ROLES}",
            name="ck_chat_channel_members_role",
        ),
        UniqueConstraint("channel_id", "agent_id", name="uq_chat_channel_members_channel_agent"),
        # A partial unique index enforcing "at most one is_human=True row per
        # channel" is added in the migration via op.execute -- SQLAlchemy's
        # UniqueConstraint can't express a WHERE clause, and agent_id being
        # NULL for every human row means a plain UniqueConstraint on
        # (channel_id, agent_id) would not catch a second human row.
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.chat_channels.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agents.id", ondelete="CASCADE"), nullable=True
    )
    is_human: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # This agent's own Hermes CLI session continuity *within this channel*
    # (analogous to ChatSession.hermes_session_id) -- null for the human row.
    hermes_session_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # An individually silenced member -- never woken by @mention even under
    # a future non-"mention_only" turn_policy. Already useful in V1 as a
    # lightweight way to keep a member listed without it responding.
    muted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # This agent's function *in this channel* (2026-08-05, see
    # docs/architecture/CHANNEL_AGENT_ROLES_AND_ORCHESTRATION.md) -- may
    # diverge from Agent.default_role (the same agent can be "developer" in
    # one channel and "qa" in another). Null for the human row and for an
    # agent whose function hasn't been set yet. Always editable by Marcelo
    # (the only human in the channel); "who can approve work" is a
    # completely separate axis handled via the real governance.Approval/
    # AuthorityDelegation machinery, not a flag on this row.
    role: Mapped[str | None] = mapped_column(String(30), nullable=True)

    channel: Mapped["ChatChannel"] = relationship("ChatChannel", back_populates="members")


class ChatChannelMessage(Base, TimestampMixin):
    """One turn in the shared transcript, from the human, an agent, or the
    system (execution-result narration, see triggered_demand_id below)."""

    __tablename__ = "chat_channel_messages"
    __table_args__ = (
        CheckConstraint(f"author_type IN {CHANNEL_MESSAGE_AUTHOR_TYPES!r}", name="ck_chat_channel_messages_author_type"),
        CheckConstraint(
            "(author_type = 'agent') = (author_agent_id IS NOT NULL)",
            name="ck_chat_channel_messages_agent_author_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.chat_channels.id", ondelete="CASCADE"), nullable=False
    )
    author_type: Mapped[str] = mapped_column(String(10), nullable=False)
    author_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agents.id", ondelete="SET NULL"), nullable=True
    )
    # Snapshot of the author's display name at post time -- an agent removed
    # from the channel (or deleted) later doesn't blank out past history.
    author_label: Mapped[str | None] = mapped_column(String(150), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # List of Agent UUIDs @mentioned in `content` -- drives which members are
    # woken for a real turn under turn_policy="mention_only". Populated by
    # the same mention-parsing the composer already does client-side
    # (mirrors ChatPane.tsx's extractMentionedAgents), re-derived server-side
    # so the wake logic never trusts the client alone.
    mentioned_agent_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Set only when this message triggered a real AgentDemand dispatch (see
    # api/routes/channel.py's dispatch-task action) -- the channel narrates
    # and links to that Message, it never becomes a second execution record.
    triggered_demand_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agent_demands.id", ondelete="SET NULL"), nullable=True
    )
    thinking_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attachment_names: Mapped[str | None] = mapped_column(String(500), nullable=True)

    channel: Mapped["ChatChannel"] = relationship("ChatChannel", back_populates="messages")


class ChatChannelArtifact(Base, TimestampMixin):
    """A file created/edited by any agent-member during a channel turn
    (captured from hermes_stream.py's tool_complete event) -- mirrors
    ChatArtifact (app/db/models/chat.py) but keyed to the channel and the
    specific agent who produced it, since a channel can have many agents."""

    __tablename__ = "chat_channel_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.chat_channels.id", ondelete="CASCADE"), nullable=False
    )
    author_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agents.id", ondelete="SET NULL"), nullable=True
    )
    path: Mapped[str] = mapped_column(String(1000), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    channel: Mapped["ChatChannel"] = relationship("ChatChannel", back_populates="artifacts")


class ChatChannelTask(Base, TimestampMixin):
    """A lightweight, channel-native task item -- exists so a channel with
    no Project attached can still track work ("an idea" per Marcelo) without
    forcing the PlanningItem->ProjectTask traceability chain onto a
    conversation that isn't formal work yet.

    project_task_id is NULL until explicitly promoted (see
    api/routes/channel.py's :promote action, which reuses the existing
    "quick_task" conversion target in app/core/conversions.py verbatim --
    no new task-creation logic). Before promotion this row is the source of
    truth for status/assignee; after promotion it mirrors the real
    ProjectTask instead of owning the data (avoids two diverging sources of
    truth, same principle as AgentDemand.dispatch_result narration)."""

    __tablename__ = "chat_channel_tasks"
    __table_args__ = (
        CheckConstraint(f"status IN {CHANNEL_TASK_STATUSES!r}", name="ck_chat_channel_tasks_status"),
        CheckConstraint(
            f"role_required IS NULL OR role_required IN {PROJECT_AGENT_ROLES}",
            name="ck_chat_channel_tasks_role_required",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.chat_channels.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="todo")
    assignee_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agents.id", ondelete="SET NULL"), nullable=True
    )
    created_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.chat_channel_messages.id", ondelete="SET NULL"), nullable=True
    )
    # Only valid to set when the channel has a project_id (nowhere to
    # promote to otherwise) -- enforced at the API layer, not a DB
    # constraint, per this repo's convention for cross-row business rules.
    project_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.project_tasks.id", ondelete="SET NULL"), nullable=True
    )

    # -- 2026-08-05 additions, see
    # docs/architecture/CHANNEL_AGENT_ROLES_AND_ORCHESTRATION.md --
    # Which channel role this task is meant for -- optional, only checked
    # when a proposer/orchestrator actually tags it.
    role_required: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # Who proposed this task, when it was an agent (via the MCP propose
    # tool) rather than Marcelo through the UI -- NULL for the latter.
    created_by_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agents.id", ondelete="SET NULL"), nullable=True
    )
    # NULL = never needed approval (created by Marcelo, or an agent
    # self-assigning within its own channel role). Set only when an agent
    # proposes this task FOR ANOTHER agent -- points at a real
    # governance.Approval (entity_type="chat_channel_task"), never a
    # bespoke boolean. While that Approval is "pending" the task is
    # blocked in the channel UI; deciding it uses the Approval domain's own
    # existing routes (POST /governance/approvals/{id}/approve|reject),
    # not anything channel-specific -- see api/routes/channel.py's
    # propose_channel_task and governance.py's _decide_approval narration
    # hook.
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.approvals.id", ondelete="SET NULL"), nullable=True
    )

    channel: Mapped["ChatChannel"] = relationship("ChatChannel", back_populates="tasks")

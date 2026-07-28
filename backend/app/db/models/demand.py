"""AgentDemand: an inbox item submitted by an agent (or a user note),
"like an e-mail" per the request that created this domain -- read it,
then convert it into a Task, a Docs document, an Artifact, or a
Knowledge Base note (see app/core/conversions.py). Notes/annotations
(existing /root/docs files) go through the same conversion helpers via
api/routes/docs.py's /convert, without needing a demand row.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Identity, Integer, String, Text, false
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

DEMAND_STATUSES = ("new", "read", "converted", "archived")

# Independent of DEMAND_STATUSES (the item's own inbox lifecycle) -- a demand
# can be status="read" and dispatch_status="running" at the same time. NULL
# until target_agent_id is set and a dispatch is actually triggered.
DEMAND_DISPATCH_STATUSES = ("pending", "dispatched", "running", "completed", "failed")

# "Tipo" da mensagem -- mandatory, exactly two values (2026-07-28, Marcelo:
# "no type só sistem dois tipo task ou backlog e o campo é obrigatório...
# não temos resposta automática. somente processamento"). This retired the
# old third value, "demand" (an auto-generated reply, threaded via origin_id
# to the message it answered) -- there is no more reply message at all; see
# dispatch_result below for what replaced it.
#   "task"    -> a polymorphic origin_id, same convention as governance.py
#                (entity_type, entity_id), no real FK: origin_id is a
#                ProjectTask.id (this message dispatches/tracks that task).
#   "backlog" -> a *classification*, not a link. Marks parked work --
#                addressed or not, not ready to run, never dispatches.
#                Never carries origin_id. Promoted to "task" when someone
#                decides to run it (the reading pane's "Promover a Task").
# Never NULL -- every writer defaults to "backlog" when nothing else applies
# (see demand.py's _reconcile_task_origin).
DEMAND_ORIGIN_TYPES = ("task", "backlog")

# The only type that resolves a real origin_id (see demand.py's
# _resolve_origin) -- "backlog" is a classification, never a link.
DEMAND_LINKED_ORIGIN_TYPES = ("task",)

# Kept in sync with core/conversions.py's CONVERT_TARGETS.
DEMAND_CONVERT_TARGETS = (
    "task",
    "doc",
    "artifact",
    "knowledge_base",
    # project_id-scoped targets, added for the "console de desenvolvimento"
    # inbox: turn a demand straight into project work instead of only a
    # loose doc/task tied to an existing planning item.
    "planning_item",
    "project_doc",
    "quick_task",
)


class AgentDemand(Base, TimestampMixin):
    __tablename__ = "agent_demands"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Human-readable display number (#1, #2, ...), a real Postgres IDENTITY
    # column -- unlike the UUID PK above (Python-side, per this repo's
    # convention), this one genuinely needs DB-level atomicity, and it's
    # not the PK, so the "never server-side" rule doesn't apply here. Lets
    # Marcelo reference an existing message as another item's origin by
    # typing a short number instead of hunting for its UUID (see
    # DemandSubmitIn's origin_number).
    number: Mapped[int] = mapped_column(Integer, Identity(always=False), unique=True, nullable=False)
    # Hermes profile slug of the submitting agent (e.g. "athos").
    from_agent: Mapped[str] = mapped_column(String(50), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="new")

    # Only meaningful while status="archived" -- which "Arquivados" subpasta
    # this demand was filed under. NULL + archived = sits in the Arquivados
    # root (uncategorized). Deleting the group sets this back to NULL
    # instead of deleting the demand (see DemandGroup's ondelete note).
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.demand_groups.id", ondelete="SET NULL"), nullable=True
    )

    # Set together when /convert succeeds -- what this demand became and
    # where to find it (task id / doc path / artifact id / vault note path).
    converted_entity_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    converted_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # --- Agent dispatch (see api/routes/demand.py's /dispatch) ---
    # NULL = "sem agente" (item sits in Marcelo's evaluation queue, outside
    # the agent tree). Set = this item is a dispatch to that agent.
    target_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agents.id", ondelete="SET NULL"), nullable=True
    )
    # Resolves the free-text from_agent (Hermes profile slug or arbitrary
    # submitter) to a real Agent row when the sender is one of the 12
    # registered agents -- lets the Inbox tree group by agent without a
    # string match. NULL for submitters that aren't a registered agent.
    from_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agents.id", ondelete="SET NULL"), nullable=True
    )
    # Which project this message is about -- NULL for anything not yet
    # scoped to one (most day-to-day agent chatter). Independent of
    # conversion: ConvertIn.project_id (api/schemas/demand.py) picks the
    # project a *converted* planning_item/project_doc/quick_task lands in
    # and can differ from this field or be set on an item that never had
    # one here. This column exists so the Inbox can classify/filter by
    # project *before* conversion (see the "Controle" tab's grouping,
    # added 2026-07-25), not just after. Settable from the compose/edit
    # panel, like target_agent_id/from_agent_id above.
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.projects.id", ondelete="SET NULL"), nullable=True
    )
    # Marcelo's instruction when dispatching/forwarding an item that had no
    # prior direction of its own. NULL when the body itself already IS the
    # full prompt (autonomous agent-to-agent handoff, or a reply continuing
    # an existing thread).
    command_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Mandatory (2026-07-28, Marcelo: "o campo e obrigatorio. Enao tem tem
    # None") -- always one of DEMAND_ORIGIN_TYPES, never NULL. Every writer
    # (create_demand_and_notify/update_demand's _reconcile_task_origin,
    # _finalize_dispatch's return message) guarantees a value before
    # insert/update; there is no remaining code path that leaves this
    # unset. server_default (not just the Python-side default) for the same
    # reason as requires_response below: a raw INSERT that doesn't know
    # about this column (a stale writer, a test fixture) needs the DB
    # itself to supply a value rather than 500 on a NotNullViolationError.
    origin_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default="backlog")
    # A ProjectTask.id (this message dispatches/tracks that task) --
    # meaningful only when origin_type="task". Always NULL for "backlog"
    # (a classification, never a link -- see DEMAND_ORIGIN_TYPES' docstring).
    # No real FK, same convention as governance.py's Approval/AuditEvent
    # (entity_type, entity_id): kept deliberately loose since the target
    # table is decided by origin_type, not by the column itself. Resolved
    # from a human-typed display number at the route layer (see demand.py's
    # _resolve_origin), never hand-typed as a UUID.
    origin_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # The agent's raw output once a dispatch reaches a terminal state --
    # written by _finalize_dispatch (demand.py) onto this SAME message,
    # regardless of requires_response (2026-07-28, Marcelo: "não temos
    # resposta automática. somente processamento" + "gravado na própria
    # mensagem"). This is the only trace of the result when
    # requires_response=false; when true, the same text also becomes the
    # body of the auto-generated return message (see reply_to_id below).
    dispatch_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Set only on an auto-generated return message -- points back at the
    # original dispatched message it answers. A real self-referential FK
    # (unlike origin_id's deliberate polymorphism): both sides are always
    # AgentDemand, so there's no ambiguity to keep loose for. Created only
    # when the original had requires_response=true (2026-07-28, Marcelo:
    # "preciso gerar... uma mensagem de retorno quando solicitado pelo
    # agente... e o padrão é não" -- reverting 2026-07-27's "every reply
    # routes back regardless of requires_response" back to conditional,
    # now gating creation itself, not just routing). The return message's
    # own origin_type is "backlog" (informational, not further dispatchable
    # work) since "demand" no longer exists as a Tipo value.
    reply_to_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agent_demands.id", ondelete="SET NULL"), nullable=True
    )
    # "Execução" -- when the work this message stands for actually finished
    # running. Two writers, both server-side (never the compose form, which
    # shows it as a disabled field):
    #  1. demand.py's get_dispatch_status, once the recipient agent's own
    #     run reaches a terminal state -- either outcome, since a failed run
    #     still ran. This is the common case and the one the form's
    #     "Execução" field is really about (2026-07-25): before this, a
    #     message could be dispatched, executed and replied to with the
    #     field still empty, because only writer 2 existed and most
    #     messages have no linked task at all.
    #  2. task.py's update_task_execution, when a ProjectTask linked via
    #     origin_id (origin_type="task") transitions to "completed" --
    #     exact match on origin_id since the 2026-07-25 origin unification,
    #     no longer the best-effort kanboard_task_id comparison. Covers a
    #     message that tracks a task executed outside the Inbox dispatch
    #     path.
    # Both mean the same thing to a reader ("this ran at ..."), so they
    # share one column rather than two competing timestamps; whichever
    # happens last wins. Still NULL for anything that never ran -- a
    # dispatch that failed before starting (see run_scheduled_dispatch_pass's
    # AgentRunDispatchError path) deliberately leaves it unset.
    task_execution_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # "Retorno" -- whether this message expects a response back from the
    # recipient. Gates whether _finalize_dispatch creates the auto-generated
    # return message at all (2026-07-28) -- default False means "só
    # processamento" (dispatch_result recorded on this same message, no new
    # message); True means the executor's answer comes back as a real new
    # message (see reply_to_id above). No longer surfaced in the compose
    # form (removed 2026-07-28) -- set via the MCP's send_agent_message
    # (requires_response=True) or a direct API call, since this is framed
    # as something an agent requests, not a human toggle.
    # server_default (not just the Python-side default=False) matters here:
    # a NOT NULL column an older/differently-versioned writer's ORM model
    # doesn't know about (e.g. a stale Docker image inserting via a plain
    # from_agent/subject/body statement) omits it from the INSERT entirely
    # and needs the DB itself to supply a value, or the insert 500s on a
    # NotNullViolationError -- this happened for real once send_demand.sh
    # started targeting a deploy still on pre-Retorno code (2026-07-24).
    requires_response: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    # Scheduled send: when set (and target_agent_id is set), the background
    # loop in main.py's _scheduled_dispatch_poll_loop dispatches this item
    # automatically once scheduled_at is reached, the same way a manual
    # POST .../dispatch would (see api/routes/demand.py's _execute_dispatch,
    # shared by both paths). NULL = dispatch only happens if/when triggered
    # by hand. Left set after the fact as a historical record -- dispatch_status
    # moving off NULL is what stops the loop from re-dispatching it.
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set when the recipient agent itself pulls this item via
    # GET /demands/pending (bridge-token, see that route's docstring) --
    # distinct from both `status` (Marcelo's own read/unread) and
    # `dispatch_status` (the CLI-auto-dispatch lifecycle, which most Hermes
    # profiles don't participate in at all -- they have no runtime_type,
    # so they check their own Inbox from their own cron/loop instead of
    # being spawned by ForgeHub). NULL = the target agent hasn't checked
    # its mail yet. Pulling is itself the acknowledgment -- there's no
    # separate ack step, since a profile-driven cron isn't guaranteed to
    # come back and explicitly mark things read.
    agent_processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dispatch_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # host-bridge POST /v1/agent-runs' run_id, for polling GET .../{run_id}.
    agent_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Guards against sending the "independent dispatch" Telegram notice more
    # than once if the status poll runs multiple times.
    notice_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        CheckConstraint(f"status IN {DEMAND_STATUSES}", name="ck_agent_demands_status"),
        CheckConstraint(
            f"converted_entity_type IS NULL OR converted_entity_type IN {DEMAND_CONVERT_TARGETS}",
            name="ck_agent_demands_converted_entity_type",
        ),
        CheckConstraint(
            f"dispatch_status IS NULL OR dispatch_status IN {DEMAND_DISPATCH_STATUSES}",
            name="ck_agent_demands_dispatch_status",
        ),
        CheckConstraint(
            f"origin_type IN {DEMAND_ORIGIN_TYPES}",
            name="ck_agent_demands_origin_type",
        ),
    )

    # lazy="selectin": DemandOut always includes attachments, and the async
    # session can't do implicit lazy-load I/O once Pydantic serializes the
    # ORM object outside the request's await chain -- eager-load up front
    # instead of adding selectinload() at every one of demand.py's routes.
    attachments: Mapped[list["DemandAttachment"]] = relationship(
        "DemandAttachment",
        back_populates="demand",
        cascade="all, delete-orphan",
        order_by="DemandAttachment.created_at",
        lazy="selectin",
    )


class DemandAttachment(Base, TimestampMixin):
    """A file attached to a demand, e.g. a markdown procedure doc sent
    alongside the inbox message. The bytes live under the messages root
    (/messages, see api/routes/demand.py); this row is the pointer + metadata.

    `filename` is what the user uploaded and what a download is served as;
    `path` is the on-disk name, which is deliberately different -- see
    _stored_attachment_name for why (same-named uploads used to overwrite each
    other). Rows created before 2026-07-27 have a `path` relative to the /docs
    mount instead, and are still read from there (_resolve_attachment_file)."""

    __tablename__ = "demand_attachments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    demand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agent_demands.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # Path relative to the messages root: "<attachment id>_<message
    # number>_<UTC timestamp><ext>". Legacy rows: "anexos/demandas/
    # <demand_id>/<original name>", relative to /docs.
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Optional caption: what this file is / why it was sent. NULL (not "")
    # when none was given -- an attachment without a description is the
    # normal case, and the two must stay distinguishable.
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    demand: Mapped["AgentDemand"] = relationship("AgentDemand", back_populates="attachments")


class DemandGroup(Base, TimestampMixin):
    """A user-created subfolder inside the Inbox's "Arquivados" bucket --
    freely nestable (folder-within-folder, self-referencing parent_id) so
    archived demands can be organized by theme. "Entrada" and the
    "Arquivados" root itself are NOT rows here -- they're derived purely
    from AgentDemand.status/group_id (see that model's group_id docstring);
    only user-created subfolders under Arquivados get a row.

    ondelete="CASCADE" on parent_id: deleting a folder deletes its
    subfolders too (a real folder-tree deletion, not a "promote children"
    move). Contrast with AgentDemand.group_id's ondelete="SET NULL" --
    deleting a folder never deletes the demands inside it, they just fall
    back to the Arquivados root."""

    __tablename__ = "demand_groups"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.demand_groups.id", ondelete="CASCADE"), nullable=True
    )

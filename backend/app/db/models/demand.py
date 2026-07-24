"""AgentDemand: an inbox item submitted by an agent (or a user note),
"like an e-mail" per the request that created this domain -- read it,
then convert it into a Task, a Docs document, an Artifact, or a
Knowledge Base note (see app/core/conversions.py). Notes/annotations
(existing /root/docs files) go through the same conversion helpers via
api/routes/docs.py's /convert, without needing a demand row.
"""
import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

DEMAND_STATUSES = ("new", "read", "converted", "archived")

# Independent of DEMAND_STATUSES (the item's own inbox lifecycle) -- a demand
# can be status="read" and dispatch_status="running" at the same time. NULL
# until target_agent_id is set and a dispatch is actually triggered.
DEMAND_DISPATCH_STATUSES = ("pending", "dispatched", "running", "completed", "failed")

# Polymorphic origin, same convention as governance.py's Approval/AuditEvent
# (entity_type, entity_id) -- no real FK since it points at two different
# tables. NULL origin = this item is the root of a new dispatch thread.
DEMAND_ORIGIN_TYPES = ("task", "demand")

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
    # Marcelo's instruction when dispatching/forwarding an item that had no
    # prior direction of its own. NULL when the body itself already IS the
    # full prompt (autonomous agent-to-agent handoff, or a reply continuing
    # an existing thread).
    command_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    origin_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    origin_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
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
            f"origin_type IS NULL OR origin_type IN {DEMAND_ORIGIN_TYPES}",
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
    alongside the inbox message. Stored on disk under the same /docs
    mount docs.py already writes to (see api/routes/demand.py's upload
    handler), this row is just the pointer + metadata."""

    __tablename__ = "demand_attachments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    demand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agent_demands.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # Relative path under /docs, e.g. "anexos/demandas/<demand_id>/<filename>".
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)

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

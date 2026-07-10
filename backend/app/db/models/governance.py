"""SQLAlchemy models for the Governance domain.

Tables owned by this domain: approvals, audit_events, policies.

These tables provide cross-cutting governance for the rest of the system
(SPEC.md section 4.8 / 6.2 / 6.5 / 6.7):
- `policies` is a registry of named governance rules (e.g. "critical skills
  require approval", "third-party skills require security review") that
  other domains and this domain's own business logic can reference.
- `approvals` records explicit human/role decisions for gated transitions
  (pipeline stage gates, releases, critical skill registration, etc.).
  Targets are referenced polymorphically via (entity_type, entity_id)
  rather than a hard FK, because approvals can gate many different kinds
  of entities owned by other domains (pipeline_stage_gates, releases,
  skills, ...). entity_id is a UUID string; entity_type is a free-text
  discriminator (e.g. "pipeline_stage_gate", "release", "skill").
- `audit_events` is an append-only log of major entity transitions for
  traceability (SPEC 5.7 / 6.4.4): "every task completion must be
  auditable". Also polymorphic via (entity_type, entity_id) for the same
  reason as approvals.

Per foundation convention: FKs to tables owned by OTHER domains are
plain UUID columns with a string-form ForeignKey (e.g.
ForeignKey("company.pipeline_stage_gates.id")) so this module never
imports another domain's model module. Where the relationship is
inherently polymorphic (approvals/audit_events can target many
different table types) we deliberately do NOT use a FK at all — a
real FK can only point at one table, and these rows are
cross-cutting by design.
"""
import uuid

from sqlalchemy import Boolean, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Policy(Base, TimestampMixin):
    """A named governance rule/policy that can be activated or retired.

    Examples (SPEC 6.5): "critical_skill_requires_approval",
    "third_party_skill_requires_security_review",
    "published_version_immutable".
    """

    __tablename__ = "policies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Discriminator for what kind of rule this is, e.g. "approval_required",
    # "security_review_required", "immutability". Free-text by design —
    # the set of policy types is expected to grow without a migration.
    policy_type: Mapped[str] = mapped_column(String(100), nullable=False)
    # Arbitrary structured configuration for the rule (thresholds, target
    # entity types, severity levels, etc.).
    rules: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Polymorphic target — the entity this policy governs (optional; a policy
    # may also be general-purpose with no specific entity binding).
    entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class Approval(Base, TimestampMixin):
    """An explicit approval/rejection decision for a gated transition.

    Polymorphic target via (entity_type, entity_id) — see module
    docstring. `status` follows pending -> approved|rejected; once
    decided (approved/rejected) the decision is treated as final
    (business rule enforced in the route layer, not the DB).
    """

    __tablename__ = "approvals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # e.g. "release_approval", "gate_approval", "skill_approval",
    # "security_review". Lets callers distinguish *why* an approval exists
    # even when entity_type is shared.
    approval_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending | approved | rejected
    # Optional link to the policy that mandated this approval.
    policy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.policies.id", ondelete="SET NULL"),
        nullable=True,
    )
    requested_by: Mapped[str] = mapped_column(String(150), nullable=False)
    decided_by: Mapped[str | None] = mapped_column(String(150), nullable=True)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_approvals_entity", "entity_type", "entity_id"),
    )


class AuditEvent(Base, TimestampMixin):
    """Append-only record of a major entity transition.

    Polymorphic target via (entity_type, entity_id) — see module
    docstring. Read-mostly: created via POST, never updated/deleted
    through the API (audit integrity).
    """

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # e.g. "created", "status_changed", "approved", "rejected",
    # "stage_completed", "task_completed".
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    actor: Mapped[str] = mapped_column(String(150), nullable=False)
    # Free-form structured detail of the transition (old/new status, etc.).
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_audit_events_entity", "entity_type", "entity_id"),
    )

"""Client/Workstation/Irregularity domain -- the Nexo monitoring foundation.

A Client is a company Marcelo supports (e.g. Clube de Tiro Gatling). A
Workstation is one machine of theirs running the Nexo Remote Agent,
identified to the ingestion endpoint by a per-device token (never the raw
token stored -- only its SHA-256 hash, same boundary as
Agent.forgerouter_api_key_encrypted / AgentServiceCredential.token_hash).
An Irregularity is one rule violation surfaced from an ingested report; see
docs/architecture/NEXO_CLIENT_MONITORING_AND_NETWORK_ADMIN.md sections 2-3
for the full rule table and lifecycle.
"""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

SUPPORT_PLANS = ("4h", "8h", "12h")
OS_KINDS = ("linux", "windows")
IRREGULARITY_RULE_KEYS = (
    "disk_space_low",
    "backup_stale",
    "unauthorized_remote_tool",
    "critical_service_down",
    "collection_failed",
    "agent_unreachable",
)
IRREGULARITY_SEVERITIES = ("info", "warning", "critical")
IRREGULARITY_STATUSES = ("open", "acknowledged", "resolved")


class Client(Base, TimestampMixin):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    support_plan: Mapped[str | None] = mapped_column(String(20), nullable=True)
    headscale_tag: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            f"support_plan IS NULL OR support_plan IN {SUPPORT_PLANS}",
            name="ck_clients_support_plan",
        ),
    )


class Workstation(Base, TimestampMixin):
    __tablename__ = "workstations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.clients.id", ondelete="CASCADE"), nullable=False
    )
    hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    os_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    # SHA-256 hex digest of the raw device token. The raw token is shown to
    # the caller exactly once, at issuance -- never stored, never returned
    # by any read endpoint. See Server.private_key_encrypted's docstring
    # for the sibling "store a durable copy, decrypted, never leak on read"
    # boundary; this one is simpler still because a device token is a
    # bearer secret, not something ForgeHub ever needs to reconstruct.
    device_token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    device_token_issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    device_token_revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_report_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_agent_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    __table_args__ = (
        CheckConstraint(f"os_kind IN {OS_KINDS}", name="ck_workstations_os_kind"),
    )


class WorkstationPeerGrant(Base, TimestampMixin):
    """A historical permission for one same-client workstation pair.

    Routes store pair IDs canonically. Revocation closes a row instead of
    deleting it; the partial unique index permits a later grant to create a
    new historical row while preventing two simultaneously-active grants.
    """

    __tablename__ = "workstation_peer_grants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workstation_a_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.workstations.id", ondelete="CASCADE"), nullable=False
    )
    workstation_b_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.workstations.id", ondelete="CASCADE"), nullable=False
    )
    granted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.users.id", ondelete="SET NULL"), nullable=True
    )
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index(
            "uq_workstation_peer_grants_active_pair",
            "workstation_a_id",
            "workstation_b_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )


class Irregularity(Base, TimestampMixin):
    __tablename__ = "irregularities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workstation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.workstations.id", ondelete="CASCADE"), nullable=False
    )
    rule_key: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        CheckConstraint(f"rule_key IN {IRREGULARITY_RULE_KEYS}", name="ck_irregularities_rule_key"),
        CheckConstraint(f"severity IN {IRREGULARITY_SEVERITIES}", name="ck_irregularities_severity"),
        CheckConstraint(f"status IN {IRREGULARITY_STATUSES}", name="ck_irregularities_status"),
    )

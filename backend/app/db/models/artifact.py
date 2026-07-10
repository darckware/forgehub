"""SQLAlchemy models for the Artifact domain (SPEC 4.7 / 5.6 / 6 — artifact
governance).

Tables owned by this module:
- artifacts: a formal deliverable produced in a project (PRD, SPEC,
  DATA SPEC, SECURITY SPEC, source code, migration, test report,
  release notes, pull request, deployment package, approval record...).
  Linked (loosely, via nullable FKs) to a pipeline stage and/or a task
  execution that produced it, per SPEC 5.6 ("Link artifacts to task
  executions and pipeline stages").
- artifact_versions: each concrete revision of an artifact. An artifact
  can have many versions; exactly one is "current" at a time.

Foreign keys into tables owned by OTHER domains are declared as plain
string references (e.g. "company.pipeline_stages.id") and are NOT
backed by relationship()/ORM imports of those domains' modules, per the
foundation's import-order-decoupling convention. They are nullable
because the owning rows may not exist yet at artifact-creation time
(e.g. an artifact registered ad hoc before a pipeline stage is wired
up), and because not every artifact need be tied to a stage or
execution.
"""
import enum
import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class ArtifactType(str, enum.Enum):
    """Artifact kinds called out explicitly in PRD 5.7."""

    PRD = "prd"
    SPEC = "spec"
    DATA_SPEC = "data_spec"
    BUSINESS_RULE_SPEC = "business_rule_spec"
    SECURITY_SPEC = "security_spec"
    SOURCE_CODE = "source_code"
    MIGRATION = "migration"
    TEST_REPORT = "test_report"
    RELEASE_NOTES = "release_notes"
    PULL_REQUEST = "pull_request"
    DEPLOYMENT_PACKAGE = "deployment_package"
    APPROVAL_RECORD = "approval_record"
    # Fine-grained deliverable types (added so individual screens, DB
    # objects, etc. can be registered/governed/locked one-by-one instead
    # of only as a section inside a bigger spec document).
    SCREEN = "screen"
    COMPONENT = "component"
    REPORT = "report"
    DATABASE_SCHEMA = "database_schema"
    TABLE = "table"
    STORED_PROCEDURE = "stored_procedure"
    REFERENCE_DOC = "reference_doc"
    CONTEXT_BRIEF = "context_brief"
    OTHER = "other"


class ArtifactStatus(str, enum.Enum):
    """Lifecycle of an artifact as a whole (SPEC 6.2.6-6.2.8: required
    artifacts can be missing, present, or approved before a stage gate
    can pass)."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class ArtifactVersionStatus(str, enum.Enum):
    """Lifecycle of an individual artifact_version revision."""

    DRAFT = "draft"
    FINAL = "final"
    SUPERSEDED = "superseded"


class Artifact(Base, TimestampMixin):
    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    artifact_type: Mapped[ArtifactType] = mapped_column(
        Enum(ArtifactType, name="artifact_type_enum"), nullable=False
    )
    status: Mapped[ArtifactStatus] = mapped_column(
        Enum(ArtifactStatus, name="artifact_status_enum"),
        nullable=False,
        default=ArtifactStatus.DRAFT,
        server_default=ArtifactStatus.DRAFT.name,
    )
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)

    # Loose traceability links into other domains (SPEC 5.6). String FK
    # targets only -- no cross-domain ORM relationship() / model import.
    pipeline_stage_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.pipeline_stages.id", ondelete="SET NULL"),
        nullable=True,
    )
    task_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.task_executions.id", ondelete="SET NULL"),
        nullable=True,
    )

    requires_approval: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # Advisory "do not touch" flag (not a file-system permission): once
    # set, the API layer rejects further mutation of this artifact
    # (new versions, edits, approve/reject) until it is explicitly
    # unlocked, so an agent reading ForgeHub knows this deliverable is
    # finalized and must not be altered.
    is_locked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    versions: Mapped[list["ArtifactVersion"]] = relationship(
        "ArtifactVersion",
        back_populates="artifact",
        cascade="all, delete-orphan",
        order_by="ArtifactVersion.version_number",
    )


class ArtifactVersion(Base, TimestampMixin):
    __tablename__ = "artifact_versions"
    __table_args__ = (
        UniqueConstraint(
            "artifact_id", "version_number", name="uq_artifact_version_number"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    artifact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.artifacts.id", ondelete="CASCADE"),
        nullable=False,
    )

    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ArtifactVersionStatus] = mapped_column(
        Enum(ArtifactVersionStatus, name="artifact_version_status_enum"),
        nullable=False,
        default=ArtifactVersionStatus.DRAFT,
        server_default=ArtifactVersionStatus.DRAFT.name,
    )

    # Where the actual content of this version lives: a URI/path (repo
    # path, S3 key, PR URL, etc.) rather than inlined blob storage.
    location_uri: Mapped[str] = mapped_column(String(2048), nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    produced_by_task_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.task_executions.id", ondelete="SET NULL"),
        nullable=True,
    )

    artifact: Mapped["Artifact"] = relationship(
        "Artifact", back_populates="versions"
    )

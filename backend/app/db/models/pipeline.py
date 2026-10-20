"""SQLAlchemy models for the Pipeline domain.

Tables owned by this domain (see docs/SPEC.md section 4.3 / 6.2):
- pipeline_templates
- pipeline_template_stages
- pipeline_template_required_artifacts
- project_pipelines
- pipeline_stages
- pipeline_stage_dependencies
- pipeline_stage_required_artifacts
- pipeline_stage_gates

Foreign keys pointing at tables owned by OTHER domains (e.g. `projects`,
`artifacts`) are declared as plain string targets
(`ForeignKey("company.projects.id")`) rather than importing those
domains' model modules, per the bootstrap convention -- this avoids
import-order coupling. SQLAlchemy resolves these lazily once every
domain module has been imported centrally (app/db/models/__init__.py).
"""
import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

# ---------------------------------------------------------------------------
# Pipeline templates
# ---------------------------------------------------------------------------


class PipelineTemplate(Base, TimestampMixin):
    """A reusable, named pipeline definition (e.g. "Standard Feature Flow")."""

    __tablename__ = "pipeline_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    stages: Mapped[list["PipelineTemplateStage"]] = relationship(
        back_populates="template", cascade="all, delete-orphan"
    )


class PipelineTemplateStage(Base, TimestampMixin):
    """A stage definition within a pipeline template."""

    __tablename__ = "pipeline_template_stages"
    __table_args__ = (
        UniqueConstraint("template_id", "order_index", name="uq_template_stage_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.pipeline_templates.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    stage_type: Mapped[str] = mapped_column(String(100), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_verification: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    template: Mapped["PipelineTemplate"] = relationship(back_populates="stages")
    required_artifacts: Mapped[list["PipelineTemplateRequiredArtifact"]] = relationship(
        back_populates="template_stage", cascade="all, delete-orphan"
    )


class PipelineTemplateRequiredArtifact(Base, TimestampMixin):
    """An artifact type required by a given template stage."""

    __tablename__ = "pipeline_template_required_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_stage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.pipeline_template_stages.id"),
        nullable=False,
    )
    artifact_type: Mapped[str] = mapped_column(String(100), nullable=False)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    template_stage: Mapped["PipelineTemplateStage"] = relationship(back_populates="required_artifacts")


# ---------------------------------------------------------------------------
# Project pipelines (live instances)
# ---------------------------------------------------------------------------


class ProjectPipeline(Base, TimestampMixin):
    """An active (or historical) pipeline instance for a project.

    Business rule (SPEC 6.2.1/6.2.2): every project must have an active
    pipeline, and only one pipeline can be active per project at a time.
    `project_id` references the `projects` table owned by the Project
    domain -- declared as a string FK target, not imported.
    """

    __tablename__ = "project_pipelines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.projects.id", ondelete="CASCADE"), nullable=False
    )
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.pipeline_templates.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    stages: Mapped[list["PipelineStage"]] = relationship(
        back_populates="pipeline", cascade="all, delete-orphan", order_by="PipelineStage.order_index"
    )


class PipelineStage(Base, TimestampMixin):
    """A concrete stage instance within a project pipeline.

    Business rule (SPEC 6.2.3): every stage must define order, status,
    and type.
    """

    __tablename__ = "pipeline_stages"
    __table_args__ = (
        UniqueConstraint("pipeline_id", "order_index", name="uq_pipeline_stage_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pipeline_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.project_pipelines.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    stage_type: Mapped[str] = mapped_column(String(100), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_verification: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    pipeline: Mapped["ProjectPipeline"] = relationship(back_populates="stages")
    required_artifacts: Mapped[list["PipelineStageRequiredArtifact"]] = relationship(
        back_populates="stage", cascade="all, delete-orphan"
    )
    gates: Mapped[list["PipelineStageGate"]] = relationship(
        back_populates="stage", cascade="all, delete-orphan"
    )
    # Dependencies where THIS stage is the dependent one.
    dependencies: Mapped[list["PipelineStageDependency"]] = relationship(
        back_populates="stage",
        foreign_keys="PipelineStageDependency.stage_id",
        cascade="all, delete-orphan",
    )


class PipelineStageDependency(Base, TimestampMixin):
    """Declares that `stage_id` depends on `depends_on_stage_id`.

    Business rule (SPEC 6.2.9): blocked stages must prevent dependent
    stages from advancing.
    """

    __tablename__ = "pipeline_stage_dependencies"
    __table_args__ = (
        UniqueConstraint("stage_id", "depends_on_stage_id", name="uq_stage_dependency_pair"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.pipeline_stages.id", ondelete="CASCADE"), nullable=False
    )
    depends_on_stage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.pipeline_stages.id", ondelete="CASCADE"), nullable=False
    )

    stage: Mapped["PipelineStage"] = relationship(
        back_populates="dependencies", foreign_keys=[stage_id]
    )


class PipelineStageRequiredArtifact(Base, TimestampMixin):
    """An artifact required for a concrete stage instance to complete.

    Business rule (SPEC 6.2.6/6.2.7): stages may require mandatory
    artifacts; a stage cannot complete if mandatory artifacts are
    missing. `artifact_id` optionally links to a real artifact once
    produced (Artifact domain, owned elsewhere -- string FK).
    """

    __tablename__ = "pipeline_stage_required_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.pipeline_stages.id", ondelete="CASCADE"), nullable=False
    )
    artifact_type: Mapped[str] = mapped_column(String(100), nullable=False)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.artifacts.id"), nullable=True
    )
    is_fulfilled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    stage: Mapped["PipelineStage"] = relationship(back_populates="required_artifacts")


class PipelineStageGate(Base, TimestampMixin):
    """An approval/verification gate guarding a stage's completion.

    Business rules (SPEC 6.2.4/6.2.5/6.2.8/6.2.10): stages may require
    human approval or independent verification; a stage cannot complete
    if mandatory artifacts require approval and approval is missing;
    release approval is allowed only when all required gates pass.
    """

    __tablename__ = "pipeline_stage_gates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.pipeline_stages.id", ondelete="CASCADE"), nullable=False
    )
    gate_type: Mapped[str] = mapped_column(String(50), nullable=False)  # approval | verification
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    stage: Mapped["PipelineStage"] = relationship(back_populates="gates")

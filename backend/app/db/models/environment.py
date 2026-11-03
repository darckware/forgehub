"""SQLAlchemy models for the Environment domain (Plano Integrado M0.7).

Tables owned by this domain: environment_releases.

What is published in each environment, and from which commit
(docs/architecture/MISSION_EXECUTIONS_SCREEN_SPEC.md §6;
MCP_MISSION_TOOLS_SPEC.md §11 D-M0-1/D-M0-7). A row is a *recorded*
release: written by POST /api/v1/environments/releases (the single writer),
or imported once from the on-host convention with source='imported'. The
build or the running container is never read as proof of a release (12 §10
"sem inferir release do build"): no row means "sem registro".

The latest row per (environment, target) is the current release. Rows are
append-only; a correction is a new row.
"""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

ENVIRONMENTS = ("test", "production")
RELEASE_SOURCES = ("recorded", "imported")


def _in(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"


class EnvironmentRelease(Base, TimestampMixin):
    __tablename__ = "environment_releases"
    __table_args__ = (
        CheckConstraint(f"environment IN {_in(ENVIRONMENTS)}", name="ck_environment_releases_environment"),
        CheckConstraint(f"source IN {_in(RELEASE_SOURCES)}", name="ck_environment_releases_source"),
        CheckConstraint("commit_sha ~ '^[0-9a-f]{40}$'", name="ck_environment_releases_commit_sha"),
        UniqueConstraint("environment", "target", "released_at", name="uq_environment_releases_env_target_at"),
        Index("ix_environment_releases_latest", "environment", "target", "released_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    environment: Mapped[str] = mapped_column(String(20), nullable=False)
    # e.g. "forgehub"; the <target> of a `publish:<environment>:<target>` execution target.
    target: Mapped[str] = mapped_column(String(200), nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    released_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Principal name (person or agent) that recorded the release.
    released_by: Mapped[str] = mapped_column(String(255), nullable=False)
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.project_tasks.id", ondelete="SET NULL"), nullable=True
    )
    evidence_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="recorded", server_default="recorded")

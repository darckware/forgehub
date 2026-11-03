"""M0.7: environment_releases (what is published in each environment).

Plano Integrado Onda 1, M0.7 (docs/architecture/MISSION_EXECUTIONS_SCREEN_SPEC.md
§6; MCP_MISSION_TOOLS_SPEC.md §11 D-M0-1/D-M0-7). One row per recorded
release; the latest row per (environment, target) is what the mission
executions screen shows. Written only by POST /api/v1/environments/releases.

Revision ID: f3a9c6d1b8e2
Revises: b9f246c18a73
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f3a9c6d1b8e2"
down_revision = "b9f246c18a73"
branch_labels = None
depends_on = None

SCHEMA = "company"


def upgrade() -> None:
    op.create_table(
        "environment_releases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("environment", sa.String(20), nullable=False),
        sa.Column("target", sa.String(200), nullable=False),
        sa.Column("commit_sha", sa.String(40), nullable=False),
        sa.Column("branch", sa.String(255), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_by", sa.String(255), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey(f"{SCHEMA}.project_tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("evidence_ref", sa.String(500), nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="recorded"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("environment IN ('test', 'production')", name="ck_environment_releases_environment"),
        sa.CheckConstraint("source IN ('recorded', 'imported')", name="ck_environment_releases_source"),
        sa.CheckConstraint("commit_sha ~ '^[0-9a-f]{40}$'", name="ck_environment_releases_commit_sha"),
        sa.UniqueConstraint("environment", "target", "released_at", name="uq_environment_releases_env_target_at"),
        schema=SCHEMA,
    )
    op.create_index("ix_environment_releases_latest", "environment_releases",
                    ["environment", "target", "released_at"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_environment_releases_latest", table_name="environment_releases", schema=SCHEMA)
    op.drop_table("environment_releases", schema=SCHEMA)

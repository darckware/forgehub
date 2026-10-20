"""add Nexo installation tracking

Revision ID: 5a8c1e7d9f20
Revises: 40e6bb284f7b
Create Date: 2026-09-08 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "5a8c1e7d9f20"
down_revision: Union[str, Sequence[str], None] = "40e6bb284f7b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "company"


def upgrade() -> None:
    op.create_table(
        "nexo_agent_builds",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("git_sha", sa.String(40), nullable=False),
        sa.Column("agent_version", sa.String(50), nullable=False),
        sa.Column("os_kind", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("artifact_path", sa.String(500), nullable=True),
        sa.Column("artifact_size", sa.BigInteger(), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("build_log_excerpt", sa.String(2000), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("os_kind IN ('linux', 'windows')", name="ck_nexo_agent_builds_os_kind"),
        sa.CheckConstraint(
            "status IN ('queued', 'building', 'ready', 'failed')",
            name="ck_nexo_agent_builds_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("git_sha", "os_kind", name="uq_nexo_agent_builds_sha_os"),
        schema=SCHEMA,
    )
    op.create_index("ix_nexo_agent_builds_status", "nexo_agent_builds", ["status"], schema=SCHEMA)

    op.create_table(
        "workstation_installations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workstation_id", sa.UUID(), nullable=False),
        sa.Column("build_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("package_generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("online_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('package_ready', 'downloaded', 'online', 'outdated', 'error')",
            name="ck_workstation_installations_status",
        ),
        sa.ForeignKeyConstraint(["workstation_id"], ["company.workstations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["build_id"], ["company.nexo_agent_builds.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workstation_id"),
        schema=SCHEMA,
    )

    op.create_table(
        "workstation_installation_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("installation_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("from_status", sa.String(20), nullable=True),
        sa.Column("to_status", sa.String(20), nullable=False),
        sa.Column("detail", sa.String(2000), nullable=True),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('package_generated', 'downloaded', 'first_report', "
            "'version_mismatch', 'error')",
            name="ck_workstation_installation_events_event_type",
        ),
        sa.CheckConstraint(
            "from_status IS NULL OR from_status IN "
            "('package_ready', 'downloaded', 'online', 'outdated', 'error')",
            name="ck_workstation_installation_events_from_status",
        ),
        sa.CheckConstraint(
            "to_status IN ('package_ready', 'downloaded', 'online', 'outdated', 'error')",
            name="ck_workstation_installation_events_to_status",
        ),
        sa.ForeignKeyConstraint(
            ["installation_id"],
            ["company.workstation_installations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["company.users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_workstation_installation_events_installation_created",
        "workstation_installation_events",
        ["installation_id", "created_at"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_workstation_installation_events_installation_created",
        table_name="workstation_installation_events",
        schema=SCHEMA,
    )
    op.drop_table("workstation_installation_events", schema=SCHEMA)
    op.drop_table("workstation_installations", schema=SCHEMA)
    op.drop_index("ix_nexo_agent_builds_status", table_name="nexo_agent_builds", schema=SCHEMA)
    op.drop_table("nexo_agent_builds", schema=SCHEMA)

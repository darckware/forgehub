"""add vpn operation events

Revision ID: 4e9d9c51a7b2
Revises: f6d9a3b7c210
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "4e9d9c51a7b2"
down_revision: str | None = "f6d9a3b7c210"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vpn_operation_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column("target", sa.String(length=20), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_code", sa.String(length=50), nullable=True),
        sa.Column("summary", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("action IN ('connect', 'disconnect', 'restart', 'test')", name="ck_vpn_operation_events_action"),
        sa.CheckConstraint("status IN ('running', 'succeeded', 'failed')", name="ck_vpn_operation_events_status"),
        sa.CheckConstraint("target IN ('local', 'remote')", name="ck_vpn_operation_events_target"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["company.users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        schema="company",
    )
    op.create_index(
        "ix_vpn_operation_events_created_at",
        "vpn_operation_events",
        ["created_at"],
        unique=False,
        schema="company",
    )
    op.create_index(
        "ix_vpn_operation_events_target_created_at",
        "vpn_operation_events",
        ["target", "created_at"],
        unique=False,
        schema="company",
    )


def downgrade() -> None:
    op.drop_index("ix_vpn_operation_events_target_created_at", table_name="vpn_operation_events", schema="company")
    op.drop_index("ix_vpn_operation_events_created_at", table_name="vpn_operation_events", schema="company")
    op.drop_table("vpn_operation_events", schema="company")

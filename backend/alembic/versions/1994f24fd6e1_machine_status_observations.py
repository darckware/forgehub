"""machine status observations (Remote Access phase 4, gap 10)

The last status the machine status monitor observed per machine, so its
15-minute pass alerts on transitions only and never re-alerts after a restart.

Revision ID: 1994f24fd6e1
Revises: e6f2d4a89cb7
Create Date: 2026-11-12
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "1994f24fd6e1"
down_revision = "e6f2d4a89cb7"
branch_labels = None
depends_on = None

SCHEMA = "company"


def upgrade() -> None:
    op.create_table(
        "machine_status_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "server_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.servers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("since", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pending_status", sa.String(32), nullable=True),
        sa.Column("pending_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mass_batch", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('complete', 'partial', 'not_prepared', 'offline', 'unknown')",
            name="ck_machine_status_observations_status",
        ),
        sa.CheckConstraint(
            "pending_status IS NULL OR pending_status IN "
            "('complete', 'partial', 'not_prepared', 'offline', 'unknown')",
            name="ck_machine_status_observations_pending_status",
        ),
        sa.UniqueConstraint("server_id", name="uq_machine_status_observations_server_id"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("machine_status_observations", schema=SCHEMA)

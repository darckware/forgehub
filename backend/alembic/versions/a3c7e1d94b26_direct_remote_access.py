"""Direct remote access: purpose/elevation on a delegation, origin on each result.

Revision ID: a3c7e1d94b26
Revises: f7a1b2c3d4e5
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "a3c7e1d94b26"
down_revision = "f7a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("authority_delegations", sa.Column("purpose", sa.String(20), nullable=True), schema="company")
    op.add_column("authority_delegations", sa.Column(
        "allow_elevation", sa.Boolean, nullable=False, server_default=sa.false()), schema="company")
    op.create_check_constraint(
        "ck_authority_delegations_purpose", "authority_delegations",
        "purpose IS NULL OR purpose IN ('development', 'support')", schema="company")
    op.add_column("host_execution_results", sa.Column(
        "delegation_id", UUID(as_uuid=True),
        sa.ForeignKey("company.authority_delegations.id", ondelete="SET NULL"), nullable=True), schema="company")
    op.create_index("ix_host_execution_results_delegation", "host_execution_results", ["delegation_id"], schema="company")


def downgrade():
    op.drop_index("ix_host_execution_results_delegation", table_name="host_execution_results", schema="company")
    op.drop_column("host_execution_results", "delegation_id", schema="company")
    op.drop_constraint("ck_authority_delegations_purpose", "authority_delegations", schema="company")
    op.drop_column("authority_delegations", "allow_elevation", schema="company")
    op.drop_column("authority_delegations", "purpose", schema="company")

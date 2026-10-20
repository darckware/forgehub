"""Operator deliberation and contextual consolidation of Messages.

Revision ID: d4f9a2c6e8b1
Revises: c3e8a1f5d2b7
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d4f9a2c6e8b1"
down_revision = "c3e8a1f5d2b7"
branch_labels = None
depends_on = None


def upgrade():
    for column in (
        sa.Column("context_area", sa.String(100), nullable=True),
        sa.Column("consolidated_into_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("approval_status", sa.String(20), nullable=True),
        sa.Column("approved_content_hash", sa.String(64), nullable=True),
        sa.Column("decision_reminded_at", sa.DateTime(timezone=True), nullable=True),
    ):
        op.add_column("agent_demands", column, schema="company")
    op.create_foreign_key("fk_demand_consolidation", "agent_demands", "agent_demands", ["consolidated_into_id"], ["id"], source_schema="company", referent_schema="company", ondelete="RESTRICT")
    op.create_index("ix_company_agent_demands_consolidated_into_id", "agent_demands", ["consolidated_into_id"], schema="company")
    op.create_check_constraint("ck_demand_approval_status", "agent_demands", "approval_status IS NULL OR approval_status IN ('pending', 'approved', 'rejected')", schema="company")
    op.create_check_constraint("ck_demand_not_self_consolidated", "agent_demands", "consolidated_into_id IS NULL OR consolidated_into_id <> id", schema="company")


def downgrade():
    op.drop_constraint("ck_demand_not_self_consolidated", "agent_demands", schema="company")
    op.drop_constraint("ck_demand_approval_status", "agent_demands", schema="company")
    op.drop_index("ix_company_agent_demands_consolidated_into_id", "agent_demands", schema="company")
    op.drop_constraint("fk_demand_consolidation", "agent_demands", schema="company")
    for name in ("decision_reminded_at", "approved_content_hash", "approval_status", "requires_approval", "consolidated_into_id", "context_area"):
        op.drop_column("agent_demands", name, schema="company")

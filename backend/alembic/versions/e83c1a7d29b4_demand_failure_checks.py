"""Link diagnostic checks to failed execution messages.

Revision ID: e83c1a7d29b4
Revises: f2c7a4e9b1d3
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e83c1a7d29b4"
down_revision = "f2c7a4e9b1d3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("agent_demands", sa.Column("failure_check_source_id", postgresql.UUID(as_uuid=True), nullable=True), schema="company")
    op.create_foreign_key("fk_demands_failure_check_source", "agent_demands", "agent_demands", ["failure_check_source_id"], ["id"], source_schema="company", referent_schema="company", ondelete="RESTRICT")
    op.create_index("uq_agent_demands_failure_check_source", "agent_demands", ["failure_check_source_id"], schema="company", unique=True)
    op.create_check_constraint("ck_demands_check_not_self", "agent_demands", "failure_check_source_id IS NULL OR failure_check_source_id <> id", schema="company")


def downgrade():
    op.drop_constraint("ck_demands_check_not_self", "agent_demands", schema="company", type_="check")
    op.drop_index("uq_agent_demands_failure_check_source", table_name="agent_demands", schema="company")
    op.drop_constraint("fk_demands_failure_check_source", "agent_demands", schema="company", type_="foreignkey")
    op.drop_column("agent_demands", "failure_check_source_id", schema="company")

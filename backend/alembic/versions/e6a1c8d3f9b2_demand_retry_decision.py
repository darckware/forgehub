"""Preserve lifetime attempts when an operator authorizes a new retry budget."""
import sqlalchemy as sa
from alembic import op

revision = "e6a1c8d3f9b2"
down_revision = "d4f9a2c6e8b1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("agent_demands", sa.Column("retry_limit", sa.Integer(), nullable=False, server_default="3"), schema="company")
    op.add_column("agent_demands", sa.Column("decision_reason", sa.Text(), nullable=True), schema="company")
    op.create_check_constraint("ck_demand_retry_limit", "agent_demands", "retry_limit >= 3", schema="company")


def downgrade():
    op.drop_constraint("ck_demand_retry_limit", "agent_demands", schema="company")
    op.drop_column("agent_demands", "decision_reason", schema="company")
    op.drop_column("agent_demands", "retry_limit", schema="company")

"""Link an agent's maintenance run to the Messages task that asked for it.

Revision ID: c3e8a1f5d2b7
Revises: b7d2e9f4c1a3

2026-10-19: an agent maintains machines only on a task (Messages), and the
run is checked against what that task allowed (machines, scripts). The link
also lets a machine's history point at the request and its answer.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c3e8a1f5d2b7"
down_revision = "b7d2e9f4c1a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "host_executions",
        sa.Column("agent_demand_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="company",
    )
    op.create_foreign_key(
        "fk_host_executions_agent_demand", "host_executions", "agent_demands",
        ["agent_demand_id"], ["id"], source_schema="company", referent_schema="company", ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_host_executions_agent_demand", "host_executions", schema="company", type_="foreignkey")
    op.drop_column("host_executions", "agent_demand_id", schema="company")

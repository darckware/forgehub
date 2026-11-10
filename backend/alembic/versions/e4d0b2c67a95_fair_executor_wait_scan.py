"""Persist fair bounded executor-wait reevaluation without editing task content."""
from alembic import op
import sqlalchemy as sa

revision = "e4d0b2c67a95"
down_revision = "e3d9a1c56f84"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("agent_demands", sa.Column("executor_wait_checked_at", sa.DateTime(timezone=True)),
                  schema="company")
    op.create_index("ix_demand_executor_wait_scan", "agent_demands",
                    [sa.text("executor_wait_checked_at ASC NULLS FIRST"), "scheduled_at", "number"],
                    schema="company", postgresql_where=sa.text(
                        "dispatch_status IS NULL AND agent_run_id IS NULL AND origin_type = 'task' "
                        "AND status != 'archived'"))


def downgrade():
    op.execute("DROP INDEX IF EXISTS company.ix_demand_executor_wait_scan")
    op.drop_column("agent_demands", "executor_wait_checked_at", schema="company")

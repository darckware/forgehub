"""Identify expired host execution output without deleting audit history."""
from alembic import op
import sqlalchemy as sa

revision = "e2c8d0b45e73"
down_revision = "e1b7c9a34d62"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("host_execution_results", sa.Column("output_expired", sa.Boolean(), nullable=False,
        server_default=sa.text("false")), schema="company")
    op.create_index("ix_host_results_output_retention", "host_execution_results", ["finished_at", "id"],
        schema="company", postgresql_where=sa.text("output_expired = false AND status IN ('succeeded', 'failed', 'skipped')"))


def downgrade() -> None:
    op.drop_index("ix_host_results_output_retention", table_name="host_execution_results", schema="company")
    op.drop_column("host_execution_results", "output_expired", schema="company")

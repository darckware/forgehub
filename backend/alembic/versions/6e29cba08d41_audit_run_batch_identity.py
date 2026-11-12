"""Identify checklist batches without changing individual observation times."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "6e29cba08d41"
down_revision = "4c219b76ae03"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("audit_check_runs", sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=True), schema="company")
    op.create_index("ix_company_audit_check_runs_batch_id", "audit_check_runs", ["batch_id"], schema="company")


def downgrade():
    op.drop_index("ix_company_audit_check_runs_batch_id", table_name="audit_check_runs", schema="company")
    op.drop_column("audit_check_runs", "batch_id", schema="company")

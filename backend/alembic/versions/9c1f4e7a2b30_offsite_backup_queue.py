"""Off-site backup runs can wait in a queue.

Revision ID: 9c1f4e7a2b30
Revises: 7d8820d5bfb2
"""
from alembic import op

revision = "9c1f4e7a2b30"
down_revision = "7d8820d5bfb2"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_offsite_backup_run_status", "offsite_backup_runs", schema="company")
    op.create_check_constraint(
        "ck_offsite_backup_run_status", "offsite_backup_runs",
        "status IN ('queued', 'running', 'ok', 'failed', 'interrupted')", schema="company",
    )
    op.alter_column("offsite_backup_runs", "started_at", nullable=True, schema="company")
    op.create_index(
        "ix_offsite_backup_runs_status_created", "offsite_backup_runs", ["status", "created_at"], schema="company"
    )


def downgrade():
    op.drop_index("ix_offsite_backup_runs_status_created", table_name="offsite_backup_runs", schema="company")
    op.execute("DELETE FROM company.offsite_backup_runs WHERE status = 'queued'")
    op.alter_column("offsite_backup_runs", "started_at", nullable=False, schema="company")
    op.drop_constraint("ck_offsite_backup_run_status", "offsite_backup_runs", schema="company")
    op.create_check_constraint(
        "ck_offsite_backup_run_status", "offsite_backup_runs",
        "status IN ('running', 'ok', 'failed', 'interrupted')", schema="company",
    )

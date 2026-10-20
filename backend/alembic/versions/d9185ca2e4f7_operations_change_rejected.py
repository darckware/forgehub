"""Represent A2 proposals declined by Marcelo.

Revision ID: d9185ca2e4f7
Revises: b29f76c8e10a
"""

from alembic import op

revision = "d9185ca2e4f7"
down_revision = "b29f76c8e10a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_operations_changes_status", "operations_changes", schema="company", type_="check")
    op.create_check_constraint(
        "ck_operations_changes_status", "operations_changes",
        "status IN ('proposed', 'awaiting_approval', 'evaluating', 'kept', 'reverted', 'rejected')",
        schema="company",
    )


def downgrade() -> None:
    op.execute("UPDATE company.operations_changes SET status = 'reverted' WHERE status = 'rejected'")
    op.drop_constraint("ck_operations_changes_status", "operations_changes", schema="company", type_="check")
    op.create_check_constraint(
        "ck_operations_changes_status", "operations_changes",
        "status IN ('proposed', 'awaiting_approval', 'evaluating', 'kept', 'reverted')",
        schema="company",
    )

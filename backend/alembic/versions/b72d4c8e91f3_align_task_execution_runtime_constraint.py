"""align task execution runtime constraint

Revision ID: b72d4c8e91f3
Revises: a41c8e7d2f90
Create Date: 2026-08-14 20:15:00
"""
from typing import Sequence, Union

from alembic import op


revision: str = "b72d4c8e91f3"
down_revision: Union[str, Sequence[str], None] = "a41c8e7d2f90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "company"
CONSTRAINT = "ck_task_executions_runtime_type"


def upgrade() -> None:
    """Replace the stale antigravity constraint with the canonical agy value."""
    op.drop_constraint(
        CONSTRAINT,
        "task_executions",
        schema=SCHEMA,
        type_="check",
    )
    op.execute(
        "UPDATE company.task_executions "
        "SET runtime_type = 'agy' WHERE runtime_type = 'antigravity'"
    )
    op.create_check_constraint(
        CONSTRAINT,
        "task_executions",
        "runtime_type IS NULL OR runtime_type IN ('claude', 'codex', 'agy')",
        schema=SCHEMA,
    )


def downgrade() -> None:
    """Restore the legacy runtime name and its original constraint."""
    op.drop_constraint(
        CONSTRAINT,
        "task_executions",
        schema=SCHEMA,
        type_="check",
    )
    op.execute(
        "UPDATE company.task_executions "
        "SET runtime_type = 'antigravity' WHERE runtime_type = 'agy'"
    )
    op.create_check_constraint(
        CONSTRAINT,
        "task_executions",
        "runtime_type IS NULL OR runtime_type IN ('claude', 'codex', 'antigravity')",
        schema=SCHEMA,
    )

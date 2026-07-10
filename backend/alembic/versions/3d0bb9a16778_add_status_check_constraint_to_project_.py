"""add status check constraint to project_tasks

Revision ID: 3d0bb9a16778
Revises: 91bd82affb72
Create Date: 2026-06-23 23:00:53.136705

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3d0bb9a16778'
down_revision: Union[str, Sequence[str], None] = '91bd82affb72'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TASK_STATUSES = ("planned", "assigned", "in_progress", "blocked", "done", "deployed", "cancelled")


def upgrade() -> None:
    """Upgrade schema."""
    op.create_check_constraint(
        "ck_project_tasks_status",
        "project_tasks",
        f"status IN {TASK_STATUSES!r}",
        schema="company",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_project_tasks_status", "project_tasks", schema="company", type_="check")

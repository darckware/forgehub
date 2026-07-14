"""add orchestration timestamp defaults

Revision ID: 8b1f6a3d2c40
Revises: 7d4a2c1e9b60
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8b1f6a3d2c40"
down_revision: Union[str, Sequence[str], None] = "7d4a2c1e9b60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES = (
    "agent_runtime_profiles",
    "project_agent_memberships",
    "project_loop_policies",
    "task_execution_reviews",
)


def upgrade() -> None:
    for table in TABLES:
        op.alter_column(
            table,
            "created_at",
            schema="company",
            server_default=sa.text("now()"),
        )
        op.alter_column(
            table,
            "updated_at",
            schema="company",
            server_default=sa.text("now()"),
        )


def downgrade() -> None:
    for table in TABLES:
        op.alter_column(table, "created_at", schema="company", server_default=None)
        op.alter_column(table, "updated_at", schema="company", server_default=None)

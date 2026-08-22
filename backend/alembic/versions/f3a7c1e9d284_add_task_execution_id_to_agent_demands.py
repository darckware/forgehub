"""add task_execution_id to agent_demands

Revision ID: f3a7c1e9d284
Revises: 6bd92eeab902
Create Date: 2026-08-17

Layered task-execution governance, Fase 1.2 (plan: resilient-twirling-blossom).
Dedicated FK to task_executions.id rather than reusing origin_id (which names
the *task*, not a single attempt) -- a task can have multiple executions/
retries, and _finalize_dispatch (demand.py) needs to know exactly which
attempt to close, not "the latest one for this task" (a race against a
concurrent retry).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f3a7c1e9d284"
down_revision: Union[str, Sequence[str], None] = "6bd92eeab902"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_demands",
        sa.Column("task_execution_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="company",
    )
    op.create_foreign_key(
        "fk_agent_demands_task_execution_id",
        "agent_demands",
        "task_executions",
        ["task_execution_id"],
        ["id"],
        source_schema="company",
        referent_schema="company",
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_agent_demands_task_execution_id", "agent_demands", schema="company", type_="foreignkey"
    )
    op.drop_column("agent_demands", "task_execution_id", schema="company")

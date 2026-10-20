"""retire pending dispatch status

Revision ID: 60bb40510cb4
Revises: b72d4c8e91f3
Create Date: 2026-08-15 00:00:00
"""
from typing import Sequence, Union

from alembic import op


revision: str = "60bb40510cb4"
down_revision: Union[str, Sequence[str], None] = "b72d4c8e91f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "company"
CONSTRAINT = "ck_agent_demands_dispatch_status"


def upgrade() -> None:
    """"pending" never had a writer -- every real dispatch path goes straight
    from NULL to "dispatched" (run_scheduled_dispatch_pass -> _execute_dispatch,
    see db/models/demand.py's DEMAND_DISPATCH_STATUSES docstring). No backfill
    needed: there is nothing to migrate, by construction."""
    op.drop_constraint(CONSTRAINT, "agent_demands", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        CONSTRAINT,
        "agent_demands",
        "dispatch_status IS NULL OR dispatch_status IN "
        "('dispatched', 'running', 'completed', 'failed')",
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT, "agent_demands", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        CONSTRAINT,
        "agent_demands",
        "dispatch_status IS NULL OR dispatch_status IN "
        "('pending', 'dispatched', 'running', 'completed', 'failed')",
        schema=SCHEMA,
    )

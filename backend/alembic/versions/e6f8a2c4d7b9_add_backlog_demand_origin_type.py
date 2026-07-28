"""add backlog demand origin_type

Revision ID: e6f8a2c4d7b9
Revises: d5e7f9a1b3c5
Create Date: 2026-07-26 01:55:00.000000

Adds "backlog" to agent_demands.origin_type ("Tipo" in the compose form).

Unlike "task"/"demand", it's a classification rather than a polymorphic
link -- it never carries an origin_id. It marks parked work: addressed or
not, not a task yet, and deliberately not dispatchable. Promoting it to
"task" is what puts it in play (see the reading pane's "Promover a Task").

The sidebar has had a *Backlog group* since 2026-07-25 with no matching
type behind it, which forced that group to define itself by dispatch state
instead of by what the item actually is.

Chains onto d5e7f9a1b3c5 (the demand lineage). The repo has had two
independent Alembic heads since before this change -- this keeps the count
at two rather than adding a third.
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'e6f8a2c4d7b9'
down_revision: Union[str, Sequence[str], None] = 'd5e7f9a1b3c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONSTRAINT = 'ck_agent_demands_origin_type'


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint(CONSTRAINT, 'agent_demands', schema='company', type_='check')
    op.create_check_constraint(
        CONSTRAINT,
        'agent_demands',
        "origin_type IS NULL OR origin_type IN ('task', 'demand', 'backlog')",
        schema='company',
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Anything already filed as backlog would violate the narrower
    # constraint -- park it back as unclassified rather than fail the
    # downgrade or silently mislabel it as a task.
    op.execute(
        "UPDATE company.agent_demands SET origin_type = NULL WHERE origin_type = 'backlog'"
    )
    op.drop_constraint(CONSTRAINT, 'agent_demands', schema='company', type_='check')
    op.create_check_constraint(
        CONSTRAINT,
        'agent_demands',
        "origin_type IS NULL OR origin_type IN ('task', 'demand')",
        schema='company',
    )

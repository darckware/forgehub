"""drop demand origin_task_number

Revision ID: d5e7f9a1b3c5
Revises: c4d6e8f0a1b3
Create Date: 2026-07-25 00:20:00.000000

Unifies the demand origin reference: origin_id is now polymorphic
(AgentDemand.id for origin_type="demand", ProjectTask.id for
origin_type="task" -- resolvable now that ProjectTask has its own
`number`, see migration c4d6e8f0a1b3) instead of splitting the "task"
case into a separate, non-referential origin_task_number label.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd5e7f9a1b3c5'
down_revision: Union[str, Sequence[str], None] = 'c4d6e8f0a1b3'
branch_labels: Union[str, Sequence[str], None] = None
# The other historical branch creates the column and dispatch constraints.
depends_on: Union[str, Sequence[str], None] = 'e0a2199046cf'


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column('agent_demands', 'origin_task_number', schema='company')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('agent_demands', sa.Column('origin_task_number', sa.Integer(), nullable=True), schema='company')

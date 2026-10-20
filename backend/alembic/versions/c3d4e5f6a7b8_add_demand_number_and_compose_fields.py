"""add demand display number

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-24 00:00:00.000000

NOTE: same pre-existing two-heads situation noted in 8c829b7454d6 -- this
migration only extends that branch, it does not merge d718c040a4b3.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'agent_demands',
        sa.Column('number', sa.Integer(), sa.Identity(always=False), nullable=False),
        schema='company',
    )
    op.create_unique_constraint('uq_agent_demands_number', 'agent_demands', ['number'], schema='company')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_agent_demands_number', 'agent_demands', schema='company', type_='unique')
    op.drop_column('agent_demands', 'number', schema='company')

"""add demand task execution timestamp

Revision ID: c123b75b24d4
Revises: 7d94ecaef8f6
Create Date: 2026-07-24 19:49:47.256827

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c123b75b24d4'
down_revision: Union[str, Sequence[str], None] = '7d94ecaef8f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('agent_demands', sa.Column('task_execution_at', sa.DateTime(timezone=True), nullable=True), schema='company')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('agent_demands', 'task_execution_at', schema='company')

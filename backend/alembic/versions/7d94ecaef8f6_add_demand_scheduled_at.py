"""add demand scheduled_at

Revision ID: 7d94ecaef8f6
Revises: e0a2199046cf
Create Date: 2026-07-24 18:48:31.216683

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '7d94ecaef8f6'
down_revision: Union[str, Sequence[str], None] = 'e0a2199046cf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('agent_demands', sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True), schema='company')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('agent_demands', 'scheduled_at', schema='company')

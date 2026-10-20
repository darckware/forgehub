"""add demand agent_processed_at

Revision ID: f22fbe0127fd
Revises: d79e1389940b
Create Date: 2026-07-24 22:12:55.692294

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f22fbe0127fd'
down_revision: Union[str, Sequence[str], None] = 'd79e1389940b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('agent_demands', sa.Column('agent_processed_at', sa.DateTime(timezone=True), nullable=True), schema='company')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('agent_demands', 'agent_processed_at', schema='company')

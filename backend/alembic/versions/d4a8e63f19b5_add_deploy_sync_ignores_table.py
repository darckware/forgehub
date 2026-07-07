"""add deploy_sync_ignores table

Revision ID: d4a8e63f19b5
Revises: c9f4a17d52e8
Create Date: 2026-07-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4a8e63f19b5'
down_revision: Union[str, Sequence[str], None] = 'c9f4a17d52e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('deploy_sync_ignores',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('container_name', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('container_name'),
    schema='company'
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('deploy_sync_ignores', schema='company')

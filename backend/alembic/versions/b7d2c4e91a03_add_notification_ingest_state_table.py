"""add notification ingest state table

Revision ID: b7d2c4e91a03
Revises: a4d81f0c2b77
Create Date: 2026-07-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7d2c4e91a03'
down_revision: Union[str, Sequence[str], None] = 'a4d81f0c2b77'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('notification_ingest_state',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('source', sa.String(length=50), nullable=False),
    sa.Column('suppress_before', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source'),
    schema='company'
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('notification_ingest_state', schema='company')

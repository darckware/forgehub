"""add notifications table

Revision ID: a4d81f0c2b77
Revises: c91e2ab77f10
Create Date: 2026-07-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4d81f0c2b77'
down_revision: Union[str, Sequence[str], None] = 'c91e2ab77f10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('notifications',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('source', sa.String(length=50), nullable=False),
    sa.Column('severity', sa.String(length=50), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('message', sa.Text(), nullable=True),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('job_id', sa.String(length=255), nullable=True),
    sa.Column('job_name', sa.String(length=255), nullable=True),
    sa.Column('profile', sa.String(length=100), nullable=True),
    sa.Column('script_name', sa.String(length=255), nullable=True),
    sa.Column('event_key', sa.String(length=512), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("source IN ('cron', 'system')", name='ck_notifications_source'),
    sa.CheckConstraint("severity IN ('info', 'success', 'warning', 'error')", name='ck_notifications_severity'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('event_key'),
    schema='company'
    )
    op.create_index('ix_notifications_occurred_at', 'notifications', ['occurred_at'], unique=False, schema='company')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_notifications_occurred_at', table_name='notifications', schema='company')
    op.drop_table('notifications', schema='company')

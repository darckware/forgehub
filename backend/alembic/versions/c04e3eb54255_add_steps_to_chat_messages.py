"""add steps to chat_messages

Revision ID: c04e3eb54255
Revises: 2664534a504d
Create Date: 2026-07-16 01:31:39.806690

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c04e3eb54255'
down_revision: Union[str, Sequence[str], None] = '2664534a504d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Note: autogenerate also proposed dropping approval_requests' partial
    # unique index (uq_approval_requests_pending_target) -- a known false
    # positive with postgresql_where partial indexes, unrelated to this
    # migration's actual change. Left out deliberately.
    op.add_column('chat_messages', sa.Column('steps', postgresql.JSONB(astext_type=sa.Text()), nullable=True), schema='company')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('chat_messages', 'steps', schema='company')

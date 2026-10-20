"""add chat_sessions working_directory_path

Revision ID: ff98a10e7daa
Revises: 25707ceceaf5
Create Date: 2026-07-28 14:30:25.551296

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'ff98a10e7daa'
down_revision: Union[str, Sequence[str], None] = '25707ceceaf5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# NOTE: autogenerate also detected a drop of the 'uq_approval_requests_pending_target'
# index and 'chat_messages.steps' column -- pre-existing drift unrelated to this
# migration (see every prior migration in this feature set for the same note).
# Deliberately NOT included here; left for whoever owns that drift to address.


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('chat_sessions', sa.Column('working_directory_path', sa.String(length=1024), nullable=True), schema='company')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('chat_sessions', 'working_directory_path', schema='company')

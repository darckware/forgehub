"""add chat_groups and chat_sessions.group_id

Revision ID: b27855f20f54
Revises: ff98a10e7daa
Create Date: 2026-07-28 17:43:45.581107

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b27855f20f54'
down_revision: Union[str, Sequence[str], None] = 'ff98a10e7daa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Scoped to this feature only -- autogenerate also picked up unrelated
    # pre-existing drift (approval_requests index, chat_messages.steps
    # column) from other in-progress work; deliberately left out here.
    op.create_table('chat_groups',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    schema='company'
    )
    op.add_column('chat_sessions', sa.Column('group_id', sa.UUID(), nullable=True), schema='company')
    op.create_foreign_key(op.f('chat_sessions_group_id_fkey'), 'chat_sessions', 'chat_groups', ['group_id'], ['id'], source_schema='company', referent_schema='company', ondelete='SET NULL')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f('chat_sessions_group_id_fkey'), 'chat_sessions', schema='company', type_='foreignkey')
    op.drop_column('chat_sessions', 'group_id', schema='company')
    op.drop_table('chat_groups', schema='company')

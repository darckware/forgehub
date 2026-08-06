"""add chat_channels.orchestrator_agent_id

Revision ID: e7a1f2c9b4d6
Revises: 3cad0134cf1b
Create Date: 2026-08-05 15:00:00.000000

Hand-written (not autogenerate), same rationale as the two prior channel
migrations: avoids sweeping in pre-existing unrelated model/DB drift. See
docs/architecture/CHANNEL_AGENT_ROLES_AND_ORCHESTRATION.md -- this column is
a purely informational label ("who Marcelo intends as the operational
coordinator among this channel's agent members"); it grants no authority by
itself, that stays on governance.AuthorityDelegation.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e7a1f2c9b4d6'
down_revision: Union[str, Sequence[str], None] = '3cad0134cf1b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'chat_channels',
        sa.Column('orchestrator_agent_id', postgresql.UUID(as_uuid=True), nullable=True),
        schema='company',
    )
    op.create_foreign_key(
        'fk_chat_channels_orchestrator_agent_id',
        'chat_channels', 'agents',
        ['orchestrator_agent_id'], ['id'],
        source_schema='company', referent_schema='company', ondelete='SET NULL',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        'fk_chat_channels_orchestrator_agent_id', 'chat_channels', schema='company', type_='foreignkey'
    )
    op.drop_column('chat_channels', 'orchestrator_agent_id', schema='company')

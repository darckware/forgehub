"""add openclaw runtime_type for agents

Revision ID: f5bd6aa4aff8
Revises: afbb96534853
Create Date: 2026-07-25 02:13:35.433262

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f5bd6aa4aff8'
down_revision: Union[str, Sequence[str], None] = 'afbb96534853'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint('ck_agents_runtime_type', 'agents', schema='company', type_='check')
    op.create_check_constraint(
        'ck_agents_runtime_type',
        'agents',
        "runtime_type IS NULL OR runtime_type IN ('claude', 'codex', 'agy', 'hermes', 'openclaw')",
        schema='company',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_agents_runtime_type', 'agents', schema='company', type_='check')
    op.create_check_constraint(
        'ck_agents_runtime_type',
        'agents',
        "runtime_type IS NULL OR runtime_type IN ('claude', 'codex', 'agy', 'hermes')",
        schema='company',
    )

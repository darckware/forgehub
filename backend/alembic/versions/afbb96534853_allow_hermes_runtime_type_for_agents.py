"""allow hermes runtime_type for agents

Revision ID: afbb96534853
Revises: f22fbe0127fd
Create Date: 2026-07-25 01:40:04.768891

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'afbb96534853'
down_revision: Union[str, Sequence[str], None] = 'f22fbe0127fd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint('ck_agents_runtime_type', 'agents', schema='company', type_='check')
    op.create_check_constraint(
        'ck_agents_runtime_type',
        'agents',
        "runtime_type IS NULL OR runtime_type IN ('claude', 'codex', 'agy', 'hermes')",
        schema='company',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_agents_runtime_type', 'agents', schema='company', type_='check')
    op.create_check_constraint(
        'ck_agents_runtime_type',
        'agents',
        "runtime_type IS NULL OR runtime_type IN ('claude', 'codex', 'agy')",
        schema='company',
    )

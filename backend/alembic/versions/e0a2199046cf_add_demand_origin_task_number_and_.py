"""add demand origin task number and requires response

Revision ID: e0a2199046cf
Revises: c3d4e5f6a7b8
Create Date: 2026-07-24 18:09:31.909085

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e0a2199046cf'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('agent_demands', sa.Column('origin_task_number', sa.Integer(), nullable=True), schema='company')
    op.add_column(
        'agent_demands',
        sa.Column('requires_response', sa.Boolean(), nullable=False, server_default=sa.false()),
        schema='company',
    )
    op.alter_column('agent_demands', 'requires_response', server_default=None, schema='company')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('agent_demands', 'requires_response', schema='company')
    op.drop_column('agent_demands', 'origin_task_number', schema='company')

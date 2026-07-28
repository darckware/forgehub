"""add project_task display number

Revision ID: c4d6e8f0a1b3
Revises: b2c4d6e8f0a1
Create Date: 2026-07-25 00:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c4d6e8f0a1b3'
down_revision: Union[str, Sequence[str], None] = 'b2c4d6e8f0a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'project_tasks',
        sa.Column('number', sa.Integer(), sa.Identity(always=False), nullable=False),
        schema='company',
    )
    op.create_unique_constraint('uq_project_tasks_number', 'project_tasks', ['number'], schema='company')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_project_tasks_number', 'project_tasks', schema='company', type_='unique')
    op.drop_column('project_tasks', 'number', schema='company')

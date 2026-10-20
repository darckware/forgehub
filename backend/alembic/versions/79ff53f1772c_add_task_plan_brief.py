"""add task plan_brief

Revision ID: 79ff53f1772c
Revises: 190281545b4f
Create Date: 2026-08-01 01:06:51.017721

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '79ff53f1772c'
down_revision: Union[str, Sequence[str], None] = '190281545b4f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Only project_tasks.plan_brief -- autogenerate also picked up the same
    unrelated pre-existing drift as 190281545b4f (approval_requests index,
    chat_messages.steps); left untouched here.
    """
    op.add_column('project_tasks', sa.Column('plan_brief', sa.Text(), nullable=True), schema='company')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('project_tasks', 'plan_brief', schema='company')

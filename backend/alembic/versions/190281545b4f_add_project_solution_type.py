"""add project solution_type

Revision ID: 190281545b4f
Revises: 42bc54a62079
Create Date: 2026-08-01 00:32:36.953046

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '190281545b4f'
down_revision: Union[str, Sequence[str], None] = '42bc54a62079'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Only projects.solution_type -- autogenerate also picked up unrelated
    pre-existing drift (approval_requests index, chat_messages.steps) not
    part of this change; left untouched here.
    """
    op.add_column('projects', sa.Column('solution_type', sa.String(length=20), nullable=True), schema='company')
    op.create_check_constraint(
        'ck_projects_solution_type',
        'projects',
        "solution_type IS NULL OR solution_type IN ('web_app', 'mobile_app', 'api_service', 'database', 'deploy')",
        schema='company',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_projects_solution_type', 'projects', schema='company', type_='check')
    op.drop_column('projects', 'solution_type', schema='company')

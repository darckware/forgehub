"""add project_type to projects

Revision ID: 0d160dcd7dbb
Revises: 60bb40510cb4
Create Date: 2026-08-15 12:48:38.035034

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0d160dcd7dbb'
down_revision: Union[str, Sequence[str], None] = '60bb40510cb4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('projects', sa.Column('project_type', sa.String(length=20), server_default='creation', nullable=False), schema='company')
    # autogenerate doesn't detect CheckConstraint additions (see
    # c36149f00511's own note) -- added by hand, same as every other
    # enum-like column in this codebase.
    op.create_check_constraint(
        "ck_projects_project_type",
        "projects",
        "project_type IN ('creation', 'maintenance')",
        schema="company",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_projects_project_type", "projects", schema="company", type_="check")
    op.drop_column('projects', 'project_type', schema='company')

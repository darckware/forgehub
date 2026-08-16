"""extend project solution types with automation migration analysis reporting

Revision ID: abea36ac8d3e
Revises: 9823e7890ae4
Create Date: 2026-08-15 23:37:18.637379

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'abea36ac8d3e'
down_revision: Union[str, Sequence[str], None] = '9823e7890ae4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OLD_TYPES = ("web_app", "mobile_app", "api_service", "database", "deploy")
NEW_TYPES = OLD_TYPES + ("automation", "data_migration", "data_analysis", "reporting")


def upgrade() -> None:
    """Upgrade schema."""
    # Autogenerate doesn't diff CheckConstraint bodies -- hand-written.
    op.drop_constraint("ck_projects_solution_type", "projects", schema="company", type_="check")
    op.create_check_constraint(
        "ck_projects_solution_type",
        "projects",
        f"solution_type IS NULL OR solution_type IN {NEW_TYPES!r}",
        schema="company",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_projects_solution_type", "projects", schema="company", type_="check")
    op.create_check_constraint(
        "ck_projects_solution_type",
        "projects",
        f"solution_type IS NULL OR solution_type IN {OLD_TYPES!r}",
        schema="company",
    )

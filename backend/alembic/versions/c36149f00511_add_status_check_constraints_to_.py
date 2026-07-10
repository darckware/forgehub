"""add status check constraints to projects, project_plans, change_requests

Revision ID: c36149f00511
Revises: 576dae402892
Create Date: 2026-06-23 21:01:26.959584

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c36149f00511'
down_revision: Union[str, Sequence[str], None] = '576dae402892'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    NOTE: hand-written -- Alembic's autogenerate does not detect
    CheckConstraint additions/removals, so the initial `revision
    --autogenerate` produced an empty upgrade()/downgrade() pair. Both
    target tables are empty in every known environment at the time of
    this migration, so no data backfill/cleanup is needed before adding
    these constraints.
    """
    op.create_check_constraint(
        "ck_projects_status",
        "projects",
        "status IN ('planned', 'active', 'on_hold', 'completed', 'cancelled')",
        schema="company",
    )
    op.create_check_constraint(
        "ck_project_plans_status",
        "project_plans",
        "status IN ('draft', 'approved', 'baselined', 'superseded')",
        schema="company",
    )
    op.create_check_constraint(
        "ck_change_requests_status",
        "change_requests",
        "status IN ('pending', 'approved', 'rejected', 'applied')",
        schema="company",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_change_requests_status", "change_requests", schema="company", type_="check")
    op.drop_constraint("ck_project_plans_status", "project_plans", schema="company", type_="check")
    op.drop_constraint("ck_projects_status", "projects", schema="company", type_="check")

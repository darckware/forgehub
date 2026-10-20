"""add planning_items.project_scope_item_id

Revision ID: 94cecfd3bb31
Revises: 8c829b7454d6
Create Date: 2026-07-22 00:00:00.000000

NOTE: same pre-existing two-heads situation noted in 8c829b7454d6 -- this
migration only extends that branch, it does not merge d718c040a4b3.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "94cecfd3bb31"
down_revision: Union[str, Sequence[str], None] = "8c829b7454d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "company"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "planning_items",
        sa.Column("project_scope_item_id", sa.UUID(), nullable=True),
        schema=SCHEMA,
    )
    op.create_foreign_key(
        "fk_planning_items_project_scope_item",
        "planning_items", "project_scope_items",
        ["project_scope_item_id"], ["id"],
        source_schema=SCHEMA, referent_schema=SCHEMA,
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_planning_items_project_scope_item", "planning_items", schema=SCHEMA, type_="foreignkey")
    op.drop_column("planning_items", "project_scope_item_id", schema=SCHEMA)

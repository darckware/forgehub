"""add concept project description, working directory and tech stack fields

Revision ID: 8c829b7454d6
Revises: e2c2222722ea
Create Date: 2026-07-21 00:00:00.000000

NOTE: branched off e2c2222722ea, one of two pre-existing divergent heads
(the other is d718c040a4b3) -- flagged to the repo owner as a pending
`alembic merge heads` cleanup, not something this migration attempts to fix.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "8c829b7454d6"
down_revision: Union[str, Sequence[str], None] = "e2c2222722ea"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "company"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "product_concept_revisions",
        sa.Column("project_description", sa.Text(), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "product_concept_revisions",
        sa.Column("working_directory_path", sa.String(length=1024), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "product_concept_revisions",
        sa.Column("tech_stack_decisions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("product_concept_revisions", "tech_stack_decisions", schema=SCHEMA)
    op.drop_column("product_concept_revisions", "working_directory_path", schema=SCHEMA)
    op.drop_column("product_concept_revisions", "project_description", schema=SCHEMA)

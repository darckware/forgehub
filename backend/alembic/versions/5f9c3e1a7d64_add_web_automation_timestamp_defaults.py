"""add web automation timestamp defaults

Revision ID: 5f9c3e1a7d64
Revises: 4e8b2d0f6c53
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "5f9c3e1a7d64"
down_revision: Union[str, Sequence[str], None] = "4e8b2d0f6c53"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "web_automation_routines",
        "created_at",
        schema="company",
        server_default=sa.text("now()"),
    )
    op.alter_column(
        "web_automation_routines",
        "updated_at",
        schema="company",
        server_default=sa.text("now()"),
    )


def downgrade() -> None:
    op.alter_column("web_automation_routines", "updated_at", schema="company", server_default=None)
    op.alter_column("web_automation_routines", "created_at", schema="company", server_default=None)

"""default ForgeRouter routing group to auto

Revision ID: a4d7e1c9f520
Revises: 9c2e4b8f1a73
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a4d7e1c9f520"
down_revision: Union[str, Sequence[str], None] = "9c2e4b8f1a73"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rows created before semantic routing existed inherited "standard".
    # Their model_ref was auto, so retain the original intended behavior.
    op.execute(
        "UPDATE company.agent_runtime_profiles "
        "SET routing_group = 'auto' "
        "WHERE routing_group = 'standard' AND model_ref = 'forgerouter/auto'"
    )
    op.alter_column(
        "agent_runtime_profiles",
        "routing_group",
        schema="company",
        server_default=sa.text("'auto'"),
    )


def downgrade() -> None:
    op.alter_column(
        "agent_runtime_profiles",
        "routing_group",
        schema="company",
        server_default=sa.text("'standard'"),
    )

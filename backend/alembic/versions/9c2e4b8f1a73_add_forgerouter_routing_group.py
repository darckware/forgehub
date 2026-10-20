"""add ForgeRouter routing group to runtime profiles

Revision ID: 9c2e4b8f1a73
Revises: 8b1f6a3d2c40
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9c2e4b8f1a73"
down_revision: Union[str, Sequence[str], None] = "8b1f6a3d2c40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_runtime_profiles",
        sa.Column("routing_group", sa.String(length=32), nullable=False, server_default="standard"),
        schema="company",
    )
    op.create_check_constraint(
        "ck_agent_runtime_profiles_routing_group",
        "agent_runtime_profiles",
        "routing_group IN ('auto', 'simple', 'standard', 'complex', 'reasoning', 'vision', 'audio', 'code')",
        schema="company",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_agent_runtime_profiles_routing_group",
        "agent_runtime_profiles",
        schema="company",
        type_="check",
    )
    op.drop_column("agent_runtime_profiles", "routing_group", schema="company")

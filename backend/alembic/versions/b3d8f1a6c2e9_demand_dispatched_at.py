"""AgentDemand.dispatched_at: when the latest dispatch started

Revision ID: b3d8f1a6c2e9
Revises: a7c2e9f4b1d6
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b3d8f1a6c2e9"
down_revision: Union[str, Sequence[str], None] = "a7c2e9f4b1d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
SCHEMA = "company"


def upgrade() -> None:
    op.add_column(
        "agent_demands",
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("agent_demands", "dispatched_at", schema=SCHEMA)

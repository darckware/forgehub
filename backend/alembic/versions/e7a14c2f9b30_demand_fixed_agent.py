"""Let a message keep its agent when that agent runs out of quota.

Revision ID: e7a14c2f9b30
Revises: d5e93a7b2c18
"""
from alembic import op
import sqlalchemy as sa

revision = "e7a14c2f9b30"
down_revision = "d5e93a7b2c18"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_demands", sa.Column("fixed_agent", sa.Boolean(), nullable=False,
                                             server_default=sa.false()), schema="company")


def downgrade() -> None:
    op.drop_column("agent_demands", "fixed_agent", schema="company")

"""remove obsolete chat message steps

Revision ID: dd853ac4226c
Revises: 7d1351f999f2
Create Date: 2026-08-14 18:05:33.995128

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'dd853ac4226c'
down_revision: Union[str, Sequence[str], None] = '7d1351f999f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove the pre-ActiveTurn tool-step snapshot.

    Runtime progress now lives in ``active_turns.steps`` and final chat
    messages never read or write this nullable column. No data is copied:
    ActiveTurn already owns the durable in-flight record and historical
    ChatMessage rows did not expose this field through the API.
    """
    op.drop_column("chat_messages", "steps", schema="company")


def downgrade() -> None:
    op.add_column(
        "chat_messages",
        sa.Column("steps", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema="company",
    )

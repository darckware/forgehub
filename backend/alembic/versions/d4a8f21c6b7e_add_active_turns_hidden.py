"""Add active_turns.hidden

2026-08-14: a chat turn ended by the new explicit Stop route persists its
partial reply from this row (ActiveTurn.live_text/steps), not from the
in-memory state of the request that started it -- see chat.py's
`stop_chat_turn`. Without knowing whether the original turn was `hidden` (an
Assistant-panel priming call, never shown in the transcript), a stopped
hidden turn's partial content would leak into the visible conversation.

Revision ID: d4a8f21c6b7e
Revises: c9e51f082a34
Create Date: 2026-08-14
"""
import sqlalchemy as sa
from alembic import op

revision = "d4a8f21c6b7e"
down_revision = "c9e51f082a34"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "active_turns",
        sa.Column("hidden", sa.Boolean(), nullable=False, server_default="false"),
        schema="company",
    )


def downgrade() -> None:
    op.drop_column("active_turns", "hidden", schema="company")

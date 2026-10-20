"""add communication-channel fields to agent_demands

Messages executes everything, but the result stayed inside Messages: whoever
asked from the Workspace, from the Assistant panel or from Telegram had no
way of learning that their task finished (2026-08-13).

- `channel` is the medium the request arrived through -- named "meio de
  comunicação" rather than "origem" on purpose, since `origin_type` already
  means the Tipo and one word for two concepts is the mistake "backlog" made.
- `channel_ref` is the concrete address to answer at. Two columns rather
  than one because the kind alone can't answer: "telegram" by itself only
  reaches the configured home channel, never the chat that actually asked.
- `feedback_sent_at` makes delivery idempotent and, crucially, makes an
  undelivered outcome *findable*: a terminal message with a NULL stamp is
  exactly the signal that feedback is still owed, so a delivery lost to a
  restart or an outage is retried instead of vanishing.

All nullable, no backfill: messages filed before this have no channel to
answer, and inventing one would fabricate a destination nobody asked from.

Revision ID: f2a6d38e91b4
Revises: e8c14b7a2f60
Create Date: 2026-08-13

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'f2a6d38e91b4'
down_revision: Union[str, Sequence[str], None] = 'e8c14b7a2f60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "company"
TABLE = "agent_demands"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("channel", sa.String(length=20), nullable=True), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("channel_ref", sa.String(length=255), nullable=True), schema=SCHEMA)
    op.add_column(
        TABLE,
        sa.Column("feedback_sent_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_agent_demands_channel",
        TABLE,
        "channel IS NULL OR channel IN ('workspace', 'assistant', 'factory', 'agent', 'telegram')",
        schema=SCHEMA,
    )
    # Partial index for the feedback sweep, which only ever asks "what is
    # terminal and still owes a delivery" -- a small slice of the table.
    op.execute(
        f"CREATE INDEX IF NOT EXISTS ix_agent_demands_feedback_owed "
        f"ON {SCHEMA}.{TABLE} (dispatch_status) "
        f"WHERE feedback_sent_at IS NULL"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {SCHEMA}.ix_agent_demands_feedback_owed")
    op.drop_constraint("ck_agent_demands_channel", TABLE, schema=SCHEMA, type_="check")
    for col in ("feedback_sent_at", "channel_ref", "channel"):
        op.drop_column(TABLE, col, schema=SCHEMA)

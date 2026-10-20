"""add active_turns

Gives a running agent turn an owner outside the browser tab that started it
(2026-08-13, Marcelo: "não posso perder o contexto e o processamento por um
erro ou congelamento do frontend").

The run already survived the client -- it is a subprocess held in the
bridge's own `_active_streams`. What did not survive was any record of it:
the processing bubble, the live text and the tool steps were React state, so
a reload, a crash, or closing the tab left a blank screen while the agent
kept working. A frozen frontend gets no chance to save anything on its way
out, which is precisely why the client cannot hold this.

Modelled on the Terminal, which solves the same problem with tmux: a session
on the host, a stable id, and attach to come back. This table is the
`tmux has-session` the chat never had.

One table for both surfaces, with (scope, scope_id) rather than two nullable
FKs -- the same polymorphic convention governance.py uses. Their differences
are carried inside: `agent_id` is set for chat (one agent replies) and NULL
for channel (several run at once); every step carries its own agent so a
channel's parallel trails don't blend; `pending_approval` is chat-only,
where a turn can pause mid-stream for a yes/no.

Revision ID: b3f7e4a19c82
Revises: a7d51c93f8b2
Create Date: 2026-08-13

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'b3f7e4a19c82'
down_revision: Union[str, Sequence[str], None] = 'a7d51c93f8b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "company"


def upgrade() -> None:
    op.create_table(
        "active_turns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stream_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="running"),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("pending_approval", postgresql.JSONB(), nullable=True),
        sa.Column("steps", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("live_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("live_text_by_agent", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("reattach_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("scope IN ('chat', 'channel')", name="ck_active_turns_scope"),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed', 'cancelled')",
            name="ck_active_turns_status",
        ),
        schema=SCHEMA,
    )
    # Partial: the only question ever asked of this table at runtime is
    # "what is running for this owner?", and finished rows become the
    # overwhelming majority over time.
    op.execute(
        f"CREATE INDEX IF NOT EXISTS ix_active_turns_running "
        f"ON {SCHEMA}.active_turns (scope, scope_id) WHERE status = 'running'"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {SCHEMA}.ix_active_turns_running")
    op.drop_table("active_turns", schema=SCHEMA)

"""add dispatch contingency fields to agent_demands

Backs the failure-contingency rules agreed on 2026-08-13 (Marcelo:
"notificação de todas as falhas ao usuário, e prazo para retorno e adicionar
um icone de reprocessamento das falhas", plus "registra o número de
tentativas é válida no máximo 3").

- `dispatch_deadline_at` closes the worst failure mode there was: a run that
  hangs stays at "running" forever, never reaches a terminal state, and so
  never fires the feedback that only triggers on completed/failed. The
  host-bridge's own max_seconds cannot cover it -- a dead bridge enforces
  nothing.
- `dispatch_attempts` bounds manual reprocessing, so nobody keeps re-running
  something whose cause was never fixed.
- `dispatch_error` is what the notification and the reading pane show.

All three are nullable/defaulted, and existing rows need no backfill: a
message that already finished has no deadline to enforce, and zero attempts
recorded is the honest value for dispatches that predate the counter.

Revision ID: e8c14b7a2f60
Revises: d5f92b31c8a4
Create Date: 2026-08-13

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e8c14b7a2f60'
down_revision: Union[str, Sequence[str], None] = 'd5f92b31c8a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "company"
TABLE = "agent_demands"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column("dispatch_deadline_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        TABLE,
        sa.Column("dispatch_attempts", sa.Integer(), nullable=False, server_default="0"),
        schema=SCHEMA,
    )
    op.add_column(TABLE, sa.Column("dispatch_error", sa.Text(), nullable=True), schema=SCHEMA)
    # Partial index: the timeout sweep only ever looks at in-flight rows, and
    # those are a small minority of the table (everything else is terminal).
    op.execute(
        f"CREATE INDEX IF NOT EXISTS ix_agent_demands_dispatch_deadline "
        f"ON {SCHEMA}.{TABLE} (dispatch_deadline_at) "
        f"WHERE dispatch_deadline_at IS NOT NULL"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {SCHEMA}.ix_agent_demands_dispatch_deadline")
    for col in ("dispatch_error", "dispatch_attempts", "dispatch_deadline_at"):
        op.drop_column(TABLE, col, schema=SCHEMA)

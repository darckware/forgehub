"""add agent_demands.working_path

Completes a half-applied feature (2026-08-13). `working_path` had been
added to DemandSubmitIn/DemandUpdateIn and was already being read in
_execute_dispatch (`demand.working_path or settings.AGENT_RUNTIME_PATHS...`),
but the column itself was never added to the model or the database -- so
every dispatch raised AttributeError: 'AgentDemand' object has no attribute
'working_path'. The API accepted the field and the datastore had nowhere to
put it.

What it is for: the per-runtime default in AGENT_RUNTIME_PATHS is a *home*
directory, not a workspace. Dispatching to Porthos started Claude Code in
/root/.claude, where no project directory is reachable -- the exact failure
Athos filed as #8971 and re-filed as #9001. This column lets a message carry
the cwd its run should start in.

Nullable with no backfill: NULL is meaningful here (fall back to the
runtime default), not missing data.

Revision ID: d5f92b31c8a4
Revises: c4e81a90f3d7
Create Date: 2026-08-13

"""
from typing import Sequence, Union

import sqlalchemy as sa  # noqa: F401  (kept for downgrade/type parity)
from alembic import op

revision: str = 'd5f92b31c8a4'
down_revision: Union[str, Sequence[str], None] = 'c4e81a90f3d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "company"
TABLE = "agent_demands"


def upgrade() -> None:
    # IF NOT EXISTS, not a plain add_column: on the live database the column
    # had already been created by hand, outside Alembic (which is why the
    # schema and the migration history disagreed while the ORM model still
    # lacked the attribute). A plain ADD COLUMN raises DuplicateColumnError
    # there and leaves this revision permanently unapplicable, while a fresh
    # database needs the column created normally. Postgres-only syntax,
    # which this project already is (asyncpg, schema-qualified everywhere).
    op.execute(
        f"ALTER TABLE {SCHEMA}.{TABLE} ADD COLUMN IF NOT EXISTS working_path VARCHAR(1024)"
    )


def downgrade() -> None:
    op.drop_column(TABLE, "working_path", schema=SCHEMA)

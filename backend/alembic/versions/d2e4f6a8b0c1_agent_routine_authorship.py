"""agent_routines: who created and last changed each routine

2026-11-13 (Marcelo: the orchestrator "pode utilizar e programar Operação
24x7"): agents now write routines through /api/v1/operations/agent/routines,
effective immediately, so each routine records its author and its last
editor -- ``agent:<slug>`` for an agent, the username for a person (display)
-- and ``created_by_agent_id``, the creating agent by id: ownership for the
agent routes and the sender of the routine's occurrences. NULL on rows
created before this revision (author unknown) and on people's routines.

Revision ID: d2e4f6a8b0c1
Revises: c7d9e1f3a5b8
Create Date: 2026-11-13
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d2e4f6a8b0c1"
down_revision = "c7d9e1f3a5b8"
branch_labels = None
depends_on = None

SCHEMA = "company"


def upgrade() -> None:
    op.add_column("agent_routines", sa.Column("created_by", sa.String(150), nullable=True), schema=SCHEMA)
    op.add_column("agent_routines", sa.Column("updated_by", sa.String(150), nullable=True), schema=SCHEMA)
    op.add_column(
        "agent_routines",
        sa.Column("created_by_agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_foreign_key(
        "fk_agent_routines_created_by_agent_id", "agent_routines", "agents",
        ["created_by_agent_id"], ["id"], source_schema=SCHEMA, referent_schema=SCHEMA, ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_agent_routines_created_by_agent_id", "agent_routines", schema=SCHEMA,
                       type_="foreignkey")
    op.drop_column("agent_routines", "created_by_agent_id", schema=SCHEMA)
    op.drop_column("agent_routines", "updated_by", schema=SCHEMA)
    op.drop_column("agent_routines", "created_by", schema=SCHEMA)

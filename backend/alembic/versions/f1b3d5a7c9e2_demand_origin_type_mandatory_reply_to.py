"""demand origin_type mandatory, add dispatch_result/reply_to_id

Revision ID: f1b3d5a7c9e2
Revises: a7c3e9f1d2b4
Create Date: 2026-07-28 02:10:00.000000

Retires the third Tipo value, "demand" (2026-07-28, Marcelo: "no type so
sistem dois tipo task ou backlog e o campo e obrigatorio... nao temos
resposta automatica. somente processamento"). origin_type becomes NOT NULL,
restricted to ('task', 'backlog'). Two new columns replace what "demand" +
origin_id used to encode for an auto-generated reply:

- dispatch_result: the agent's raw output, written onto the SAME dispatched
  message once it finishes -- "processamento", not a new message.
- reply_to_id: set only on an auto-generated return message (created when
  the original had requires_response=true), pointing back at the message it
  answers. A real self-referential FK, unlike origin_id's deliberate
  polymorphism.

Backfill: any existing NULL or 'demand' origin_type becomes 'backlog' --
safe for both "never classified" and "was an auto-reply" rows, since
neither was ever dispatchable to begin with.

Chains onto a7c3e9f1d2b4 (the demand lineage). The repo has had two
independent Alembic heads since before this change -- this keeps the count
at two rather than adding a third.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'f1b3d5a7c9e2'
down_revision: Union[str, Sequence[str], None] = 'a7c3e9f1d2b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONSTRAINT = 'ck_agent_demands_origin_type'


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'agent_demands',
        sa.Column('dispatch_result', sa.Text(), nullable=True),
        schema='company',
    )
    op.add_column(
        'agent_demands',
        sa.Column('reply_to_id', postgresql.UUID(as_uuid=True), nullable=True),
        schema='company',
    )
    op.create_foreign_key(
        'fk_agent_demands_reply_to_id',
        'agent_demands',
        'agent_demands',
        ['reply_to_id'],
        ['id'],
        source_schema='company',
        referent_schema='company',
        ondelete='SET NULL',
    )
    op.execute(
        "UPDATE company.agent_demands SET origin_type = 'backlog' "
        "WHERE origin_type IS NULL OR origin_type = 'demand'"
    )
    op.drop_constraint(CONSTRAINT, 'agent_demands', schema='company', type_='check')
    op.alter_column(
        'agent_demands',
        'origin_type',
        schema='company',
        nullable=False,
        server_default='backlog',
        existing_type=sa.String(20),
    )
    op.create_check_constraint(
        CONSTRAINT,
        'agent_demands',
        "origin_type IN ('task', 'backlog')",
        schema='company',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(CONSTRAINT, 'agent_demands', schema='company', type_='check')
    op.alter_column(
        'agent_demands',
        'origin_type',
        schema='company',
        nullable=True,
        server_default=None,
        existing_type=sa.String(20),
    )
    op.create_check_constraint(
        CONSTRAINT,
        'agent_demands',
        "origin_type IS NULL OR origin_type IN ('task', 'demand', 'backlog')",
        schema='company',
    )
    op.drop_constraint('fk_agent_demands_reply_to_id', 'agent_demands', schema='company', type_='foreignkey')
    op.drop_column('agent_demands', 'reply_to_id', schema='company')
    op.drop_column('agent_demands', 'dispatch_result', schema='company')

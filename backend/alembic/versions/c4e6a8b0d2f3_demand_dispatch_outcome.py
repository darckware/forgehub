"""Messages: an authorization request or a wait for a reply is not a failure (ECO-054 5a/5b).

Marcelo, 2026-11-16: an agent that stops because it needs his authorization
sends the message to Aprovação; one that only waits for a person's answer is
"aguardando resposta". Neither counts as a failed dispatch.
"""
from alembic import op
import sqlalchemy as sa

revision = 'c4e6a8b0d2f3'
down_revision = 'b2d4f6a8c0e1'
branch_labels = None
depends_on = None

OUTCOMES = "('awaiting_authorization', 'authorized', 'authorization_refused', 'waiting_reply')"


def upgrade():
    op.add_column('agent_demands', sa.Column('dispatch_outcome', sa.String(30), nullable=True), schema='company')
    op.add_column('agent_demands', sa.Column('outcome_note', sa.Text(), nullable=True), schema='company')
    op.create_check_constraint('ck_agent_demands_dispatch_outcome', 'agent_demands',
                               f"dispatch_outcome IS NULL OR dispatch_outcome IN {OUTCOMES}", schema='company')


def downgrade():
    op.drop_constraint('ck_agent_demands_dispatch_outcome', 'agent_demands', schema='company', type_='check')
    op.drop_column('agent_demands', 'outcome_note', schema='company')
    op.drop_column('agent_demands', 'dispatch_outcome', schema='company')

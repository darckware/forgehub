"""Messages: the whatsapp_group channel.

Revision ID: c7e1a94d2f30
Revises: a3f1c7d92e04
"""
from alembic import op

revision = "c7e1a94d2f30"
down_revision = "a3f1c7d92e04"
branch_labels = None
depends_on = None

SCHEMA = "company"
TABLE = "agent_demands"
NAME = "ck_agent_demands_channel"
BEFORE = "('workspace', 'assistant', 'factory', 'agent', 'telegram')"
AFTER = "('workspace', 'assistant', 'factory', 'agent', 'telegram', 'whatsapp_group')"


def _check(values: str) -> None:
    op.drop_constraint(NAME, TABLE, schema=SCHEMA, type_="check")
    op.create_check_constraint(NAME, TABLE, f"channel IS NULL OR channel IN {values}", schema=SCHEMA)


def upgrade() -> None:
    _check(AFTER)


def downgrade() -> None:
    op.execute(f"UPDATE {SCHEMA}.{TABLE} SET channel = NULL, channel_ref = NULL WHERE channel = 'whatsapp_group'")
    _check(BEFORE)

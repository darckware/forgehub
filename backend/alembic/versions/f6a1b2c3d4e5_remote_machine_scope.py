"""Explicit machine/group scopes for remote delegation.

Revision ID: f6a1b2c3d4e5
Revises: e4c7a2d09b16
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = "f6a1b2c3d4e5"
down_revision = "e4c7a2d09b16"
branch_labels = None
depends_on = None


def upgrade():
    for name in ("servers", "host_groups"):
        op.add_column("authority_delegations", sa.Column(name, postgresql.JSONB(), nullable=False, server_default="[]"), schema="company")


def downgrade():
    for name in ("host_groups", "servers"):
        op.drop_column("authority_delegations", name, schema="company")

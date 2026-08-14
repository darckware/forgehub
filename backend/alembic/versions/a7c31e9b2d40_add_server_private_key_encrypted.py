"""Add servers.private_key_encrypted (encrypted durable copy of the identity file)

The inventory recorded where a server's SSH key lived, never the key itself.
When the Aegis profile directory was recreated on 2026-07-07, the identity
files for 172.15.2.4/172.15.2.5 stayed behind in a backup directory and the
Workspace terminal lost access to those servers -- the row still pointed at a
path that no longer had a file. This column is the durable copy that lets the
file be restored (see db/models/server.py for the full note).

Nullable: existing rows have no vaulted key until someone backs one up, and a
server whose key is managed entirely outside ForgeHub can stay that way.

Revision ID: a7c31e9b2d40
Revises: b3f7e4a19c82
Create Date: 2026-08-14
"""
from alembic import op
import sqlalchemy as sa

revision = "a7c31e9b2d40"
down_revision = "b3f7e4a19c82"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "servers",
        sa.Column("private_key_encrypted", sa.Text(), nullable=True),
        schema="company",
    )


def downgrade() -> None:
    op.drop_column("servers", "private_key_encrypted", schema="company")

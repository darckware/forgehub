"""Add servers.access_enabled (park a server without deleting its key)

2026-08-14, Marcelo: "tem um forma de adicionar um icone de ligar/desligar o
acesso, sem excluir a chave". Turning a server off was only expressible by
removing the key or the row, which throws away the way back in -- the same
mistake the key vault (a7c31e9b2d40) exists to undo.

A ForgeHub-side switch only: nothing is revoked on the server itself. Existing
rows default to enabled, since that is what they already were.

Revision ID: b8d3c05f1e77
Revises: e2f4a71b9c53
Create Date: 2026-08-14
"""
import sqlalchemy as sa
from alembic import op

revision = "b8d3c05f1e77"
down_revision = "e2f4a71b9c53"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "servers",
        sa.Column("access_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        schema="company",
    )


def downgrade() -> None:
    op.drop_column("servers", "access_enabled", schema="company")

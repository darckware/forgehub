"""Add product kind and sellable marker.

Revision ID: a91f3c2e7d40
Revises: f2d7a4c9e1b6
"""
from alembic import op
import sqlalchemy as sa

revision = "a91f3c2e7d40"
down_revision = "f2d7a4c9e1b6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("products", sa.Column("kind", sa.String(30), nullable=False, server_default="software"), schema="company")
    op.add_column("products", sa.Column("sellable", sa.Boolean(), nullable=False, server_default=sa.false()), schema="company")
    op.create_check_constraint("ck_products_kind", "products", "kind IN ('software', 'service', 'infrastructure', 'client_it')", schema="company")


def downgrade():
    op.drop_constraint("ck_products_kind", "products", schema="company", type_="check")
    op.drop_column("products", "sellable", schema="company")
    op.drop_column("products", "kind", schema="company")

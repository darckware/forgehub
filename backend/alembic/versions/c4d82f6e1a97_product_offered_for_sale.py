"""Record when a product was offered for sale in Darckware.

Revision ID: c4d82f6e1a97
Revises: b82e4d1a6c30
"""
from alembic import op
import sqlalchemy as sa

revision = "c4d82f6e1a97"
down_revision = "b82e4d1a6c30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("offered_for_sale_at", sa.DateTime(timezone=True), nullable=True), schema="company")


def downgrade() -> None:
    op.drop_column("products", "offered_for_sale_at", schema="company")

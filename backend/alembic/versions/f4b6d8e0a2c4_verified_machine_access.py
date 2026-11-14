"""Require proof of the active machine login before agent access."""
from alembic import op
import sqlalchemy as sa

revision = "f4b6d8e0a2c4"
down_revision = "e3f5a7b9c1d2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("servers", sa.Column("access_verified_at", sa.DateTime(timezone=True), nullable=True), schema="company")


def downgrade():
    op.drop_column("servers", "access_verified_at", schema="company")

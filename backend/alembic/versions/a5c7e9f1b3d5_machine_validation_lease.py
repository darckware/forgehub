"""Reserve candidate verification without holding a transaction during SSH."""
from alembic import op
import sqlalchemy as sa

revision = "a5c7e9f1b3d5"
down_revision = "f4b6d8e0a2c4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("servers", sa.Column("preparation_validation_until", sa.DateTime(timezone=True), nullable=True), schema="company")


def downgrade():
    op.drop_column("servers", "preparation_validation_until", schema="company")

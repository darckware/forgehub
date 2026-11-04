"""Add user contact and organization details.

Revision ID: f26b87d314c9
Revises: e18a0d9c4721
"""
from alembic import op
import sqlalchemy as sa

revision = "f26b87d314c9"
down_revision = "e18a0d9c4721"
branch_labels = None
depends_on = None


def upgrade():
    for name in ("phone", "job_title", "department"):
        op.add_column("users", sa.Column(name, sa.String(255), nullable=True), schema="company")


def downgrade():
    for name in ("phone", "job_title", "department"):
        op.drop_column("users", name, schema="company")

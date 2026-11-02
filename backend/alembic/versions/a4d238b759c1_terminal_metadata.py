"""Persist terminal names and notes.

Revision ID: a4d238b759c1
Revises: e8c4b2d9a7f1
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "a4d238b759c1"
down_revision = "e8c4b2d9a7f1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "terminal_metadata",
        sa.Column("session_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("label", sa.String(40), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="company",
    )


def downgrade():
    op.drop_table("terminal_metadata", schema="company")

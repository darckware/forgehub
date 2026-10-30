"""Pessoal: Marcelo's location, one row per day, for the summary's weather.

Revision ID: 4b7e2c9d1f05
Revises: 9c1f4e7a2b30
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "4b7e2c9d1f05"
down_revision = "9c1f4e7a2b30"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "personal_locations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("city", sa.String(120), nullable=False),
        sa.Column("state", sa.String(80), nullable=True),
        sa.Column("country", sa.String(80), nullable=False, server_default="Brasil"),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("source", sa.String(30), nullable=False, server_default="maia"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(50), nullable=False, server_default="maia"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("day", name="uq_personal_locations_day"),
        sa.CheckConstraint("source IN ('maia', 'manual')", name="ck_personal_location_source"),
        sa.CheckConstraint("latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180",
                           name="ck_personal_location_coordinates"),
        schema="company",
    )


def downgrade():
    op.drop_table("personal_locations", schema="company")

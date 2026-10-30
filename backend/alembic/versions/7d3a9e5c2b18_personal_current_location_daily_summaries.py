"""Pessoal: one current GPS location instead of one per day, plus the Maia's daily summaries.

``personal_locations`` (one row per day, 4b7e2c9d1f05) misread the request: what's needed is
Marcelo's current GPS location and a record of each morning summary. The table was dropped
while still empty in production.

Revision ID: 7d3a9e5c2b18
Revises: 4b7e2c9d1f05
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "7d3a9e5c2b18"
down_revision = "4b7e2c9d1f05"
branch_labels = None
depends_on = None


def _timestamps():
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def upgrade():
    op.drop_table("personal_locations", schema="company")
    op.create_table(
        "personal_location",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slot", sa.String(16), nullable=False, server_default="current"),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("accuracy_m", sa.Float(), nullable=True),
        sa.Column("city", sa.String(120), nullable=True),
        sa.Column("state", sa.String(80), nullable=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("shared_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("slot", name="uq_personal_location_slot"),
        sa.CheckConstraint("slot = 'current'", name="ck_personal_location_slot"),
        sa.CheckConstraint("source IN ('telegram', 'whatsapp', 'browser')", name="ck_personal_location_source"),
        sa.CheckConstraint("latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180",
                           name="ck_personal_location_coordinates"),
        schema="company",
    )
    op.create_table(
        "personal_daily_summaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("location_city", sa.String(120), nullable=True),
        sa.Column("location_state", sa.String(80), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("created_by", sa.String(50), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("day", name="uq_personal_daily_summaries_day"),
        schema="company",
    )


def downgrade():
    op.drop_table("personal_daily_summaries", schema="company")
    op.drop_table("personal_location", schema="company")
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
        *_timestamps(),
        sa.UniqueConstraint("day", name="uq_personal_locations_day"),
        sa.CheckConstraint("source IN ('maia', 'manual')", name="ck_personal_location_source"),
        sa.CheckConstraint("latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180",
                           name="ck_personal_location_coordinates"),
        schema="company",
    )

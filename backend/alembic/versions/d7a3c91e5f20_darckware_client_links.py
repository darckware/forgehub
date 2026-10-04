"""Darckware client links on products and projects (client demands Onda 3)

Products and projects record the Darckware client they are built for, and a
project the ticket/demand it was opened from. Darckware ids, no FK: that CRM
lives in another database. Plan:
docs/superpowers/plans/2026-10-04-client-demands-darckware.md (F3).

Revision ID: d7a3c91e5f20
Revises: c84e2f619ab0
Create Date: 2026-10-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d7a3c91e5f20"
down_revision = "c84e2f619ab0"
branch_labels = None
depends_on = None

SCHEMA = "company"


def upgrade() -> None:
    op.add_column("products", sa.Column("darckware_client_id", postgresql.UUID(as_uuid=True), nullable=True), schema=SCHEMA)
    op.add_column("products", sa.Column("darckware_client_name", sa.String(200), nullable=True), schema=SCHEMA)
    op.create_index("ix_company_products_darckware_client_id", "products", ["darckware_client_id"], schema=SCHEMA)

    op.add_column("projects", sa.Column("darckware_client_id", postgresql.UUID(as_uuid=True), nullable=True), schema=SCHEMA)
    op.add_column("projects", sa.Column("darckware_origin_type", sa.String(20), nullable=True), schema=SCHEMA)
    op.add_column("projects", sa.Column("darckware_origin_id", postgresql.UUID(as_uuid=True), nullable=True), schema=SCHEMA)
    op.create_index("ix_company_projects_darckware_client_id", "projects", ["darckware_client_id"], schema=SCHEMA)
    op.create_check_constraint(
        "ck_projects_darckware_origin_type",
        "projects",
        "darckware_origin_type IS NULL OR darckware_origin_type IN ('ticket', 'demand')",
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_constraint("ck_projects_darckware_origin_type", "projects", schema=SCHEMA, type_="check")
    op.drop_index("ix_company_projects_darckware_client_id", table_name="projects", schema=SCHEMA)
    op.drop_column("projects", "darckware_origin_id", schema=SCHEMA)
    op.drop_column("projects", "darckware_origin_type", schema=SCHEMA)
    op.drop_column("projects", "darckware_client_id", schema=SCHEMA)
    op.drop_index("ix_company_products_darckware_client_id", table_name="products", schema=SCHEMA)
    op.drop_column("products", "darckware_client_name", schema=SCHEMA)
    op.drop_column("products", "darckware_client_id", schema=SCHEMA)

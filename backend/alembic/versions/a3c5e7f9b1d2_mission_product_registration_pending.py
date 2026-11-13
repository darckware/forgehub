"""mission: product_registration_pending (new product/service from the mission form)

2026-11-12: a mission can be created with a product/service that does not
exist yet; ForgeHub registers a minimal shell and this flag tells the
orchestrator to complete the registration (blocks draft -> planning).

Revision ID: a3c5e7f9b1d2
Revises: 6e29cba08d41
Create Date: 2026-11-12
"""
import sqlalchemy as sa
from alembic import op

revision = "a3c5e7f9b1d2"
down_revision = '6e29cba08d41'
branch_labels = None
depends_on = None

SCHEMA = "company"


def upgrade() -> None:
    op.add_column(
        "project_missions",
        sa.Column("product_registration_pending", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("project_missions", "product_registration_pending", schema=SCHEMA)

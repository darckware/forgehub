"""add product_id to deploy_installations

Revision ID: e2a1b3c4d5e6
Revises: d1e9f3a8b042
Create Date: 2026-06-29 04:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'e2a1b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'd1e9f3a8b042'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'deploy_installations',
        sa.Column('product_id', postgresql.UUID(as_uuid=True), nullable=True),
        schema='company',
    )
    op.create_foreign_key(
        'fk_deploy_installations_product_id',
        'deploy_installations',
        'products',
        ['product_id'],
        ['id'],
        source_schema='company',
        referent_schema='company',
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint(
        'fk_deploy_installations_product_id',
        'deploy_installations',
        schema='company',
        type_='foreignkey',
    )
    op.drop_column('deploy_installations', 'product_id', schema='company')

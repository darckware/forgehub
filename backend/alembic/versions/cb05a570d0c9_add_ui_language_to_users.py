"""add ui_language to users

Revision ID: cb05a570d0c9
Revises: c04e3eb54255
Create Date: 2026-07-17 12:21:37.109790

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cb05a570d0c9'
down_revision: Union[str, Sequence[str], None] = 'c04e3eb54255'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Note: autogenerate also proposed dropping approval_requests' partial
    # unique index (uq_approval_requests_pending_target) -- a known false
    # positive with postgresql_where partial indexes, unrelated to this
    # migration's actual change (see c04e3eb54255). Left out deliberately.
    op.add_column('users', sa.Column('ui_language', sa.String(length=8), server_default='pt-BR', nullable=False), schema='company')
    op.create_check_constraint(
        'ck_users_ui_language', 'users', "ui_language IN ('en', 'pt-BR')", schema='company'
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_users_ui_language', 'users', schema='company', type_='check')
    op.drop_column('users', 'ui_language', schema='company')

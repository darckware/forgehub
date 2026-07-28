"""add es to ui_language

Revision ID: a1b2c3d4e5f6
Revises: 94cecfd3bb31
Create Date: 2026-07-23 00:00:00.000000

NOTE: same pre-existing two-heads situation noted in 8c829b7454d6 -- this
migration only extends that branch, it does not merge d718c040a4b3.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '94cecfd3bb31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint('ck_users_ui_language', 'users', schema='company', type_='check')
    op.create_check_constraint(
        'ck_users_ui_language', 'users', "ui_language IN ('en', 'pt-BR', 'es')", schema='company'
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_users_ui_language', 'users', schema='company', type_='check')
    op.create_check_constraint(
        'ck_users_ui_language', 'users', "ui_language IN ('en', 'pt-BR')", schema='company'
    )

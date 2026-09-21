"""add TOTP two-factor auth columns to users

Revision ID: e7f8a9b0c1d2
Revises: 6c9e8a2d4b70
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, Sequence[str], None] = "6c9e8a2d4b70"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
SCHEMA = "company"


def upgrade() -> None:
    op.add_column("users", sa.Column("totp_secret", sa.String(64), nullable=True), schema=SCHEMA)
    op.add_column("users", sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default="false"), schema=SCHEMA)
    op.add_column("users", sa.Column("totp_recovery_codes", sa.Text(), nullable=True), schema=SCHEMA)


def downgrade() -> None:
    op.drop_column("users", "totp_recovery_codes", schema=SCHEMA)
    op.drop_column("users", "totp_enabled", schema=SCHEMA)
    op.drop_column("users", "totp_secret", schema=SCHEMA)

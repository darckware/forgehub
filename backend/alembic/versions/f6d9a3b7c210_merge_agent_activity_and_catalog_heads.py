"""merge Agent Activity and tech catalog migration heads

Revision ID: f6d9a3b7c210
Revises: 1a2b3c4d5e6f, e5c8a12f4d90
Create Date: 2026-08-31
"""

from collections.abc import Sequence


revision: str = "f6d9a3b7c210"
down_revision: str | Sequence[str] | None = ("1a2b3c4d5e6f", "e5c8a12f4d90")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Join the two schema branches without additional DDL."""


def downgrade() -> None:
    """Restore the two independent migration heads."""

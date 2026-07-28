"""add products.application_url_dev

Revision ID: c4a9e2b7d1f6
Revises: b3d71a0c6e94
Create Date: 2026-07-26 18:00:00.000000

Splits a product's application URL per environment: the existing
`application_url` keeps its meaning as the **production** address and this
new column holds the **development** one.

The production column deliberately keeps its historical name instead of
being renamed to `application_url_prod`. It predates the split and is
already read by `WebAppPane.tsx` and `workspace_browser.py`
(`_resolve_product_url`), plus any external consumer of `ProductOut` --
renaming would break those for a purely cosmetic gain, and a rename is not
reversible without the same churn.

Nullable, no backfill: a product may legitimately have only one of the two
environments running (or neither, for a product still in concept).

Chains onto b3d71a0c6e94. The repo has had two independent Alembic heads
since before this change -- this keeps the count at two rather than adding
a third.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c4a9e2b7d1f6"
down_revision: Union[str, None] = "b3d71a0c6e94"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("application_url_dev", sa.String(length=2048), nullable=True),
        schema="company",
    )


def downgrade() -> None:
    op.drop_column("products", "application_url_dev", schema="company")

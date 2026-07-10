"""add deploy_groups table, seeded from existing installation group names

Revision ID: e8b1c72a4f60
Revises: d4a8e63f19b5
Create Date: 2026-07-03 00:00:00.000000

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8b1c72a4f60'
down_revision: Union[str, Sequence[str], None] = 'd4a8e63f19b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('deploy_groups',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('order_index', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name'),
    schema='company'
    )

    # Seed from group names already in use by installations so the combobox
    # starts populated (UUIDs generated Python-side, matching model defaults).
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT DISTINCT group_name FROM company.deploy_installations "
        "WHERE group_name IS NOT NULL AND group_name <> '' ORDER BY group_name"
    )).fetchall()
    for idx, (group_name,) in enumerate(rows):
        conn.execute(
            sa.text(
                "INSERT INTO company.deploy_groups (id, name, order_index) "
                "VALUES (:id, :name, :order_index)"
            ),
            {"id": str(uuid.uuid4()), "name": group_name, "order_index": idx},
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('deploy_groups', schema='company')

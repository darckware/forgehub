"""add public_key to servers

Revision ID: c91e2ab77f10
Revises: b4a30fa38d08
Create Date: 2026-07-02

Public half of the dedicated SSH key installed on the server by the
"install SSH key" flow (api/routes/server.py::install_server_key). The
private key stays on the host running the terminal/bridge.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c91e2ab77f10'
down_revision: Union[str, Sequence[str], None] = 'b4a30fa38d08'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('servers', sa.Column('public_key', sa.Text(), nullable=True), schema='company')


def downgrade() -> None:
    op.drop_column('servers', 'public_key', schema='company')

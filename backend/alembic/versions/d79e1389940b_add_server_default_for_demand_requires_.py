"""add server default for demand requires_response

Revision ID: d79e1389940b
Revises: c123b75b24d4
Create Date: 2026-07-24 20:41:45.078847

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd79e1389940b'
down_revision: Union[str, Sequence[str], None] = 'c123b75b24d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    A NOT NULL column with only a Python-side default breaks any writer
    whose ORM model doesn't declare it (e.g. an older deployed backend
    image inserting via a plain from_agent/subject/body statement) -- the
    column gets omitted from the INSERT and Postgres rejects the NULL.
    Happened for real against the still-on-old-code Docker deploy
    (port 8000) once send_demand.sh started sending requires_response.
    A server_default makes every writer, regardless of app version, safe.
    """
    op.alter_column('agent_demands', 'requires_response', server_default=sa.false(), schema='company')


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('agent_demands', 'requires_response', server_default=None, schema='company')

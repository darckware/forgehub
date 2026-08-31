"""link Messages to Software Factory development requests

Revision ID: e5c8a12f4d90
Revises: d4b7e91a2c63
Create Date: 2026-08-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e5c8a12f4d90"
down_revision: Union[str, Sequence[str], None] = "d4b7e91a2c63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_demands",
        sa.Column("development_request_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="company",
    )
    op.create_foreign_key(
        "fk_agent_demands_development_request_id",
        "agent_demands",
        "development_requests",
        ["development_request_id"],
        ["id"],
        source_schema="company",
        referent_schema="company",
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_agent_demands_development_request_id",
        "agent_demands",
        ["development_request_id"],
        schema="company",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agent_demands_development_request_id",
        table_name="agent_demands",
        schema="company",
    )
    op.drop_constraint(
        "fk_agent_demands_development_request_id",
        "agent_demands",
        schema="company",
        type_="foreignkey",
    )
    op.drop_column("agent_demands", "development_request_id", schema="company")

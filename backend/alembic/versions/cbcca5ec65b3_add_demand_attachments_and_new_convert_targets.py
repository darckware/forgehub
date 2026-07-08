"""add demand_attachments table and new demand convert targets

Revision ID: cbcca5ec65b3
Revises: 0090a2d0d35c
Create Date: 2026-07-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "cbcca5ec65b3"
down_revision: Union[str, Sequence[str], None] = "0090a2d0d35c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_TARGETS = "('task', 'doc', 'artifact', 'knowledge_base')"
NEW_TARGETS = "('task', 'doc', 'artifact', 'knowledge_base', 'planning_item', 'project_doc', 'quick_task')"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "demand_attachments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("demand_id", sa.UUID(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        # Path relative to /docs (the same mount docs.py writes under),
        # e.g. "anexos/demandas/<demand_id>/<filename>".
        sa.Column("path", sa.String(length=1024), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["demand_id"], ["company.agent_demands.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="company",
    )
    op.drop_constraint("ck_agent_demands_converted_entity_type", "agent_demands", schema="company", type_="check")
    op.create_check_constraint(
        "ck_agent_demands_converted_entity_type",
        "agent_demands",
        f"converted_entity_type IS NULL OR converted_entity_type IN {NEW_TARGETS}",
        schema="company",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_agent_demands_converted_entity_type", "agent_demands", schema="company", type_="check")
    op.create_check_constraint(
        "ck_agent_demands_converted_entity_type",
        "agent_demands",
        f"converted_entity_type IS NULL OR converted_entity_type IN {OLD_TARGETS}",
        schema="company",
    )
    op.drop_table("demand_attachments", schema="company")

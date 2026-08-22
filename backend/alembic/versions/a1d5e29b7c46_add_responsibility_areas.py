"""add responsibility_areas

Revision ID: a1d5e29b7c46
Revises: f3a7c1e9d284
Create Date: 2026-08-17

Layered task-execution governance, Fase 2 (plan: resilient-twirling-blossom).
Default agent owner per task_type, optionally scoped to a project. A partial
unique index enforces "at most one global default per task_type" since a
plain UniqueConstraint treats every NULL project_id as distinct.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a1d5e29b7c46"
down_revision: Union[str, Sequence[str], None] = "f3a7c1e9d284"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "responsibility_areas",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_type", sa.String(length=50), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("owner_agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["project_id"], ["company.projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_agent_id"], ["company.agents.id"]),
        sa.UniqueConstraint("task_type", "project_id", name="uq_responsibility_areas_task_type_project"),
        schema="company",
    )
    op.create_index(
        "uq_responsibility_areas_global_default",
        "responsibility_areas",
        ["task_type"],
        unique=True,
        schema="company",
        postgresql_where=sa.text("project_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_responsibility_areas_global_default", table_name="responsibility_areas", schema="company"
    )
    op.drop_table("responsibility_areas", schema="company")

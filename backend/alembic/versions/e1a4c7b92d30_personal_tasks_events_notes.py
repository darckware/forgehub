"""Personal domain: Marcelo's tasks, agenda events and notes (Maia's data)

Marcelo, 2026-10-07: "criar no ForgeHub lista de tarefas, anotações, agenda para a Maia ter
acesso". See app/db/models/personal.py.

Revision ID: e1a4c7b92d30
Revises: d7a3c91e5f20
Create Date: 2026-10-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e1a4c7b92d30"
down_revision = "d7a3c91e5f20"
branch_labels = None
depends_on = None

SCHEMA = "company"


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "personal_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("list_name", sa.String(80), nullable=False, server_default="Pessoal"),
        sa.Column("priority", sa.String(10), nullable=False, server_default="normal"),
        sa.Column("status", sa.String(10), nullable=False, server_default="pending"),
        sa.Column("due_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("due_has_time", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("recurrence", sa.String(10), nullable=False, server_default=""),
        sa.Column("reminders", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("reminders_sent", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(50), nullable=False, server_default="marcelo"),
        *_timestamps(),
        sa.CheckConstraint("status IN ('pending', 'done', 'cancelled')", name="ck_personal_tasks_status"),
        sa.CheckConstraint("priority IN ('low', 'normal', 'high')", name="ck_personal_tasks_priority"),
        sa.CheckConstraint("recurrence IN ('', 'daily', 'weekly', 'monthly', 'yearly')", name="ck_personal_tasks_recurrence"),
        schema=SCHEMA,
    )
    op.create_index("ix_company_personal_tasks_due_at", "personal_tasks", ["due_at"], schema=SCHEMA)

    op.create_table(
        "personal_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("all_day", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("location", sa.String(300), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="scheduled"),
        sa.Column("recurrence", sa.String(10), nullable=False, server_default=""),
        sa.Column("reminders", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("reminders_sent", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_by", sa.String(50), nullable=False, server_default="marcelo"),
        *_timestamps(),
        sa.CheckConstraint("status IN ('scheduled', 'cancelled')", name="ck_personal_events_status"),
        sa.CheckConstraint("recurrence IN ('', 'daily', 'weekly', 'monthly', 'yearly')", name="ck_personal_events_recurrence"),
        sa.CheckConstraint("ends_at IS NULL OR ends_at >= starts_at", name="ck_personal_events_window"),
        schema=SCHEMA,
    )
    op.create_index("ix_company_personal_events_starts_at", "personal_events", ["starts_at"], schema=SCHEMA)

    op.create_table(
        "personal_notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("tags", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_by", sa.String(50), nullable=False, server_default="marcelo"),
        *_timestamps(),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("personal_notes", schema=SCHEMA)
    op.drop_index("ix_company_personal_events_starts_at", table_name="personal_events", schema=SCHEMA)
    op.drop_table("personal_events", schema=SCHEMA)
    op.drop_index("ix_company_personal_tasks_due_at", table_name="personal_tasks", schema=SCHEMA)
    op.drop_table("personal_tasks", schema=SCHEMA)

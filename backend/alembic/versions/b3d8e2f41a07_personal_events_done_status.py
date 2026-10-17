"""personal events: "done" status (Realizado)

Revision ID: b3d8e2f41a07
Revises: 4a827c8cfc87
Create Date: 2026-10-16
"""
from alembic import op

revision = "b3d8e2f41a07"
down_revision = "4a827c8cfc87"
branch_labels = None
depends_on = None

SCHEMA = "company"


def upgrade() -> None:
    op.drop_constraint("ck_personal_events_status", "personal_events", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "ck_personal_events_status", "personal_events",
        "status IN ('scheduled', 'done', 'cancelled')", schema=SCHEMA,
    )


def downgrade() -> None:
    op.execute(f"UPDATE {SCHEMA}.personal_events SET status = 'scheduled' WHERE status = 'done'")
    op.drop_constraint("ck_personal_events_status", "personal_events", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "ck_personal_events_status", "personal_events",
        "status IN ('scheduled', 'cancelled')", schema=SCHEMA,
    )

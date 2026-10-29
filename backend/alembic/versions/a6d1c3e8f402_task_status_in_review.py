"""M0.6a: project_tasks.status accepts 'in_review'.

Plano Integrado Onda 1, M0.6a (docs/architecture/MCP_MISSION_TOOLS_SPEC.md
"Integration before `done` for mission tasks"): an approved review on a
mission task whose commit isn't in the mission mainline yet verifies the
execution and leaves the task `in_review` until it is integrated.

Downgrade refuses while any task is in_review: moving it to another status
silently is a decision for the operator, never the migration.

Revision ID: a6d1c3e8f402
Revises: e83c1a7d29b4
"""
import sqlalchemy as sa
from alembic import op

revision = "a6d1c3e8f402"
down_revision = "e83c1a7d29b4"
branch_labels = None
depends_on = None

SCHEMA = "company"
OLD_STATUSES = ("planned", "ready", "assigned", "in_progress", "blocked", "done", "deployed", "cancelled")
NEW_STATUSES = OLD_STATUSES + ("in_review",)


def _in(values):
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade():
    op.drop_constraint("ck_project_tasks_status", "project_tasks", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "ck_project_tasks_status", "project_tasks", f"status IN {_in(NEW_STATUSES)}", schema=SCHEMA
    )


def downgrade():
    count = op.get_bind().execute(
        sa.text(f"SELECT count(*) FROM {SCHEMA}.project_tasks WHERE status = 'in_review'")
    ).scalar_one()
    if count:
        raise RuntimeError(
            f"{count} task(s) are in_review; move them to another status before downgrading"
        )
    op.drop_constraint("ck_project_tasks_status", "project_tasks", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "ck_project_tasks_status", "project_tasks", f"status IN {_in(OLD_STATUSES)}", schema=SCHEMA
    )

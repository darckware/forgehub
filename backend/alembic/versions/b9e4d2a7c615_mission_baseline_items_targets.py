"""M0.6b: immutable baseline items and task execution targets.

Plano Integrado Onda 1, M0.6b (docs/architecture/MCP_MISSION_TOOLS_SPEC.md
§4.2-§4.3): `plan_baselines` gains `content_hash`/`superseded_at`, the new
`plan_baseline_items` freezes one content hash per task, and
`task_execution_targets` declares what a task's run holds exclusively.

Downgrade refuses while any mission is active or verifying: those are the
states the dispatch guard lets through, so dropping the baseline items would
leave their dispatch unguarded. The operator pauses them first.

Revision ID: b9e4d2a7c615
Revises: a6d1c3e8f402
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b9e4d2a7c615"
down_revision = "a6d1c3e8f402"
branch_labels = None
depends_on = None

SCHEMA = "company"


def _timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade():
    op.add_column("plan_baselines", sa.Column("content_hash", sa.String(64), nullable=True), schema=SCHEMA)
    op.add_column(
        "plan_baselines", sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True), schema=SCHEMA
    )
    op.create_table(
        "plan_baseline_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "baseline_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.plan_baselines.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "task_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.project_tasks.id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column("content_hash", sa.String(64), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("baseline_id", "task_id", name="uq_plan_baseline_items_task"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_plan_baseline_items_task_id", "plan_baseline_items", ["task_id"], schema=SCHEMA
    )
    op.create_table(
        "task_execution_targets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "task_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.project_tasks.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("target_key", sa.String(500), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("task_id", "kind", "target_key", name="uq_task_execution_targets_target"),
        sa.CheckConstraint(
            "kind IN ('worktree', 'branch', 'publish')", name="ck_task_execution_targets_kind"
        ),
        schema=SCHEMA,
    )


def downgrade():
    count = op.get_bind().execute(
        sa.text(f"SELECT count(*) FROM {SCHEMA}.project_missions WHERE state IN ('active', 'verifying')")
    ).scalar_one()
    if count:
        raise RuntimeError(
            f"{count} mission(s) are active or verifying; pause them before downgrading "
            "(their dispatch would be left unguarded)"
        )
    op.drop_table("task_execution_targets", schema=SCHEMA)
    op.drop_index("ix_plan_baseline_items_task_id", "plan_baseline_items", schema=SCHEMA)
    op.drop_table("plan_baseline_items", schema=SCHEMA)
    op.drop_column("plan_baselines", "superseded_at", schema=SCHEMA)
    op.drop_column("plan_baselines", "content_hash", schema=SCHEMA)

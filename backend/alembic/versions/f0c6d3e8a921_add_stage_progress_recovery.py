"""add stage progress recovery

Revision ID: f0c6d3e8a921
Revises: e9b5c2d4f710
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f0c6d3e8a921"
down_revision: Union[str, Sequence[str], None] = "e9b5c2d4f710"
branch_labels = None
depends_on = None
SCHEMA = "company"


def _timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.add_column(
        "pipeline_stages",
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        schema=SCHEMA,
    )
    op.create_table(
        "progress_checkpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pipeline_stage_id", postgresql.UUID(as_uuid=True)),
        sa.Column("task_id", postgresql.UUID(as_uuid=True)),
        sa.Column("task_execution_id", postgresql.UUID(as_uuid=True)),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("checkpoint_type", sa.String(30), nullable=False),
        sa.Column("step_key", sa.String(150), nullable=False),
        sa.Column("step_label", sa.String(255), nullable=False),
        sa.Column("state_snapshot", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("completed_requirement_keys", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("evidence_refs", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("last_confirmed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resume_from_step_key", sa.String(150)),
        sa.Column("blocker_code", sa.String(100)),
        sa.Column("error_code", sa.String(100)),
        sa.Column("message", sa.Text()),
        sa.Column("actor_type", sa.String(20), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True)),
        sa.Column("actor_name", sa.String(150), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["project_id"], [f"{SCHEMA}.projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pipeline_stage_id"], [f"{SCHEMA}.pipeline_stages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], [f"{SCHEMA}.project_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_execution_id"], [f"{SCHEMA}.task_executions.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "checkpoint_type IN ('started','progress','evidence','blocked','failed','paused','heartbeat_lost','reconciled','resumed','completed')",
            name="ck_progress_checkpoint_type",
        ),
        sa.CheckConstraint("actor_type IN ('user','agent','system')", name="ck_progress_checkpoint_actor_type"),
        sa.UniqueConstraint("task_execution_id", "sequence", name="uq_progress_checkpoint_execution_sequence"),
        sa.UniqueConstraint("idempotency_key", name="uq_progress_checkpoint_idempotency"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_progress_checkpoint_project_created", "progress_checkpoints",
        ["project_id", "created_at"], schema=SCHEMA,
    )
    op.create_index(
        "ix_progress_checkpoint_stage_created", "progress_checkpoints",
        ["pipeline_stage_id", "created_at"], schema=SCHEMA,
    )
    op.create_table(
        "stage_completion_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("pipeline_stage_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage_revision", sa.Integer(), nullable=False),
        sa.Column("baseline_id", postgresql.UUID(as_uuid=True)),
        sa.Column("policy_version_id", postgresql.UUID(as_uuid=True)),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("result", sa.String(20), nullable=False),
        sa.Column("requirement_results", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("missing_requirements", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("blocking_reasons", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("evidence_refs", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("evaluator_version", sa.String(50), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("evaluated_by_type", sa.String(20), nullable=False),
        sa.Column("evaluated_by_id", postgresql.UUID(as_uuid=True)),
        sa.Column("evaluated_by_name", sa.String(150), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["pipeline_stage_id"], [f"{SCHEMA}.pipeline_stages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["baseline_id"], [f"{SCHEMA}.plan_baselines.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["policy_version_id"], [f"{SCHEMA}.policy_versions.id"], ondelete="SET NULL"),
        sa.CheckConstraint("result IN ('ready','not_ready','stale')", name="ck_stage_completion_result"),
        sa.UniqueConstraint("pipeline_stage_id", "input_hash", name="uq_stage_completion_stage_input"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_stage_completion_stage_evaluated", "stage_completion_assessments",
        ["pipeline_stage_id", "evaluated_at"], schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("stage_completion_assessments", schema=SCHEMA)
    op.drop_table("progress_checkpoints", schema=SCHEMA)
    op.drop_column("pipeline_stages", "revision", schema=SCHEMA)


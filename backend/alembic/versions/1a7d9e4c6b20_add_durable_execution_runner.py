"""add durable execution runner

Revision ID: 1a7d9e4c6b20
Revises: f0c6d3e8a921
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "1a7d9e4c6b20"
down_revision: Union[str, Sequence[str], None] = "f0c6d3e8a921"
branch_labels = None
depends_on = None
SCHEMA = "company"


def ts():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.drop_constraint("ck_project_tasks_status", "project_tasks", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "ck_project_tasks_status", "project_tasks",
        "status IN ('planned','ready','assigned','in_progress','blocked','done','deployed','cancelled')",
        schema=SCHEMA,
    )
    op.create_table(
        "execution_waves",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("baseline_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pipeline_stage_id", postgresql.UUID(as_uuid=True)),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("authorized_by_type", sa.String(20)),
        sa.Column("authorized_by_id", postgresql.UUID(as_uuid=True)),
        sa.Column("delegation_id", postgresql.UUID(as_uuid=True)),
        sa.Column("wip_limit", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("budget_limit", sa.Numeric(12, 2)),
        sa.Column("preflight_snapshot", postgresql.JSONB()),
        sa.Column("preflight_hash", sa.String(64)),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("paused_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        *ts(),
        sa.ForeignKeyConstraint(["project_id"], [f"{SCHEMA}.projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["baseline_id"], [f"{SCHEMA}.plan_baselines.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["pipeline_stage_id"], [f"{SCHEMA}.pipeline_stages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["delegation_id"], [f"{SCHEMA}.authority_delegations.id"], ondelete="SET NULL"),
        sa.CheckConstraint("status IN ('draft','approved','active','paused','completed','cancelled')", name="ck_execution_wave_status"),
        sa.UniqueConstraint("project_id", "idempotency_key", name="uq_execution_wave_project_idempotency"),
        schema=SCHEMA,
    )
    op.create_index("ix_execution_wave_project_status", "execution_waves", ["project_id", "status"], schema=SCHEMA)
    op.create_table(
        "execution_wave_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("execution_wave_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("release_order", sa.Integer(), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True)), *ts(),
        sa.ForeignKeyConstraint(["execution_wave_id"], [f"{SCHEMA}.execution_waves.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], [f"{SCHEMA}.project_tasks.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("execution_wave_id", "task_id", name="uq_execution_wave_task"), schema=SCHEMA,
    )
    op.create_index("ix_execution_wave_task_task", "execution_wave_tasks", ["task_id"], schema=SCHEMA)
    op.create_table(
        "execution_work_packages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("runtime_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_wave_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("baseline_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("contract_version", sa.String(80), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("validation_errors", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("issued_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)), *ts(),
        sa.ForeignKeyConstraint(["task_id"], [f"{SCHEMA}.project_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assignment_id"], [f"{SCHEMA}.task_assignments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["runtime_profile_id"], [f"{SCHEMA}.agent_runtime_profiles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["execution_wave_id"], [f"{SCHEMA}.execution_waves.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["baseline_id"], [f"{SCHEMA}.plan_baselines.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("status IN ('draft','validated','issued','superseded','expired','cancelled')", name="ck_execution_work_package_status"),
        sa.UniqueConstraint("task_id", "revision", name="uq_execution_work_package_task_revision"),
        sa.UniqueConstraint("idempotency_key", name="uq_execution_work_package_idempotency"), schema=SCHEMA,
    )
    op.create_table(
        "execution_runners",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("runner_key", sa.String(120), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="offline"),
        sa.Column("adapter_version", sa.String(80)),
        sa.Column("capabilities", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.false()), *ts(),
        sa.CheckConstraint("status IN ('online','degraded','offline','disabled')", name="ck_execution_runner_status"), schema=SCHEMA,
    )
    op.create_table(
        "execution_leases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("work_package_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("runner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_execution_id", postgresql.UUID(as_uuid=True)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("leased_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("released_at", sa.DateTime(timezone=True)), *ts(),
        sa.ForeignKeyConstraint(["work_package_id"], [f"{SCHEMA}.execution_work_packages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["runner_id"], [f"{SCHEMA}.execution_runners.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_execution_id"], [f"{SCHEMA}.task_executions.id"], ondelete="SET NULL"),
        sa.CheckConstraint("status IN ('claimed','running','expired','released','cancelled')", name="ck_execution_lease_status"),
        sa.UniqueConstraint("work_package_id", name="uq_execution_lease_work_package"), schema=SCHEMA,
    )
    op.create_table(
        "execution_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("idempotency_key", sa.String(255), nullable=False), *ts(),
        sa.ForeignKeyConstraint(["task_execution_id"], [f"{SCHEMA}.task_executions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("task_execution_id", "sequence", name="uq_execution_event_sequence"),
        sa.UniqueConstraint("idempotency_key", name="uq_execution_event_idempotency"), schema=SCHEMA,
    )
    op.create_index("ix_execution_event_execution_created", "execution_events", ["task_execution_id", "created_at"], schema=SCHEMA)
    op.create_table(
        "execution_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contract_version", sa.String(80), nullable=False),
        sa.Column("result_payload", postgresql.JSONB(), nullable=False),
        sa.Column("result_hash", sa.String(64), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_stale", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("validation_errors", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")), *ts(),
        sa.ForeignKeyConstraint(["task_execution_id"], [f"{SCHEMA}.task_executions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("task_execution_id", name="uq_execution_result_execution"), schema=SCHEMA,
    )
    op.add_column("task_executions", sa.Column("work_package_id", postgresql.UUID(as_uuid=True)), schema=SCHEMA)
    op.add_column("task_executions", sa.Column("adapter_version", sa.String(80)), schema=SCHEMA)
    op.add_column("task_executions", sa.Column("process_ref", sa.String(255)), schema=SCHEMA)
    op.add_column("task_executions", sa.Column("exit_code", sa.Integer()), schema=SCHEMA)
    op.create_foreign_key("fk_task_execution_work_package", "task_executions", "execution_work_packages", ["work_package_id"], ["id"], source_schema=SCHEMA, referent_schema=SCHEMA, ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint("fk_task_execution_work_package", "task_executions", schema=SCHEMA, type_="foreignkey")
    for column in ("exit_code", "process_ref", "adapter_version", "work_package_id"):
        op.drop_column("task_executions", column, schema=SCHEMA)
    for table in ("execution_results", "execution_events", "execution_leases", "execution_runners", "execution_work_packages", "execution_wave_tasks", "execution_waves"):
        op.drop_table(table, schema=SCHEMA)
    op.drop_constraint("ck_project_tasks_status", "project_tasks", schema=SCHEMA, type_="check")
    op.create_check_constraint("ck_project_tasks_status", "project_tasks", "status IN ('planned','assigned','in_progress','blocked','done','deployed','cancelled')", schema=SCHEMA)

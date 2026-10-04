"""Record routine metrics and reversible operations changes.

Revision ID: b29f76c8e10a
Revises: d447cad24782
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "b29f76c8e10a"
down_revision = "d447cad24782"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_routine_runs", sa.Column("duration_ms", sa.Integer(), nullable=True), schema="company")
    op.add_column("agent_routine_runs", sa.Column("cost_usd", sa.Numeric(10, 6), nullable=True), schema="company")
    op.add_column("agent_routine_runs", sa.Column("evidence_received", sa.Boolean(), nullable=True), schema="company")
    op.add_column("agent_routine_runs", sa.Column("no_action", sa.Boolean(), nullable=True), schema="company")
    op.create_table(
        "operations_changes",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("routine_id", sa.UUID(), sa.ForeignKey("company.agent_routines.id", ondelete="SET NULL"), nullable=True),
        sa.Column("question_id", sa.UUID(), sa.ForeignKey("company.agent_questions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("target_type", sa.String(30), nullable=False),
        sa.Column("summary", sa.String(255), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("autonomy_level", sa.String(2), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("metric_name", sa.String(50), nullable=False),
        sa.Column("before_value", sa.Numeric(12, 4), nullable=True),
        sa.Column("after_value", sa.Numeric(12, 4), nullable=True),
        sa.Column("previous_state", JSONB(), nullable=False),
        sa.Column("new_state", JSONB(), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evaluation_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("learning", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("autonomy_level IN ('A0', 'A1', 'A2')", name="ck_operations_changes_level"),
        sa.CheckConstraint("status IN ('proposed', 'awaiting_approval', 'evaluating', 'kept', 'reverted')", name="ck_operations_changes_status"),
        schema="company",
    )
    op.create_index("ix_company_operations_changes_routine_id", "operations_changes", ["routine_id"], schema="company")


def downgrade() -> None:
    op.drop_index("ix_company_operations_changes_routine_id", table_name="operations_changes", schema="company")
    op.drop_table("operations_changes", schema="company")
    for column in ("no_action", "evidence_received", "cost_usd", "duration_ms"):
        op.drop_column("agent_routine_runs", column, schema="company")

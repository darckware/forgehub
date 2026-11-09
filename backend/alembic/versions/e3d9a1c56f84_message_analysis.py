"""Durable Messages analysis and operator presentation, without changing execution history."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e3d9a1c56f84"
down_revision = "e2c8d0b45e73"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("message_analysis_runs",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("scope_key", sa.String(64), nullable=False),
        sa.Column("scope", postgresql.JSONB(), nullable=False),
        sa.Column("requested_by", sa.String(150), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        *[sa.Column(n,sa.Integer(),nullable=False) for n in ("total","processed","applied","attempts")],
        sa.Column("summary",postgresql.JSONB(),nullable=False),sa.Column("error",sa.Text()),
        *[sa.Column(n,sa.DateTime(timezone=True)) for n in ("started_at","finished_at","lease_until")],
        sa.Column("lease_token",sa.UUID()),
        sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.CheckConstraint("status IN ('queued','running','completed','failed')", name="ck_message_analysis_status"), schema="company")
    op.create_index("uq_message_analysis_active_scope","message_analysis_runs",["scope_key"],unique=True,
                    schema="company",postgresql_where=sa.text("status IN ('queued','running')"))
    op.create_table("message_analysis_items",
        sa.Column("run_id",sa.UUID(),sa.ForeignKey("company.message_analysis_runs.id",ondelete="CASCADE"),primary_key=True),
        sa.Column("message_id",sa.UUID(),primary_key=True),sa.Column("status",sa.String(20),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),schema="company")
    op.create_table("message_triage_results",
        sa.Column("message_id",sa.UUID(),sa.ForeignKey("company.agent_demands.id",ondelete="CASCADE"),primary_key=True),
        sa.Column("analysis_run_id",sa.UUID(),sa.ForeignKey("company.message_analysis_runs.id",ondelete="SET NULL")),
        sa.Column("source_updated_at",sa.DateTime(timezone=True),nullable=False),
        *[sa.Column(n,sa.String(64),nullable=False) for n in ("source_fingerprint","context_fingerprint")],
        sa.Column("context_versions",postgresql.JSONB(),nullable=False),
        sa.Column("operator_state",sa.String(20),nullable=False),sa.Column("category",sa.String(40),nullable=False),
        *[sa.Column(n,sa.Text(),nullable=False) for n in ("summary","reason","recommendation")],
        sa.Column("proposed_action",sa.String(40),nullable=False),
        sa.Column("related_message_id",sa.UUID(),sa.ForeignKey("company.agent_demands.id",ondelete="SET NULL")),
        sa.Column("evidence_refs",postgresql.JSONB(),nullable=False),
        sa.Column("analyzed_at",sa.DateTime(timezone=True),nullable=False),sa.Column("applied_action",sa.String(40)),
        sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.CheckConstraint("operator_state IN ('decision','processing','waiting','resolved')",name="ck_message_triage_state"),schema="company")


def downgrade():
    op.drop_table("message_analysis_items",schema="company")
    op.drop_table("message_triage_results",schema="company")
    op.drop_index("uq_message_analysis_active_scope",table_name="message_analysis_runs",schema="company")
    op.drop_table("message_analysis_runs",schema="company")

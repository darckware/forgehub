"""Persist Moodle approval linkage and Telegram challenges."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "7a024b36d981"
down_revision = "8d71e3a2f609"
branch_labels = None
depends_on = None


def upgrade():
    stamp = lambda: [sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
                     sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())]
    op.create_table("moodle_message_approvals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("message_id", UUID(as_uuid=True), sa.ForeignKey("company.agent_demands.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("request_id", UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("source_agent_id", UUID(as_uuid=True), sa.ForeignKey("company.agents.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("params_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("approved_by", UUID(as_uuid=True), sa.ForeignKey("company.users.id", ondelete="RESTRICT")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("executor_id", UUID(as_uuid=True), sa.ForeignKey("company.agents.id", ondelete="RESTRICT")),
        sa.Column("message_hash", sa.String(64)),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("outcome", sa.String(20)), *stamp(), schema="company")
    op.create_table("moodle_approval_challenges",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", UUID(as_uuid=True), sa.ForeignKey("company.users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("secret_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("consumed_at", sa.DateTime(timezone=True)), *stamp(), schema="company")


def downgrade():
    raise RuntimeError("Moodle approval evidence must be retained")

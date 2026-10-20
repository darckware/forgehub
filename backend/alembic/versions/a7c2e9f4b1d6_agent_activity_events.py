"""Agent activity events pushed by the agent runtimes (Hermes outbound webhooks)

Revision ID: a7c2e9f4b1d6
Revises: f3a1c7d9e2b4
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a7c2e9f4b1d6"
down_revision: Union[str, Sequence[str], None] = "f3a1c7d9e2b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
SCHEMA = "company"


def upgrade() -> None:
    op.create_table(
        "agent_activity_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("profile", sa.String(100), nullable=False),
        sa.Column("runtime", sa.String(30), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_id", sa.String(128), nullable=True),
        sa.Column("turn_id", sa.String(128), nullable=True),
        sa.Column("tool_call_id", sa.String(128), nullable=True),
        sa.Column("platform", sa.String(40), nullable=True),
        sa.Column("counterpart_kind", sa.String(20), nullable=True),
        sa.Column("counterpart_ref", sa.String(64), nullable=True),
        sa.Column("model", sa.String(120), nullable=True),
        sa.Column("tool_name", sa.String(120), nullable=True),
        sa.Column("status", sa.String(30), nullable=True),
        sa.Column("error_type", sa.String(120), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("delivery_id", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('turn_started', 'turn_ended', 'tool_started', 'tool_ended', 'session_started')",
            name="ck_agent_activity_events_kind",
        ),
        sa.CheckConstraint(
            "counterpart_kind IS NULL OR counterpart_kind IN ('owner', 'human', 'agent', 'system')",
            name="ck_agent_activity_events_counterpart_kind",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_agent_activity_events_agent_occurred",
        "agent_activity_events",
        ["agent_id", "occurred_at"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_agent_activity_events_profile_occurred",
        "agent_activity_events",
        ["profile", "occurred_at"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ix_agent_activity_events_profile_occurred", table_name="agent_activity_events", schema=SCHEMA)
    op.drop_index("ix_agent_activity_events_agent_occurred", table_name="agent_activity_events", schema=SCHEMA)
    op.drop_table("agent_activity_events", schema=SCHEMA)

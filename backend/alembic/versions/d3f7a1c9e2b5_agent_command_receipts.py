"""M0.2a: idempotency receipts for agent commands.

Plano Integrado Onda 1, M0.2a (docs/architecture/MCP_MISSION_TOOLS_SPEC.md
§0.4): `agent_command_receipts` stores, per (principal, idempotency_key), the
request hash and the response of the first call, so a repeated MCP write
replays instead of acting twice. Receipts are not history (the AuditEvent is),
so downgrade simply drops the table.

Revision ID: d3f7a1c9e2b5
Revises: b9e4d2a7c615
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d3f7a1c9e2b5"
down_revision = "b9e4d2a7c615"
branch_labels = None
depends_on = None

SCHEMA = "company"


def upgrade():
    op.create_table(
        "agent_command_receipts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("principal_type", sa.String(20), nullable=False),
        sa.Column("principal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(150), nullable=False),
        sa.Column("command", sa.String(80), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("response_body", postgresql.JSONB(), nullable=False),
        sa.Column("target_type", sa.String(50), nullable=True),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "principal_type", "principal_id", "idempotency_key", name="uq_agent_command_receipts_principal_key"
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_agent_command_receipts_created_at", "agent_command_receipts", ["created_at"], schema=SCHEMA
    )


def downgrade():
    op.drop_index("ix_agent_command_receipts_created_at", table_name="agent_command_receipts", schema=SCHEMA)
    op.drop_table("agent_command_receipts", schema=SCHEMA)

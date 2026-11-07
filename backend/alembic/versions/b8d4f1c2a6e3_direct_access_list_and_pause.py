"""Direct access list on agents, and the switch that pauses every agent's remote access.

Revision ID: b8d4f1c2a6e3
Revises: a3c7e1d94b26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "b8d4f1c2a6e3"
down_revision = "a3c7e1d94b26"
branch_labels = None
depends_on = None

# Same value as core/remote_authority.py's CONTROL_ID.
CONTROL_ID = "6f1d2c4e-8a35-4b7e-9c10-3e5a7b9d1f24"


def upgrade():
    op.add_column("agents", sa.Column(
        "direct_access_allowed", sa.Boolean, nullable=False, server_default=sa.false()), schema="company")
    # Keeps today's state: these three could already receive a direct access.
    op.execute("UPDATE company.agents SET direct_access_allowed = true "
               "WHERE lower(name) IN ('porthus', 'aramis', 'dartan')")
    op.create_table(
        "agent_remote_access_control",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("paused", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_by", sa.String(150), nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="company",
    )
    op.execute(f"INSERT INTO company.agent_remote_access_control (id) VALUES ('{CONTROL_ID}')")


def downgrade():
    op.drop_table("agent_remote_access_control", schema="company")
    op.drop_column("agents", "direct_access_allowed", schema="company")

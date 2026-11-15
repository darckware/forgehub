"""agent_mcp_access: ForgeHub MCP servers and sensitive-action modes per agent (D4 screen).

Seeded with the decisions of 2026-11-15 (MCP split plan D2 adjusted to real usage, D4, Kairos =
marketing). Agents not listed get their function's defaults the first time the screen saves them.
"""
import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'a1c3e5f7b9d2'
down_revision = 'f2b4d6e8a0c1'
branch_labels = None
depends_on = None

SEED = {
    # slug: (servers, restart_mode, query_mode)
    "athos": (["forgehub_factory", "forgehub_missions", "forgehub_ops", "forgehub_registry"], "direct", "direct"),
    "hephaestus": (["forgehub_ops", "forgehub_registry", "forgehub_remote"], "direct", "direct"),
    "aegis": (["forgehub_factory", "forgehub_ops", "forgehub_registry", "forgehub_remote"], "approval", "direct"),
    "mnemosyne": (["forgehub_ops"], "approval", "direct"),
    "themis": (["forgehub_factory", "forgehub_ops", "forgehub_registry"], "approval", "approval"),
    "scriba": (["forgehub_factory", "forgehub_missions", "forgehub_ops"], "approval", "approval"),
    "daedalus": (["forgehub_factory", "forgehub_missions", "forgehub_ops"], "approval", "approval"),
    "atlas": (["forgehub_factory", "forgehub_missions"], "approval", "approval"),
    "kairos": (["forgehub_factory"], "approval", "approval"),
    "lara": (["forgehub_factory"], "approval", "approval"),
    "maia": (["forgehub_factory", "forgehub_personal"], "approval", "approval"),
    "porthus": (["forgehub_factory", "forgehub_missions", "forgehub_remote"], "approval", "approval"),
    "aramis": (["forgehub_factory", "forgehub_missions", "forgehub_remote"], "approval", "approval"),
    "dartan": (["forgehub_factory", "forgehub_missions", "forgehub_remote"], "approval", "approval"),
}


def upgrade():
    op.create_table(
        'agent_mcp_access',
        sa.Column('agent_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('company.agents.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('servers', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('restart_mode', sa.String(20), nullable=False, server_default='approval'),
        sa.Column('query_mode', sa.String(20), nullable=False, server_default='approval'),
        sa.Column('updated_by', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("restart_mode IN ('direct','approval')", name='ck_agent_mcp_access_restart_mode'),
        sa.CheckConstraint("query_mode IN ('direct','approval')", name='ck_agent_mcp_access_query_mode'),
        schema='company',
    )
    for slug, (servers, restart, query) in SEED.items():
        op.execute(sa.text(
            "INSERT INTO company.agent_mcp_access (agent_id, servers, restart_mode, query_mode, updated_by) "
            "SELECT id, CAST(:servers AS jsonb), :restart, :query, 'seed 2026-11-15' FROM company.agents "
            "WHERE profile_slug = :slug ON CONFLICT (agent_id) DO NOTHING"
        ).bindparams(servers=json.dumps(servers), restart=restart, query=query, slug=slug))


def downgrade():
    op.drop_table('agent_mcp_access', schema='company')

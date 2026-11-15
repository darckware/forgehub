"""Auditor ECO-072: production switches and agent MCP code come from versioned sources.

MCP split plan, Fase 0 (Marcelo, 2026-11-15): a deploy from another session started the
backend without the production switches, and agents ran the MCP from the main checkout.
"""
from alembic import op
import sqlalchemy as sa

revision = 'f2b4d6e8a0c1'
down_revision = '49707c727f82'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(sa.text('''INSERT INTO company.audit_checks
        (id,name,description,category,command,agent_profile,enabled,timeout_seconds,frequency)
        VALUES (gen_random_uuid(),'ECO-072',:description,'configuration',:command,'athos',true,55,'daily')
        ON CONFLICT (name) DO UPDATE SET enabled = true, updated_at = now()''').bindparams(
            description='Production switches match deploy/production-flags.env on main; every agent runs the published ForgeHub MCP (/root/.forgehub/mcp/current)',
            command='python3 /root/.hermes/profiles/athos/scripts/checklist_verifier.py --check ECO-072'))


def downgrade():
    op.execute("UPDATE company.audit_checks SET enabled=false WHERE name='ECO-072'")

"""Auditor ECO-073: Lara and Maia reach only the ForgeHub MCP tools of their marked servers.

Marcelo, 2026-11-15: audit access; limit only the agents that serve people outside.
"""
from alembic import op
import sqlalchemy as sa

revision = 'b2d4f6a8c0e1'
down_revision = 'a1c3e5f7b9d2'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(sa.text('''INSERT INTO company.audit_checks
        (id,name,description,category,command,agent_profile,enabled,timeout_seconds,frequency)
        VALUES (gen_random_uuid(),'ECO-073',:description,'security',:command,'aegis',true,55,'daily')
        ON CONFLICT (name) DO UPDATE SET enabled = true, updated_at = now()''').bindparams(
            description='Agents serving people outside (Lara, Maia) reach only the ForgeHub MCP tools of the servers marked for them on the Agentes e MCP do ForgeHub screen',
            command='python3 /root/.hermes/profiles/athos/scripts/checklist_verifier.py --check ECO-073'))


def downgrade():
    op.execute("UPDATE company.audit_checks SET enabled=false WHERE name='ECO-073'")

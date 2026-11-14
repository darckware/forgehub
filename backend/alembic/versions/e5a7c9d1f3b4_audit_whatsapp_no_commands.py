"""Auditor ECO-071: no WhatsApp entry accepts slash commands; one adapter per WhatsApp session.

Marcelo, 2026-11-14: "não pode aceitar nenhum comando pelo whatsapp".
"""
from alembic import op
import sqlalchemy as sa

revision = 'e5a7c9d1f3b4'
down_revision = 'd4f6b8c0e2a3'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(sa.text('''INSERT INTO company.audit_checks
        (id,name,description,category,command,agent_profile,enabled,timeout_seconds,frequency)
        VALUES (gen_random_uuid(),'ECO-071',:description,'security',:command,'aegis',true,55,'daily')
        ON CONFLICT (name) DO UPDATE SET enabled = true, updated_at = now()''').bindparams(
            description='No WhatsApp entry (root ingress or profile) accepts slash commands, in DM or group; one adapter per WhatsApp session',
            command='python3 /root/.hermes/profiles/athos/scripts/checklist_verifier.py --check ECO-071'))


def downgrade():
    op.execute("UPDATE company.audit_checks SET enabled=false WHERE name='ECO-071'")

"""Agent customer-service rules per channel (Lara: WhatsApp/site/e-mail; Maia: WhatsApp).

Seeds the Maia's WhatsApp row from personal_assistant_settings.instructions (the column stays, no
longer written). The profile files ATENDIMENTO_<CANAL>.md are written by the backend on save, not here.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'd4f6b8c0e2a3'
down_revision = 'c3e5a7b9d1f2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'agent_service_rules',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('agent_slug', sa.String(50), nullable=False),
        sa.Column('channel', sa.String(20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False, server_default=''),
        sa.Column('content_hash', sa.String(64), nullable=False),
        sa.Column('updated_by', sa.String(150), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('agent_slug', 'channel', name='uq_agent_service_rules_agent_channel'),
        sa.CheckConstraint("channel IN ('whatsapp','site','email')", name='ck_agent_service_rules_channel'),
        schema='company')
    # Plain SQL only, so `alembic upgrade --sql` (the release's offline preview) renders it too.
    op.execute(sa.text('''INSERT INTO company.audit_checks
        (id,name,description,category,command,agent_profile,enabled,timeout_seconds,frequency)
        VALUES (gen_random_uuid(),'ECO-070',:description,'knowledge',:command,'mnemosyne',true,55,'daily')
        ON CONFLICT (name) DO UPDATE SET enabled = true, updated_at = now()''').bindparams(
            description='One SOUL per agent in its home; service-rule files ATENDIMENTO_<CANAL>.md match ForgeHub; no legacy rule copies',
            command='python3 /root/.hermes/profiles/athos/scripts/checklist_verifier.py --check ECO-070'))
    # Same normalization as core/service_rules.normalize: CRLF -> LF, trimmed, one trailing newline.
    op.execute("""
        INSERT INTO company.agent_service_rules (id, agent_slug, channel, content, content_hash, updated_by)
        SELECT gen_random_uuid(), 'maia', 'whatsapp', t.content,
               encode(sha256(convert_to(t.content, 'UTF8')), 'hex'), 'migration:personal_assistant_settings'
        FROM (SELECT btrim(replace(instructions, E'\\r\\n', E'\\n'), E' \\t\\n\\r\\f\\v') || E'\\n' AS content
              FROM company.personal_assistant_settings ORDER BY created_at LIMIT 1) t
        WHERE t.content <> E'\\n'""")


def downgrade():
    op.execute("UPDATE company.audit_checks SET enabled=false WHERE name='ECO-070'")
    # Keep the Maia's latest rules where the previous code reads them; the other rows (Lara) only
    # survive in their profile files ATENDIMENTO_*.md and the audit history.
    op.execute("""UPDATE company.personal_assistant_settings SET instructions = r.content, updated_at = now()
                  FROM company.agent_service_rules r WHERE r.agent_slug = 'maia' AND r.channel = 'whatsapp'""")
    op.drop_table('agent_service_rules', schema='company')

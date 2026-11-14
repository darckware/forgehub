"""Auditor: Foundation integrity and agent-memory hygiene checks (ECO-067, ECO-068, ECO-069).

Marcelo, 2026-11-14: the Auditor must see outdated/obsolete rules in the Foundation and monitor the
agents' memories (retired rules, dead links, size) for Hermes and external agents.
Additive: inserts three check rows; downgrade disables them and keeps their runs.
"""
from alembic import op
import sqlalchemy as sa

revision = 'c3e5a7b9d1f2'
down_revision = 'b8e2c4a6d1f9'
branch_labels = None
depends_on = None

NEW_CHECKS = (
    ('ECO-067', 'foundation', 'athos', 'Foundation keeps its structure, its links resolve and it uses no retired path or term', 'weekly'),
    ('ECO-068', 'knowledge', 'mnemosyne', 'Hermes and external agents memories stay within their runtime size limits', 'daily'),
    ('ECO-069', 'knowledge', 'mnemosyne', 'Agent memories carry no retired rules, paths or dead links', 'weekly'),
)


def upgrade():
    bind = op.get_bind()
    for name, category, owner, description, frequency in NEW_CHECKS:
        bind.execute(sa.text('''INSERT INTO company.audit_checks
            (id,name,description,category,command,agent_profile,enabled,timeout_seconds,frequency)
            VALUES (gen_random_uuid(),:name,:description,:category,:command,:owner,true,55,:frequency)
            ON CONFLICT (name) DO NOTHING'''), dict(
                name=name, category=category, owner=owner, description=description, frequency=frequency,
                command=f'python3 /root/.hermes/profiles/athos/scripts/checklist_verifier.py --check {name}'))


def downgrade():
    op.execute("UPDATE company.audit_checks SET enabled=false WHERE name IN ('ECO-067','ECO-068','ECO-069')")

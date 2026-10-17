"""Register ECO-059 (shared skills locked) in the audit catalogue.

Revision ID: e5a17c3d9b42
Revises: b3d8e2f41a07

The row was created by hand on 2026-10-12, when Athos' verifier gained the
check; this makes a fresh database get it too. ON CONFLICT DO NOTHING keeps
whatever the live row already holds (an operator may have tuned it).
"""

from alembic import op
import sqlalchemy as sa

from app.core.audit_catalog import CANONICAL_AUDIT_CHECKS

revision = "e5a17c3d9b42"
down_revision = "b3d8e2f41a07"
branch_labels = None
depends_on = None

_VERIFIER = "/root/.hermes/profiles/athos/scripts/checklist_verifier.py"
_NAME = "ECO-059"


def upgrade() -> None:
    check = CANONICAL_AUDIT_CHECKS[_NAME]
    op.get_bind().execute(sa.text("""
        INSERT INTO company.audit_checks
            (id, name, description, category, command, workdir,
             agent_profile, enabled, timeout_seconds,
             remediation_description, remediation_command)
        VALUES (gen_random_uuid(), :name, :description, :category,
                :command, NULL, :agent_profile, :enabled,
                :timeout_seconds, NULL, NULL)
        ON CONFLICT (name) DO NOTHING
    """), {
        "name": _NAME,
        "description": check.description,
        "category": check.category,
        "command": f"python3 {_VERIFIER} --check {_NAME}",
        "agent_profile": check.agent_profile,
        "enabled": check.enabled,
        "timeout_seconds": check.timeout_seconds,
    })


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM company.audit_checks WHERE name = 'ECO-059'"))

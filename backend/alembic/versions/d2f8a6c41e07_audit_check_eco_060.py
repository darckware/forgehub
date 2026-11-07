"""Register ECO-060 (reads of SSH keys in ForgeVault) in the audit catalogue.

Revision ID: d2f8a6c41e07
Revises: a3c7e1d94b26

The live row was created by hand on 2026-11-06, with Athos' verifier, as ECO-059's
was; this makes a fresh database get it too. ON CONFLICT DO NOTHING keeps whatever
the live row already holds.
"""

from alembic import op
import sqlalchemy as sa

from app.core.audit_catalog import CANONICAL_AUDIT_CHECKS

revision = "d2f8a6c41e07"
down_revision = "b8d4f1c2a6e3"
branch_labels = None
depends_on = None

_VERIFIER = "/root/.hermes/profiles/athos/scripts/checklist_verifier.py"
_NAME = "ECO-060"
_REMEDIATION = (
    "Find out who used the listed identity and why, then rotate the keys it read. "
    "NOT VERIFIED means ForgeVault's audit could not be read: restore that first."
)


def upgrade() -> None:
    check = CANONICAL_AUDIT_CHECKS[_NAME]
    op.get_bind().execute(sa.text("""
        INSERT INTO company.audit_checks
            (id, name, description, category, command, workdir,
             agent_profile, enabled, timeout_seconds,
             remediation_description, remediation_command)
        VALUES (gen_random_uuid(), :name, :description, :category,
                :command, NULL, :agent_profile, :enabled,
                :timeout_seconds, :remediation, NULL)
        ON CONFLICT (name) DO NOTHING
    """), {
        "name": _NAME,
        "description": check.description,
        "category": check.category,
        "command": f"python3 {_VERIFIER} --check {_NAME}",
        "agent_profile": check.agent_profile,
        "enabled": check.enabled,
        "timeout_seconds": check.timeout_seconds,
        "remediation": _REMEDIATION,
    })


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM company.audit_checks WHERE name = 'ECO-060'"))

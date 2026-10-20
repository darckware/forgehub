"""Add ecosystem audit catalogue v2, reserving offsite backup control.

Revision ID: c84e2f619ab0
Revises: ae4d91c72b60

ECO-058 remains disabled until the first offsite snapshot and sample restore
are verified. Do not enable it merely because this migration was applied.
"""

from alembic import op
import sqlalchemy as sa

from app.core.audit_catalog import CANONICAL_AUDIT_CHECKS, RETIRED_AUDIT_CHECKS

revision = "c84e2f619ab0"
down_revision = "ae4d91c72b60"
branch_labels = None
depends_on = None

_VERIFIER = "/root/.hermes/profiles/athos/scripts/checklist_verifier.py"
_REVISED = {"ECO-007", "ECO-009", "ECO-010", "ECO-017", "ECO-019", "ECO-039"}
_NEW = {f"ECO-{number:03d}" for number in range(42, 59)}


def upgrade() -> None:
    bind = op.get_bind()
    for name in sorted(_REVISED | _NEW):
        check = CANONICAL_AUDIT_CHECKS[name]
        if name in _NEW:
            bind.execute(sa.text("""
                INSERT INTO company.audit_checks
                    (id, name, description, category, command, workdir,
                     agent_profile, enabled, timeout_seconds,
                     remediation_description, remediation_command)
                VALUES (gen_random_uuid(), :name, :description, :category,
                        :command, NULL, :agent_profile, :enabled,
                        :timeout_seconds, NULL, NULL)
                ON CONFLICT (name) DO UPDATE SET
                    description = EXCLUDED.description,
                    category = EXCLUDED.category,
                    command = EXCLUDED.command,
                    agent_profile = EXCLUDED.agent_profile,
                    enabled = EXCLUDED.enabled,
                    timeout_seconds = EXCLUDED.timeout_seconds,
                    remediation_description = NULL,
                    remediation_command = NULL,
                    updated_at = now()
            """), {
                "name": name,
                "description": check.description + (
                    f" [Disabled pending: {check.activation_condition}]"
                    if check.activation_condition else ""
                ),
                "category": check.category,
                "command": f"python3 {_VERIFIER} --check {name}",
                "agent_profile": check.agent_profile,
                "enabled": check.enabled,
                "timeout_seconds": check.timeout_seconds,
            })
        else:
            bind.execute(sa.text("""
                UPDATE company.audit_checks
                   SET description = :description, updated_at = now()
                 WHERE name = :name
            """), {"name": name, "description": check.description})
    for name, reason in RETIRED_AUDIT_CHECKS.items():
        bind.execute(sa.text("""
            UPDATE company.audit_checks
               SET enabled = false, description = :description, updated_at = now()
             WHERE name = :name
        """), {"name": name, "description": f"Retired: {reason}"})


def downgrade() -> None:
    bind = op.get_bind()
    # Runs are historical evidence. Keep any check that has them; the FK also
    # cascades, so an unconditional DELETE would destroy evidence.
    names = ", ".join(f"'{name}'" for name in sorted(_NEW))
    bind.execute(sa.text(f"""
        DELETE FROM company.audit_checks AS checks
         WHERE checks.name IN ({names})
           AND NOT EXISTS (
             SELECT 1 FROM company.audit_check_runs AS runs
              WHERE runs.check_id = checks.id
           )
    """))

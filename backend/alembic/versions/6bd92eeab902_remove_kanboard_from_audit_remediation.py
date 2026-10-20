"""remove kanboard from ECO-006/ECO-009 audit remediation

Revision ID: 6bd92eeab902
Revises: 0fdf831eade6
Create Date: 2026-08-17

ECO-006/ECO-009's `description` was already hand-corrected on the live DB
when Kanboard was removed (2026-07-28) -- no migration did it, which is why
it doesn't match the "Kanboard worker" wording still in
7a18c4e9d2f6_refresh_weekly_ecosystem_audit.py's CHECKS tuple (a historical
seed file, left as-is on purpose: editing an already-applied migration
doesn't change already-migrated databases). `remediation_description`/
`remediation_command` (added later by b31d7a9f4c20_add_audit_remediation.py)
were missed in that hand-fix and still tell an operator to restart/probe a
`kanboard-worker.service`/`kanboard` container that no longer exists.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "6bd92eeab902"
down_revision: Union[str, Sequence[str], None] = "0fdf831eade6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE company.audit_checks SET "
        "remediation_description='Restart the ForgeHub bridge service.', "
        "remediation_command='systemctl restart forgehub-chat-bridge.service', "
        "updated_at=now() "
        "WHERE name='ECO-006'"
    )
    op.execute(
        "UPDATE company.audit_checks SET "
        "remediation_description='Restart the ecosystem application services before probing every endpoint again.', "
        "remediation_command='docker restart forgerouter hindsight forgehub-backend forgehub-frontend >/dev/null && systemctl restart forgehub-chat-bridge.service', "
        "updated_at=now() "
        "WHERE name='ECO-009'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE company.audit_checks SET "
        "remediation_description='Restart the ForgeHub bridge and Kanboard worker services.', "
        "remediation_command='systemctl restart forgehub-chat-bridge.service kanboard-worker.service', "
        "updated_at=now() "
        "WHERE name='ECO-006'"
    )
    op.execute(
        "UPDATE company.audit_checks SET "
        "remediation_description='Restart the ecosystem application services before probing every endpoint again.', "
        "remediation_command='docker restart forgerouter hindsight forgehub-backend forgehub-frontend kanboard >/dev/null && systemctl restart forgehub-chat-bridge.service kanboard-worker.service', "
        "updated_at=now() "
        "WHERE name='ECO-009'"
    )

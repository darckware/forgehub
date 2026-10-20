"""make cleanup remediation self healing

Revision ID: d718c039c3a2
Revises: d718c039b2f1
Create Date: 2026-07-18
"""

from typing import Sequence, Union

from alembic import op

revision: str = "d718c039c3a2"
down_revision: Union[str, Sequence[str], None] = "d718c039b2f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE company.audit_checks SET "
        "remediation_description='Restore cleanup and log-retention configuration, reconcile containers if required, then run bounded cleanup.',"
        "remediation_command='bash /root/.hermes/profiles/athos/scripts/repair_ecosystem_cleanup.sh',"
        "timeout_seconds=600,updated_at=now() WHERE name='ECO-039'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE company.audit_checks SET "
        "remediation_description='Run the bounded weekly cleanup now; Docker volumes and database data remain protected.',"
        "remediation_command='bash /root/.hermes/profiles/athos/scripts/create_trash_cleanup_task.sh',"
        "timeout_seconds=600,updated_at=now() WHERE name='ECO-039'"
    )

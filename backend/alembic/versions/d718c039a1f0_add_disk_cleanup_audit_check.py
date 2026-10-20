"""add weekly WSL disk cleanup audit check

Revision ID: d718c039a1f0
Revises: b31d7a9f4c20
Create Date: 2026-07-18
"""

from typing import Sequence, Union

from alembic import op

revision: str = "d718c039a1f0"
down_revision: Union[str, Sequence[str], None] = "b31d7a9f4c20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO company.audit_checks("
        "id,name,description,category,command,workdir,agent_profile,enabled,timeout_seconds,"
        "remediation_description,remediation_command) "
        "VALUES (gen_random_uuid(),'ECO-039',"
        "'Weekly WSL disk cleanup covers bounded caches, temporary files, logs and backups',"
        "'cleanup','python3 /root/.hermes/profiles/athos/scripts/checklist_verifier.py --check ECO-039',"
        "NULL,'hephaestus',true,55,"
        "'Run the bounded weekly cleanup now; Docker volumes and database data remain protected.',"
        "'bash /root/.hermes/profiles/athos/scripts/create_trash_cleanup_task.sh') "
        "ON CONFLICT(name) DO UPDATE SET "
        "description=excluded.description,category=excluded.category,command=excluded.command,"
        "workdir=excluded.workdir,agent_profile=excluded.agent_profile,enabled=true,timeout_seconds=55,"
        "remediation_description=excluded.remediation_description,"
        "remediation_command=excluded.remediation_command,updated_at=now()"
    )


def downgrade() -> None:
    op.execute("DELETE FROM company.audit_checks WHERE name='ECO-039'")

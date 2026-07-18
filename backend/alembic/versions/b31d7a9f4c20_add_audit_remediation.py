"""add explicit remediation to ecosystem audit checks

Revision ID: b31d7a9f4c20
Revises: 7a18c4e9d2f6
Create Date: 2026-07-18
"""

from typing import Sequence, Union

from alembic import op

revision: str = "b31d7a9f4c20"
down_revision: Union[str, Sequence[str], None] = "7a18c4e9d2f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


REMEDIATIONS = {
    "ECO-005": ("Restart the eight Hermes gateways, then verify every unit.", "for p in athos aegis daedalus hephaestus atlas mnemosyne scriba themis; do systemctl restart hermes-gateway-$p.service || exit 1; done"),
    "ECO-006": ("Restart the ForgeHub bridge and Kanboard worker services.", "systemctl restart forgehub-chat-bridge.service kanboard-worker.service"),
    "ECO-007": ("Reconcile the declared ForgeHub and ForgeRouter Compose services.", "docker compose -f /root/project/forgehub/docker-compose.yml up -d && docker compose -f /root/project/forgerouter/docker-compose.yml up -d"),
    "ECO-008": ("Recreate declared services so Compose reconnects them to foundation_network.", "docker compose -f /root/project/forgehub/docker-compose.yml up -d --force-recreate && docker compose -f /root/project/forgerouter/docker-compose.yml up -d --force-recreate"),
    "ECO-009": ("Restart the ecosystem application services before probing every endpoint again.", "docker restart forgerouter hindsight forgehub-backend forgehub-frontend kanboard >/dev/null && systemctl restart forgehub-chat-bridge.service kanboard-worker.service"),
    "ECO-010": ("Restart both PostgreSQL containers and wait for readiness.", "docker restart company_postgres foundation_postgres >/dev/null; for c in company_postgres foundation_postgres; do for i in $(seq 1 30); do docker exec $c pg_isready -q && break; sleep 1; done; docker exec $c pg_isready -q || exit 1; done"),
    "ECO-012": ("Reapply the controlled Hindsight maintenance-function migration.", "docker exec -i foundation_postgres psql -v ON_ERROR_STOP=1 -U foundation -d foundation < /root/.hermes/profiles/athos/scripts/migrations/2026-07-18-hindsight-public-maintenance-functions.sql"),
    "ECO-013": ("Restart Hindsight and let its retain/recall pipeline reconnect.", "docker restart hindsight >/dev/null"),
    "ECO-014": ("Restart Hindsight after a maintenance-discovery failure.", "docker restart hindsight >/dev/null"),
    "ECO-015": ("Restart ForgeRouter without changing provider policy.", "docker restart forgerouter >/dev/null"),
    "ECO-016": ("Recreate the ForgeHub backend from Compose to restore the canonical Knowledge Base mount.", "docker compose -f /root/project/forgehub/docker-compose.yml up -d --force-recreate forgehub-backend"),
    "ECO-019": ("Restrict known secret-bearing files to their owner.", "chmod 600 /root/project/forgehub/.env /root/project/forgerouter/.env /root/.hermes/profiles/athos/config.yaml"),
    "ECO-020": ("Restart the Athos gateway, which owns the scheduler heartbeat.", "systemctl restart hermes-gateway-athos.service"),
    "ECO-024": ("Create a fresh weekly Hermes backup using the Athos-owned routine.", "bash /root/.hermes/profiles/athos/scripts/weekly_backup.sh"),
    "ECO-029": ("Restore the canonical host timezone; WSL continues to follow the Windows clock.", "timedatectl set-timezone America/Sao_Paulo"),
}


def upgrade() -> None:
    # Production received this additive DDL transactionally before the older
    # pending revisions were applied. IF NOT EXISTS keeps the eventual normal
    # upgrade path safe without stamping past unrelated migrations.
    op.execute(
        "ALTER TABLE company.audit_checks "
        "ADD COLUMN IF NOT EXISTS remediation_description text"
    )
    op.execute(
        "ALTER TABLE company.audit_checks "
        "ADD COLUMN IF NOT EXISTS remediation_command text"
    )
    for name, (description, command) in REMEDIATIONS.items():
        values = tuple(value.replace("'", "''") for value in (name, description, command))
        op.execute(
            "UPDATE company.audit_checks "
            f"SET remediation_description='{values[1]}', remediation_command='{values[2]}', updated_at=now() "
            f"WHERE name='{values[0]}'"
        )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE company.audit_checks "
        "DROP COLUMN IF EXISTS remediation_command"
    )
    op.execute(
        "ALTER TABLE company.audit_checks "
        "DROP COLUMN IF EXISTS remediation_description"
    )

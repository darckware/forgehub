"""fix stale audit remediations (gateway units, retired containers, missing files)

Revision ID: c5e7a9b1d3f2
Revises: b3d8f1a6c2e9
Create Date: 2026-10-02

`remediation_command` is the suggested correction handed to Athos when an
administrator approves a remediation (see `app/core/audit_remediation.py`),
so a stale value steers Athos into the stale action. The 2026-10-02 review
found seven: ECO-005/ECO-020 restarted per-profile `hermes-gateway-<profile>`
units that no longer exist with the multiplex gateway (and that the gateway
policy forbids); ECO-010/ECO-012 targeted `company_postgres`/
`foundation_postgres`, retired on 2026-09-04; ECO-012/ECO-040/ECO-041 and
ECO-024 called files that are not on disk (`weekly_backup.sh` was never the
backup script -- `backup_hermes_root.sh` is). Historical seed migrations are
left as-is on purpose, same as 6bd92eeab902.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c5e7a9b1d3f2"
down_revision: Union[str, Sequence[str], None] = "b3d8f1a6c2e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW = {'ECO-005': {'d': 'Restart the single multiplex Hermes gateway (the only restart the gateway '
                  'policy permits), then confirm it is active. Never start a second gateway or '
                  'restart per-profile units.',
             'c': 'XDG_RUNTIME_DIR=/run/user/0 systemctl --user restart hermes-gateway && sleep 10 '
                  '&& XDG_RUNTIME_DIR=/run/user/0 systemctl --user is-active hermes-gateway'},
 'ECO-010': {'d': 'Start any stopped ecosystem PostgreSQL instance (forgehub, hindsight, '
                  'forgerouter) and wait for readiness; running instances are left untouched.',
             'c': 'docker start forgehub_postgres hindsight_postgres forgerouter_postgres '
                  '>/dev/null; for c in forgehub_postgres hindsight_postgres forgerouter_postgres; '
                  'do for i in $(seq 1 30); do docker exec $c pg_isready -q && break; sleep 1; '
                  'done; docker exec $c pg_isready -q || exit 1; done'},
 'ECO-012': {'d': 'No automated correction: the Hindsight maintenance-function migration file is '
                  'not on disk. Escalate for manual review.',
             'c': None},
 'ECO-020': {'d': 'Restart the single multiplex Hermes gateway, which owns the cron ticker '
                  'heartbeat, then confirm it is active.',
             'c': 'XDG_RUNTIME_DIR=/run/user/0 systemctl --user restart hermes-gateway && sleep 10 '
                  '&& XDG_RUNTIME_DIR=/run/user/0 systemctl --user is-active hermes-gateway'},
 'ECO-024': {'d': 'Create a fresh Hermes backup with the same Athos-owned routine the '
                  'hermes-weekly-backup job runs.',
             'c': 'bash /root/.hermes/profiles/athos/scripts/backup_hermes_root.sh'},
 'ECO-040': {'d': 'No automated correction: the voice-runtime repair script does not exist yet. '
                  'Escalate for manual review.',
             'c': None},
 'ECO-041': {'d': 'No automated correction: the voice-runtime repair script does not exist yet. '
                  'Escalate for manual review.',
             'c': None}}

OLD = {'ECO-005': {'d': 'Restart the eight Hermes gateways, then verify every unit.',
             'c': 'for p in athos aegis daedalus hephaestus atlas mnemosyne scriba themis; do '
                  'systemctl restart hermes-gateway-$p.service || exit 1; done'},
 'ECO-010': {'d': 'Restart both PostgreSQL containers and wait for readiness.',
             'c': 'docker restart company_postgres foundation_postgres >/dev/null; for c in '
                  'company_postgres foundation_postgres; do for i in $(seq 1 30); do docker exec '
                  '$c pg_isready -q && break; sleep 1; done; docker exec $c pg_isready -q || exit '
                  '1; done'},
 'ECO-012': {'d': 'Reapply the controlled Hindsight maintenance-function migration.',
             'c': 'docker exec -i foundation_postgres psql -v ON_ERROR_STOP=1 -U foundation -d '
                  'foundation < '
                  '/root/.hermes/profiles/athos/scripts/migrations/2026-07-18-hindsight-public-maintenance-functions.sql'},
 'ECO-020': {'d': 'Restart the Athos gateway, which owns the scheduler heartbeat.',
             'c': 'systemctl restart hermes-gateway-athos.service'},
 'ECO-024': {'d': 'Create a fresh weekly Hermes backup using the Athos-owned routine.',
             'c': 'bash /root/.hermes/profiles/athos/scripts/weekly_backup.sh'},
 'ECO-040': {'d': 'Restore the canonical local STT, Piper pt-BR TTS and automatic voice-reply '
                  'settings; restart all Hermes gateways and verify both voice channels.',
             'c': 'bash /root/.hermes/profiles/athos/scripts/repair_voice_runtime.sh'},
 'ECO-041': {'d': 'Restore the canonical local STT, Piper pt-BR TTS and automatic voice-reply '
                  'settings; restart all Hermes gateways and verify both voice channels.',
             'c': 'bash /root/.hermes/profiles/athos/scripts/repair_voice_runtime.sh'}}

_UPDATE = sa.text(
    "UPDATE company.audit_checks SET remediation_description = :d, "
    "remediation_command = :c, updated_at = now() WHERE name = :name"
)


def _apply(values: dict[str, dict[str, str | None]]) -> None:
    bind = op.get_bind()
    for name, value in values.items():
        bind.execute(_UPDATE, {"name": name, "d": value["d"], "c": value["c"]})


def upgrade() -> None:
    _apply(NEW)


def downgrade() -> None:
    _apply(OLD)

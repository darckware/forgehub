"""Drop the Nexo client-monitoring domain (clients, workstations, irregularities, ...).

Revision ID: a9c4e7f2b1d6
Revises: e5a17c3d9b42

Nexo was dropped as a direction on 2026-10-04 (client access goes through
Tailscale + RustDesk, workstations are `servers` rows with kind="workstation")
and its last screen, /clients, was removed on 2026-10-17 at Marcelo's request.
Darckware clients live in Darckware (client_ops.py), not here.

No CASCADE on purpose: the drop order follows the foreign keys, so a table
that started depending on one of these since fails the migration instead of
losing a constraint silently. The data was dumped before this ran:
/root/backup/forgehub-nexo/nexo-tables-20261017-211216.sql (plus the
profile_permissions rows of the retired "clients" module beside it). There is
no downgrade -- restore from that dump if this ever has to come back.
"""

from alembic import op

revision = "a9c4e7f2b1d6"
down_revision = "e5a17c3d9b42"
branch_labels = None
depends_on = None

# Children before parents.
_TABLES = (
    "workstation_installation_events",
    "workstation_installations",
    "nexo_agent_builds",
    "client_reports",
    "client_read_credentials",
    "irregularities",
    "workstation_peer_grants",
    "workstations",
    "clients",
)


def upgrade() -> None:
    for table in _TABLES:
        op.execute(f"DROP TABLE IF EXISTS company.{table}")
    op.execute("DELETE FROM company.profile_permissions WHERE module = 'clients'")


def downgrade() -> None:
    raise NotImplementedError(
        "Nexo tables were dropped; restore /root/backup/forgehub-nexo/nexo-tables-20261017-211216.sql"
    )

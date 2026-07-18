"""refresh weekly ecosystem audit checks

Revision ID: 7a18c4e9d2f6
Revises: 5f9c3e1a7d64
Create Date: 2026-07-18
"""

from typing import Sequence, Union

from alembic import op

revision: str = "7a18c4e9d2f6"
down_revision: Union[str, Sequence[str], None] = "5f9c3e1a7d64"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# key, category, owner, user-facing context. The implementation stays in the
# Athos profile so the CLI cron and ForgeHub always execute the same control.
CHECKS = (
    ("ECO-001", "foundation", "athos", "Canonical Foundation documents exist and are readable"),
    ("ECO-002", "foundation", "athos", "Foundation contains documentation only; operational scripts stay profile-owned"),
    ("ECO-003", "knowledge", "mnemosyne", "Shared Knowledge Base layout exists for core and external agents"),
    ("ECO-004", "agents", "athos", "Core Hermes profiles and external runtime integrations pass the contract validator"),
    ("ECO-005", "agents", "athos", "Eight principal Hermes gateways are active and healthy"),
    ("ECO-006", "services", "hephaestus", "ForgeHub bridge and Kanboard worker systemd services are active"),
    ("ECO-007", "containers", "hephaestus", "Ecosystem Docker containers are running and healthy"),
    ("ECO-008", "network", "hephaestus", "Every ecosystem container participates in foundation_network"),
    ("ECO-009", "services", "hephaestus", "ForgeRouter, Hindsight, ForgeHub and Kanboard endpoints are healthy"),
    ("ECO-010", "database", "daedalus", "Company and Foundation PostgreSQL instances accept connections"),
    ("ECO-011", "database", "daedalus", "Foundation PostgreSQL schema topology has no application tables in public"),
    ("ECO-012", "memory", "mnemosyne", "Hindsight shared maintenance functions exist and execute"),
    ("ECO-013", "memory", "mnemosyne", "Hindsight retain/recall pipeline is connected and populated"),
    ("ECO-014", "memory", "mnemosyne", "Hindsight recent logs contain no maintenance discovery failure"),
    ("ECO-015", "provider", "atlas", "ForgeRouter is healthy and remains the exclusive agent-facing LLM provider"),
    ("ECO-016", "knowledge", "scriba", "ForgeHub mounts the complete shared Knowledge Base at /vault"),
    ("ECO-017", "configuration", "daedalus", "ForgeHub and ForgeRouter Docker Compose configurations are valid"),
    ("ECO-018", "capacity", "hephaestus", "Root filesystem disk and inode usage remain below 85 percent"),
    ("ECO-019", "security", "aegis", "Secret-bearing configuration files are owner-only"),
    ("ECO-020", "cron", "athos", "Hermes cron scheduler heartbeat is current"),
    ("ECO-021", "cron", "athos", "Every enabled Hermes cron is restricted to 09:00 through 23:59"),
    ("ECO-022", "cron", "athos", "Enabled Hermes crons have no failed latest execution"),
    ("ECO-023", "cron", "athos", "Complete ecosystem audit is scheduled weekly on Sunday at 19:00"),
    ("ECO-024", "backup", "hephaestus", "Weekly Hermes backup archive is recent and nontrivial"),
    ("ECO-025", "audit", "themis", "Foundation and ForgeHub audit persistence contains the required active checks"),
    ("ECO-026", "knowledge", "scriba", "Active Knowledge Base contains no retired provider-rotation or vault references"),
    ("ECO-027", "memory", "mnemosyne", "Hindsight has no valid obsolete provider, vault or workspace facts"),
    ("ECO-028", "scripts", "daedalus", "Athos operational shell and Python scripts pass syntax validation"),
    ("ECO-029", "infrastructure", "hephaestus", "Host clock is plausible and timezone is America/Sao_Paulo"),
    ("ECO-030", "skills", "athos", "Hermes skills have valid contracts and no obsolete ecosystem instructions"),
    ("ECO-031", "profiles", "athos", "Athos profile files, configuration, memory links and owned scripts are valid"),
    ("ECO-032", "profiles", "aegis", "Aegis profile files, configuration, memory links and owned scripts are valid"),
    ("ECO-033", "profiles", "daedalus", "Daedalus profile files, configuration, memory links and owned scripts are valid"),
    ("ECO-034", "profiles", "hephaestus", "Hephaestus profile files, configuration, memory links and owned scripts are valid"),
    ("ECO-035", "profiles", "atlas", "Atlas profile files, configuration, memory links and owned scripts are valid"),
    ("ECO-036", "profiles", "mnemosyne", "Mnemosyne profile files, configuration, memory links and owned scripts are valid"),
    ("ECO-037", "profiles", "scriba", "Scriba profile files, configuration, memory links and owned scripts are valid"),
    ("ECO-038", "profiles", "themis", "Themis profile files, configuration, memory links and owned scripts are valid"),
)


def _quote(value: str) -> str:
    return value.replace("'", "''")


def upgrade() -> None:
    names = ", ".join(f"'{key}'" for key, *_ in CHECKS)
    op.execute(f"UPDATE company.audit_checks SET enabled=false, updated_at=now() WHERE name NOT IN ({names})")
    for key, category, owner, description in CHECKS:
        command = f"python3 /root/.hermes/profiles/athos/scripts/checklist_verifier.py --check {key}"
        values = tuple(_quote(v) for v in (key, category, owner, description, command))
        op.execute(
            "INSERT INTO company.audit_checks(id,name,description,category,command,workdir,agent_profile,enabled,timeout_seconds) "
            f"VALUES (gen_random_uuid(),'{values[0]}','{values[3]}','{values[1]}','{values[4]}',NULL,'{values[2]}',true,55) "
            "ON CONFLICT(name) DO UPDATE SET description=excluded.description,category=excluded.category,command=excluded.command,"
            "workdir=excluded.workdir,agent_profile=excluded.agent_profile,enabled=true,timeout_seconds=55,updated_at=now()"
        )


def downgrade() -> None:
    op.execute("UPDATE company.audit_checks SET enabled=true, updated_at=now()")

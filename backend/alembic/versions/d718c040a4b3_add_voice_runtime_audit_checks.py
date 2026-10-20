"""add Hermes voice runtime audit checks

Revision ID: d718c040a4b3
Revises: d718c039c3a2
Create Date: 2026-07-18
"""

from typing import Sequence, Union

from alembic import op

revision: str = "d718c040a4b3"
down_revision: Union[str, Sequence[str], None] = "d718c039c3a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    rows = (
        (
            "ECO-040",
            "Telegram voice input is transcribed locally and receives an automatic pt-BR voice reply",
            "telegram",
            "python3 /root/.hermes/profiles/athos/scripts/checklist_verifier.py --check ECO-040",
            180,
        ),
        (
            "ECO-041",
            "Hermes CLI voice command, recording dependencies, local STT and pt-BR TTS are ready",
            "cli",
            "python3 /root/.hermes/profiles/athos/scripts/checklist_verifier.py --check ECO-041",
            60,
        ),
    )
    for name, description, category, command, timeout in rows:
        op.execute(
            "INSERT INTO company.audit_checks("
            "id,name,description,category,command,workdir,agent_profile,enabled,timeout_seconds,"
            "remediation_description,remediation_command) VALUES ("
            f"gen_random_uuid(),'{name}','{description}','{category}','{command}',NULL,'athos',true,{timeout},"
            "'Restore the canonical local STT, Piper pt-BR TTS and automatic voice-reply settings; "
            "restart all Hermes gateways and verify both voice channels.',"
            "'bash /root/.hermes/profiles/athos/scripts/repair_voice_runtime.sh') "
            "ON CONFLICT(name) DO UPDATE SET description=excluded.description,category=excluded.category,"
            "command=excluded.command,agent_profile=excluded.agent_profile,enabled=true,"
            "timeout_seconds=excluded.timeout_seconds,remediation_description=excluded.remediation_description,"
            "remediation_command=excluded.remediation_command,updated_at=now()"
        )


def downgrade() -> None:
    op.execute("DELETE FROM company.audit_checks WHERE name IN ('ECO-040','ECO-041')")

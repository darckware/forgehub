"""rewrite agent_tools.file_path from container mounts to host paths

Revision ID: f2c9d81b3a74
Revises: e8b1c72a4f60
Create Date: 2026-07-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f2c9d81b3a74'
down_revision: Union[str, Sequence[str], None] = 'e8b1c72a4f60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (container mount prefix, host prefix) — matches _HOST_TO_CONTAINER in
# app/api/routes/tool.py.
_PREFIXES = (
    ("/hermes-scripts/", "/root/.hermes/scripts/"),
    ("/hermes-cron/", "/root/.hermes/crons/"),
    ("/profiles/", "/root/.hermes/profiles/"),
)


def upgrade() -> None:
    """Upgrade schema."""
    for container_prefix, host_prefix in _PREFIXES:
        op.execute(
            "UPDATE company.agent_tools "
            f"SET file_path = '{host_prefix}' || substring(file_path from {len(container_prefix) + 1}) "
            f"WHERE file_path LIKE '{container_prefix}%'"
        )


def downgrade() -> None:
    """Downgrade schema."""
    for container_prefix, host_prefix in _PREFIXES:
        op.execute(
            "UPDATE company.agent_tools "
            f"SET file_path = '{container_prefix}' || substring(file_path from {len(host_prefix) + 1}) "
            f"WHERE file_path LIKE '{host_prefix}%'"
        )

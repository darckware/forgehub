"""Reconcile cron script rows left at the retired central location.

Revision ID: ae4d91c72b60
Revises: d9185ca2e4f7
"""

from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "ae4d91c72b60"
down_revision: Union[str, Sequence[str], None] = "d9185ca2e4f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _profiles_dir() -> Path:
    for path in (Path("/profiles"), Path("/root/.hermes/profiles")):
        if path.is_dir():
            return path
    raise RuntimeError("Profiles directory is unavailable; refusing to remove legacy cron script rows")


def upgrade() -> None:
    bind = op.get_bind()
    legacy_rows = bind.execute(sa.text(
        "SELECT id, name FROM company.cron_scripts WHERE location = 'main'"
    )).all()
    if not legacy_rows:
        return

    # This table currently has no inbound FK. Fail closed if another table
    # acquires one before this revision is deployed.
    dependencies = bind.execute(sa.text(
        "SELECT conname FROM pg_constraint "
        "WHERE contype = 'f' AND confrelid = 'company.cron_scripts'::regclass"
    )).scalars().all()
    if dependencies:
        raise RuntimeError(f"Cannot reconcile cron script rows with inbound FKs: {dependencies}")

    profiles = _profiles_dir()
    for row_id, name in legacy_rows:
        owner = next((
            profile.name for profile in sorted(profiles.iterdir())
            if profile.is_dir() and (profile / "scripts" / name).is_file()
        ), None)
        if owner is None:
            bind.execute(sa.text("DELETE FROM company.cron_scripts WHERE id = :id"), {"id": row_id})
            continue
        bind.execute(sa.text(
            "UPDATE company.cron_scripts SET location = :location, agent = :agent, "
            "path = :path, exists_on_disk = true, updated_at = now() WHERE id = :id"
        ), {
            "id": row_id,
            "location": owner,
            "agent": owner,
            "path": f"/profiles/{owner}/scripts/{name}",
        })


def downgrade() -> None:
    # Removed rows cannot be reconstructed; restored locations would point to
    # retired directories. This data repair intentionally has no reverse.
    pass

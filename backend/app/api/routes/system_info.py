"""Read-only identity of the ForgeHub build currently serving requests."""

import os
from pathlib import Path

from alembic.script import ScriptDirectory
from fastapi import APIRouter
from sqlalchemy import text

from app.db.base import AsyncSessionLocal


router = APIRouter(prefix="/api/v1/system", tags=["system"])

FORGEHUB_GITHUB_REPO = "https://github.com/marcelodarckferreira/forgehub"
_BACKEND_ROOT = Path(__file__).resolve().parents[3]


async def _get_postgres_version() -> str:
    async with AsyncSessionLocal() as session:
        return str((await session.execute(text("SELECT version()"))).scalar_one())


def _latest_bundled_migration() -> str | None:
    try:
        scripts = ScriptDirectory(str(_BACKEND_ROOT / "alembic"))
        head_files = sorted(
            Path(scripts.get_revision(revision).path).name
            for revision in scripts.get_heads()
        )
    except Exception:
        return None
    return ", ".join(head_files) if head_files else None


@router.get("/version")
async def system_version() -> dict[str, str | None]:
    git_sha = os.environ.get("FORGEHUB_GIT_SHA", "unknown")
    try:
        postgres_version = await _get_postgres_version()
    except Exception:
        postgres_version = None
    return {
        "app_version": os.environ.get("FORGEHUB_VERSION", "unknown"),
        "git_sha": git_sha,
        "git_commit_url": (
            f"{FORGEHUB_GITHUB_REPO}/commit/{git_sha}"
            if git_sha != "unknown"
            else None
        ),
        "build_date": os.environ.get("FORGEHUB_BUILD_DATE", "unknown"),
        "postgres_version": postgres_version,
        "latest_migration_bundled": _latest_bundled_migration(),
        "github_repo_url": FORGEHUB_GITHUB_REPO,
    }

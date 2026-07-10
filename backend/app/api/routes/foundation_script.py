"""Foundation Scripts registry — CRUD + doc-driven sync.

Backs the Foundation page's "Scripts" card: a curated list of scripts that
implement something documented under /root/.hermes/foundation (mounted
read-only here at /foundation-root, same mount foundation_docs.py browses
read-write). Rows can be added/removed by hand (source="manual") or
discovered by POST .../sync, which scans every Foundation markdown doc for
script filename mentions (e.g. a governance doc describing a Telegram
voice-message transcriber names the .py that implements it) and upserts new
rows (source="sync", doc_path set to the doc that mentioned it, path set if
a script by that name exists under any profile's scripts/ dir).

Deliberately a separate table from cron_script.py's full per-profile Crons
catalog -- that one tracks every scheduler-executed script ecosystem-wide;
this one tracks only the subset the Foundation docs themselves call out.
"""
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.foundation_script import (
    FoundationScriptContentOut,
    FoundationScriptCreate,
    FoundationScriptOut,
    FoundationScriptSyncOut,
    FoundationScriptUpdate,
)
from app.db.base import get_db
from app.db.models.foundation_script import FoundationScript

router = APIRouter(prefix="/api/v1/foundation-scripts", tags=["foundation-scripts"])

FOUNDATION_ROOT = Path("/foundation-root")
PROFILES_DIR = Path("/profiles")

# Bare script filename (no directory component), same pattern used to cross-
# reference cron jobs/Auditor checks against the scripts registry in
# foundation.py -- kept as a local copy rather than a cross-module import
# since the two registries are otherwise independent domains.
_SCRIPT_NAME_RE = re.compile(r"\b[\w.-]+\.(?:sh|py|bash)\b")


def _to_out(row: FoundationScript) -> FoundationScriptOut:
    return FoundationScriptOut(
        id=str(row.id),
        name=row.name,
        path=row.path,
        description=row.description,
        doc_path=row.doc_path,
        source=row.source,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _commit_or_name_conflict(db: AsyncSession) -> None:
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A script with this name is already registered") from exc


def _context_snippet(text: str, match: re.Match[str]) -> str:
    """A short, human-readable description auto-filled from the sentence
    the script filename was mentioned in -- so a sync-discovered row isn't
    left with an empty description the operator has to fill in by hand
    (e.g. "Voice notes are transcribed by `telegram_audio_transcriber.py`
    before being handed to the agent." for a Telegram voice-message
    transcriber)."""
    window_start = max(0, match.start() - 160)
    window_end = min(len(text), match.end() + 160)
    snippet = text[window_start:window_end]
    snippet = re.sub(r"\s+", " ", snippet).strip(" `*_#-")
    if window_start > 0:
        snippet = f"…{snippet}"
    if window_end < len(text):
        snippet = f"{snippet}…"
    return snippet[:300]


def _real_script_paths() -> dict[str, str]:
    """name -> absolute container path, for every real script file under
    any profile's scripts/ dir (first match wins on a name collision)."""
    paths: dict[str, str] = {}
    if not PROFILES_DIR.is_dir():
        return paths
    for profile_dir in sorted(PROFILES_DIR.iterdir()):
        scripts_dir = profile_dir / "scripts"
        if not scripts_dir.is_dir():
            continue
        for entry in sorted(scripts_dir.iterdir()):
            if entry.is_file() and entry.suffix in (".sh", ".py", ".bash"):
                paths.setdefault(entry.name, str(entry))
    return paths


@router.get("", response_model=list[FoundationScriptOut])
async def list_foundation_scripts(db: AsyncSession = Depends(get_db)) -> list[FoundationScriptOut]:
    rows = (await db.execute(select(FoundationScript).order_by(FoundationScript.name))).scalars().all()
    return [_to_out(row) for row in rows]


@router.post("", response_model=FoundationScriptOut, status_code=status.HTTP_201_CREATED)
async def create_foundation_script(
    payload: FoundationScriptCreate, db: AsyncSession = Depends(get_db)
) -> FoundationScriptOut:
    row = FoundationScript(
        id=uuid.uuid4(),
        name=payload.name,
        path=payload.path,
        description=payload.description,
        doc_path=payload.doc_path,
        source="manual",
    )
    db.add(row)
    await _commit_or_name_conflict(db)
    await db.refresh(row)
    return _to_out(row)


@router.patch("/{script_id}", response_model=FoundationScriptOut)
async def update_foundation_script(
    script_id: uuid.UUID, payload: FoundationScriptUpdate, db: AsyncSession = Depends(get_db)
) -> FoundationScriptOut:
    row = await db.get(FoundationScript, script_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Script not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await _commit_or_name_conflict(db)
    await db.refresh(row)
    return _to_out(row)


@router.delete("/{script_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_foundation_script(script_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    row = await db.get(FoundationScript, script_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Script not found")
    await db.delete(row)
    await db.commit()


@router.get("/{script_id}/content", response_model=FoundationScriptContentOut)
async def get_foundation_script_content(
    script_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> FoundationScriptContentOut:
    row = await db.get(FoundationScript, script_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Script not found")
    if not row.path:
        raise HTTPException(status_code=404, detail="No path registered for this script")
    path = Path(row.path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File not found on disk")
    return FoundationScriptContentOut(content=path.read_text(encoding="utf-8", errors="replace"))


@router.post("/sync", response_model=FoundationScriptSyncOut)
async def sync_foundation_scripts(db: AsyncSession = Depends(get_db)) -> FoundationScriptSyncOut:
    if not FOUNDATION_ROOT.is_dir():
        raise HTTPException(status_code=404, detail="Foundation directory is not mounted")

    real_paths = _real_script_paths()
    existing_names = set((await db.execute(select(FoundationScript.name))).scalars().all())

    # name -> (relative doc path, context snippet) of the first Foundation
    # doc that mentions it.
    discovered: dict[str, tuple[str, str]] = {}
    scanned = 0
    for md_file in sorted(FOUNDATION_ROOT.rglob("*.md")):
        scanned += 1
        try:
            text = md_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel_doc = str(md_file.relative_to(FOUNDATION_ROOT))
        for match in _SCRIPT_NAME_RE.finditer(text):
            name = match.group(0)
            # Skill/how-to docs are full of generic example filenames
            # (helper.py, setup.py, test.py, ...) that aren't real scripts
            # anywhere -- only count a mention that resolves to an actual
            # file under some profile's scripts/ dir, or every sync would
            # flood the registry with noise instead of real integrations.
            if name not in real_paths:
                continue
            discovered.setdefault(name, (rel_doc, _context_snippet(text, match)))

    added = 0
    for name, (doc_path, snippet) in discovered.items():
        if name in existing_names:
            continue
        db.add(
            FoundationScript(
                id=uuid.uuid4(),
                name=name,
                path=real_paths.get(name),
                description=snippet or None,
                doc_path=doc_path,
                source="sync",
            )
        )
        added += 1
    await db.commit()

    return FoundationScriptSyncOut(
        added=added,
        already_registered=len(discovered) - added,
        scanned_docs=scanned,
        discovered=sorted(discovered),
    )

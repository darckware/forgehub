"""Cron scripts registry routes — DB-backed catalog.

Provides:
- GET  /api/v1/scripts          list all registered scripts (from DB)
- POST /api/v1/scripts/sync     scan mounted script dirs and upsert to DB
- PUT  /api/v1/scripts/{id}     update metadata (description/category/agent)
- DELETE /api/v1/scripts/{id}   soft-delete (sets active=False)

Content reads still go through /api/v1/foundation/scripts/{location}/{name}/content
(foundation.py), which resolves the actual file from the container mounts.

The three scanned locations (in priority order):
  main     → /hermes-scripts  (/root/.hermes/scripts on host)
  central  → /hermes-cron     (/root/.hermes/crons on host)
  profile  → /profiles/<agent>/scripts

'referenced_by' is computed at query time by cross-referencing the live
jobs.json stores, so it reflects the current scheduler state without an
extra sync step.
"""
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models.cron_script import CronScript

router = APIRouter(prefix="/api/v1/scripts", tags=["scripts"])

# Container-side mount paths (match docker-compose.yml volumes)
HERMES_SCRIPTS_DIR = Path("/hermes-scripts")
HERMES_CRON_DIR = Path("/hermes-cron")
PROFILES_DIR = Path("/profiles")

_SKIP_NAMES = {"jobs.json", "README_crons.md", ".jobs.lock", ".tick.lock", "__pycache__"}
_SCRIPT_EXTS = {".sh", ".py", ".bash"}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CronJobRef(BaseModel):
    job_id: str
    job_name: str
    profile: str
    schedule_display: str | None = None
    enabled: bool
    last_status: str | None = None
    last_run_at: str | None = None
    last_error: str | None = None


class ScriptOut(BaseModel):
    id: str
    name: str
    location: str
    agent: str | None
    category: str | None
    description: str | None
    path: str
    executable: bool
    active: bool
    exists_on_disk: bool
    is_symlink: bool
    symlink_target: str | None
    escapes_scripts_dir: bool
    status: str  # "ok" | "broken" | "unused"
    referenced_by: list[CronJobRef]


class ScriptListOut(BaseModel):
    scripts: list[ScriptOut]


class ScriptUpdateIn(BaseModel):
    description: str | None = None
    category: str | None = None
    agent: str | None = None
    active: bool | None = None


class SyncResultOut(BaseModel):
    inserted: int
    updated: int
    total: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HOST_PATH_REMAPS = (
    ("/root/.hermes/scripts/", HERMES_SCRIPTS_DIR),
    ("/root/.hermes/cron/", HERMES_CRON_DIR),
    ("/root/.hermes/crons/", HERMES_CRON_DIR),
    ("/root/.hermes/profiles/", PROFILES_DIR),
)


def _remap_symlink_target(raw_target: str) -> Path | None:
    for prefix, container_dir in _HOST_PATH_REMAPS:
        if raw_target.startswith(prefix):
            return container_dir / raw_target[len(prefix):]
    return None


def _script_exists(path: Path) -> tuple[bool, bool, str | None, bool]:
    """Returns (exists, is_symlink, symlink_target, escapes_dir)."""
    is_symlink = path.is_symlink()
    symlink_target: str | None = None
    escapes = False

    if is_symlink:
        try:
            raw = os.readlink(path)
        except OSError:
            return False, True, None, False
        if os.path.isabs(raw):
            symlink_target = raw
            escapes = os.path.dirname(raw) not in (
                str(path.parent),
                "/root/.hermes/scripts",
                "/root/.hermes/cron",
                "/root/.hermes/crons",
            )
            remapped = _remap_symlink_target(raw)
            exists = remapped is not None and (remapped.exists() or remapped.is_symlink())
        else:
            resolved = (path.parent / raw).resolve()
            symlink_target = str(resolved)
            escapes = str(resolved.parent) != str(path.parent.resolve())
            exists = resolved.exists()
    else:
        exists = path.exists()

    return exists, is_symlink, symlink_target, escapes


_DOCSTRING_RE = re.compile(r'^\s*(?:"""|\'\'\')(.*?)(?:"""|\'\'\')', re.DOTALL)


def _extract_description(path: Path) -> str | None:
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    if path.suffix == ".py":
        body = content
        if body.startswith("#!"):
            body = body.split("\n", 1)[1] if "\n" in body else ""
        m = _DOCSTRING_RE.match(body.lstrip())
        if m:
            doc = " ".join(m.group(1).split())
            if doc:
                return doc

    comments: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#!"):
            continue
        if stripped.startswith("#"):
            text = stripped.lstrip("#").strip()
            if text:
                comments.append(text)
            continue
        break
    return " ".join(comments) if comments else None


def _infer_category(name: str) -> str:
    n = name.lower()
    if n.startswith("foundation"):
        return "foundation"
    if n.startswith("ecosystem"):
        return "ecosystem"
    if n.startswith("battery") or n.startswith("monitor"):
        return "monitor"
    if n.startswith("pipeline"):
        return "pipeline"
    if n.startswith("kanboard"):
        return "kanboard"
    if n.startswith(("db_", "database", "init_agent")):
        return "database"
    if n.startswith("memory"):
        return "memory"
    if n.startswith("dashboard") or n.startswith("cron_health") or n.startswith("health"):
        return "dashboard"
    if any(n.startswith(p) for p in ("backup", "cleanup", "weekly", "audit_work", "wrap_cron")):
        return "maintenance"
    return "utility"


def _load_all_cron_jobs() -> list[dict[str, Any]]:
    """Load jobs from the central store + per-profile stores (same logic as
    foundation.py _load_raw_jobs, duplicated here to avoid cross-module
    import between route files)."""
    import json

    def _read(p: Path) -> str | None:
        try:
            return p.read_text(encoding="utf-8")
        except OSError:
            return None

    def _parse(content: str | None) -> list[dict[str, Any]]:
        if not content:
            return []
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                return data.get("jobs", [])
            if isinstance(data, list):
                return list(data)
        except json.JSONDecodeError:
            pass
        return []

    central = _parse(_read(HERMES_CRON_DIR / "jobs.json"))
    central_ids = {j["id"] for j in central if j.get("id")}
    central_names = {j["name"] for j in central if j.get("name")}

    extra: list[dict[str, Any]] = []
    if PROFILES_DIR.is_dir():
        for pdir in sorted(PROFILES_DIR.iterdir()):
            for pjob in _parse(_read(pdir / "cron" / "jobs.json")):
                pid, pname = pjob.get("id"), pjob.get("name")
                if (pid and pid in central_ids) or (pname and pname in central_names):
                    continue
                pjob = dict(pjob)
                if not pjob.get("profile"):
                    pjob["profile"] = pdir.name
                extra.append(pjob)
                if pid:
                    central_ids.add(pid)
                if pname:
                    central_names.add(pname)

    return central + extra


def _build_jobs_by_script(jobs: list[dict[str, Any]]) -> dict[str, list[CronJobRef]]:
    index: dict[str, list[CronJobRef]] = {}
    for j in jobs:
        script = j.get("script")
        if not script:
            continue
        ref = CronJobRef(
            job_id=j.get("id", ""),
            job_name=j.get("name", ""),
            profile=j.get("profile", ""),
            schedule_display=(j.get("schedule") or {}).get("display") or j.get("schedule_display"),
            enabled=bool(j.get("enabled", False)),
            last_status=j.get("last_status"),
            last_run_at=j.get("last_run_at"),
            last_error=j.get("last_error"),
        )
        index.setdefault(script, []).append(ref)
    return index


def _scan_script_paths() -> list[dict[str, Any]]:
    """Return a list of raw dicts describing every script file found in the
    mounted directories. Deduplicates by name: main > central > profile."""
    seen: dict[str, dict[str, Any]] = {}

    def _add(path: Path, location: str, agent: str | None) -> None:
        name = path.name
        if name in _SKIP_NAMES or name.startswith(".") or path.suffix not in _SCRIPT_EXTS:
            return
        if not (path.is_file() or path.is_symlink()):
            return
        # main takes precedence over central and profile
        priority = {"main": 0, "central": 1, "profile": 2}.get(location, 3)
        if name in seen and priority >= {"main": 0, "central": 1, "profile": 2}.get(seen[name]["location"], 3):
            return
        exists, is_symlink, symlink_target, escapes = _script_exists(path)
        seen[name] = {
            "name": name,
            "location": location,
            "agent": agent,
            "path": str(path),
            "exists": exists,
            "is_symlink": is_symlink,
            "symlink_target": symlink_target,
            "escapes": escapes,
            "executable": exists and os.access(path, os.X_OK),
            "description": _extract_description(path) if exists and not is_symlink else None,
        }

    if HERMES_SCRIPTS_DIR.is_dir():
        for entry in sorted(HERMES_SCRIPTS_DIR.iterdir()):
            if entry.is_dir():
                continue
            _add(entry, "main", None)

    if HERMES_CRON_DIR.is_dir():
        for entry in sorted(HERMES_CRON_DIR.iterdir()):
            if entry.name in _SKIP_NAMES or entry.name.startswith(".") or entry.is_dir():
                continue
            _add(entry, "central", None)

    if PROFILES_DIR.is_dir():
        for pdir in sorted(PROFILES_DIR.iterdir()):
            scripts_dir = pdir / "scripts"
            if not scripts_dir.is_dir():
                continue
            for entry in sorted(scripts_dir.iterdir()):
                if entry.is_dir():
                    continue
                _add(entry, "profile", pdir.name)

    return list(seen.values())


def _compute_status(raw: dict[str, Any], jobs_by_script: dict[str, list[CronJobRef]]) -> str:
    if not raw["exists"] or raw["escapes"]:
        return "broken"
    if raw["name"] not in jobs_by_script:
        return "unused"
    return "ok"


def _row_to_out(row: CronScript, jobs_by_script: dict[str, list[CronJobRef]]) -> ScriptOut:
    path = Path(row.path)
    _, _, _, escapes = _script_exists(path)
    refs = jobs_by_script.get(row.name, [])
    if not row.exists_on_disk or escapes:
        status = "broken"
    elif not refs:
        status = "unused"
    else:
        status = "ok"
    return ScriptOut(
        id=str(row.id),
        name=row.name,
        location=row.location,
        agent=row.agent,
        category=row.category,
        description=row.description,
        path=row.path,
        executable=row.executable,
        active=row.active,
        exists_on_disk=row.exists_on_disk,
        is_symlink=row.is_symlink,
        symlink_target=row.symlink_target,
        escapes_scripts_dir=escapes,
        status=status,
        referenced_by=refs,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=ScriptListOut)
async def list_scripts(db: AsyncSession = Depends(get_db)) -> ScriptListOut:
    """List all registered scripts from the DB, with live cron-job references."""
    result = await db.execute(
        select(CronScript).where(CronScript.active == True).order_by(  # noqa: E712
            CronScript.location, CronScript.name
        )
    )
    rows = result.scalars().all()
    jobs = _load_all_cron_jobs()
    jobs_by_script = _build_jobs_by_script(jobs)
    return ScriptListOut(scripts=[_row_to_out(r, jobs_by_script) for r in rows])


@router.post("/sync", response_model=SyncResultOut)
async def sync_scripts(db: AsyncSession = Depends(get_db)) -> SyncResultOut:
    """Scan the mounted script directories and upsert every script into the
    DB. Preserves manually-edited description/category/agent if already set;
    only overwrites them when the DB row doesn't have a value yet."""
    scanned = _scan_script_paths()
    jobs = _load_all_cron_jobs()
    jobs_by_script = _build_jobs_by_script(jobs)

    # Build a map of agent from cron jobs for scripts without an explicit agent
    script_agent_from_jobs: dict[str, str] = {}
    for script_name, refs in jobs_by_script.items():
        if refs:
            script_agent_from_jobs[script_name] = refs[0].profile

    existing_result = await db.execute(select(CronScript))
    existing: dict[str, CronScript] = {r.name: r for r in existing_result.scalars().all()}

    inserted = 0
    updated = 0
    now = datetime.now(timezone.utc)

    for raw in scanned:
        name = raw["name"]
        inferred_agent = raw["agent"] or script_agent_from_jobs.get(name)
        inferred_cat = _infer_category(name)
        inferred_desc = raw["description"]

        if name in existing:
            row = existing[name]
            changed = False
            # Preserve manually-set values; fill blanks
            if row.description is None and inferred_desc:
                row.description = inferred_desc
                changed = True
            if row.agent is None and inferred_agent:
                row.agent = inferred_agent
                changed = True
            if row.category is None:
                row.category = inferred_cat
                changed = True
            # Always update runtime health fields
            for attr, val in [
                ("path", raw["path"]),
                ("location", raw["location"]),
                ("executable", raw["executable"]),
                ("exists_on_disk", raw["exists"]),
                ("is_symlink", raw["is_symlink"]),
                ("symlink_target", raw["symlink_target"]),
            ]:
                if getattr(row, attr) != val:
                    setattr(row, attr, val)
                    changed = True
            if changed:
                row.updated_at = now
                updated += 1
        else:
            row = CronScript(
                id=uuid.uuid4(),
                name=name,
                location=raw["location"],
                agent=inferred_agent,
                category=inferred_cat,
                description=inferred_desc,
                path=raw["path"],
                executable=raw["executable"],
                active=True,
                exists_on_disk=raw["exists"],
                is_symlink=raw["is_symlink"],
                symlink_target=raw["symlink_target"],
            )
            db.add(row)
            inserted += 1

    await db.commit()
    return SyncResultOut(inserted=inserted, updated=updated, total=len(scanned))


@router.put("/{script_id}", response_model=ScriptOut)
async def update_script(
    script_id: str, payload: ScriptUpdateIn, db: AsyncSession = Depends(get_db)
) -> ScriptOut:
    """Update a script's description, category, agent, or active flag."""
    try:
        uid = uuid.UUID(script_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid script id")
    result = await db.execute(select(CronScript).where(CronScript.id == uid))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Script not found")
    if payload.description is not None:
        row.description = payload.description
    if payload.category is not None:
        row.category = payload.category
    if payload.agent is not None:
        row.agent = payload.agent
    if payload.active is not None:
        row.active = payload.active
    await db.commit()
    jobs = _load_all_cron_jobs()
    return _row_to_out(row, _build_jobs_by_script(jobs))


@router.delete("/{script_id}")
async def delete_script(script_id: str, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    """Soft-delete a script (sets active=False)."""
    try:
        uid = uuid.UUID(script_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid script id")
    result = await db.execute(select(CronScript).where(CronScript.id == uid))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Script not found")
    row.active = False
    await db.commit()
    return {"id": script_id, "status": "deactivated"}

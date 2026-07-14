"""System control routes for Git status and Hermes backup management."""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import shlex
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import _APP_CONFIG_FILE, settings
from app.core.deps import get_current_admin
from app.db.base import get_db
from app.db.models.project import Project
from app.db.models.user import User

router = APIRouter(prefix="/api/v1/system-control", tags=["system-control"])


def _now_local() -> datetime:
    """Wall-clock time in settings.TIMEZONE (default America/Sao_Paulo) --
    used for filenames ForgeHub itself generates (backup archives) so they
    read as the actual local moment, not UTC or whatever the host OS
    happens to be set to. Falls back to naive local (OS) time if TIMEZONE
    is somehow invalid -- never hard-fails a backup over a timezone typo."""
    try:
        return datetime.now(ZoneInfo(settings.TIMEZONE))
    except (ZoneInfoNotFoundError, ValueError):
        return datetime.now()


class CommitRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    # Same KNOWN_REPOS key as GET /status's `repo` query param -- omitted/
    # unknown falls back to DEFAULT_REPO, same as status.
    repo: str | None = None

# The container's own copy of the source (under /app) is not a git checkout
# at all -- git status/log must run against the real repo on the HOST, via
# the host-bridge's /v1/exec (same bridge already used below for fs/backup
# ops; the container image doesn't even have a `git` binary installed).
#
# Only ONE hardcoded system-level entry: Hermes/Foundation itself, which is
# deliberately not a ForgeHub Project (it's the underlying agent platform,
# not something planned/executed through ForgeHub's domain model). Every
# other checkout -- including ForgeHub's own -- is a registered Project
# (working_directory_path + github_repo_url, set at project registration)
# merged in dynamically by _registered_project_repos below. There is
# deliberately no separate ad-hoc "add a repo" registry anymore: project
# registration is the one source of truth for what Git Control/Backup can
# see (2026-07-11 -- a prior KNOWN_REPOS+extras-file version of this lived
# here briefly and was removed once Project gained github_repo_url/
# backup_enabled).
#
# NOTE: a checkout path must have its own `.git` boundary. A path that's
# actually a subdirectory *inside* a larger monorepo (e.g. ForgeRouter used
# to live as a tracked folder inside the Hermes repo, at
# /root/.hermes/forgerouter, with /root/project/forgerouter just a symlink
# to it) has no `.git` of its own, so any `git -C <path>` call silently
# walks up to the parent repo's root and reports THAT repo's branch/status
# instead -- which looks like "the wrong repo" in the UI without erroring
# (see governance/FOUNDATION.md's 2026-07-11 ForgeRouter note for the
# incident this comment describes).
#
# Values (HERMES_SOURCE_PATH, GIT_CONTROL_DEFAULT_REPO, BACKUP_ROOT,
# TRASH_ROOT, CLEANUP_SCAN_ROOT, CLEANUP_PRUNE_PATHS/NAMES) all come from
# `settings` (backend/app/core/config.py), which loads them from repo-root
# `forgehub.config` -- these are operator-tunable defaults, not hardcoded
# constants, so retuning any of them is a config edit, not a code change
# (2026-07-11).
KNOWN_REPOS: dict[str, str] = {
    "hermes": settings.HERMES_SOURCE_PATH,
}
DEFAULT_REPO = settings.GIT_CONTROL_DEFAULT_REPO
BACKUP_DIR = settings.BACKUP_ROOT

# "Run Cleanup" moves eligible files here; "Empty trash" (a separate
# button/action, 2026-07-11 -- previously one click did both) permanently
# deletes its contents. Independent of the external "foundation-clear"
# Hermes cron, which always empties its own hardcoded /root/trash on its
# own weekly schedule regardless of this setting.
TRASH_ROOT = settings.TRASH_ROOT


def _all_repos() -> dict[str, str]:
    return dict(KNOWN_REPOS)

# Scanned read-only for the Cleanup card's inventory (grouped by type
# below) -- nothing here gets deleted by cleanup-scan, only by the operator
# explicitly clearing a given log another way, or POST /cleanup-run (which
# only moves matches into TRASH_ROOT, never deletes -- see POST
# /cleanup-empty-trash for the separate, permanent step).
#
# Whole filesystem, not just ~/.hermes: /mnt is the WSL host filesystem
# passthrough (huge, irrelevant -- excluded per the operator's own
# instruction), the rest are pseudo-filesystems or noise dirs that would
# otherwise make `find` slow or return junk matches (same convention as
# ecosystem_cleanup.py's own SKIP_PARTS).
SCAN_ROOT = settings.CLEANUP_SCAN_ROOT
PRUNE_PATHS = settings.CLEANUP_PRUNE_PATHS
PRUNE_NAMES = settings.CLEANUP_PRUNE_NAMES


def _prune_clause() -> str:
    path_terms = " -o ".join(f"-path {shlex.quote(p)}" for p in PRUNE_PATHS)
    name_terms = " -o ".join(f"-name {shlex.quote(n)}" for n in PRUNE_NAMES)
    return f"\\( {path_terms} -o {name_terms} \\) -prune -o"


# Rotated logs (errors.log.1, agent.log.3, ...) must categorize the same as
# their unrotated source -- strip the trailing ".<N>" before matching.
_ROTATION_SUFFIX_RE = re.compile(r"\.\d+$")


def _categorize_log(path: str) -> str:
    """Buckets a log path by what produces it -- mirrors the actual
    directory conventions found under .../profiles/*/ (see the per-agent
    gateway/agent/errors/interrupt_debug.log pattern, including their
    rotated .N variants) rather than a generic extension-only grouping,
    since "what wrote this" is what matters when deciding whether it's
    safe to clear."""
    name = _ROTATION_SUFFIX_RE.sub("", path.rsplit("/", 1)[-1])
    if "/cron/logs/" in path:
        return "Cron execution logs"
    if name == "agent.log":
        return "Agent logs"
    if name == "errors.log":
        return "Error logs"
    if name.startswith("gateway"):
        return "Gateway logs"
    if name == "interrupt_debug.log":
        return "Interrupt debug logs"
    if "hindsight" in name:
        return "Hindsight logs"
    if "/webui/" in path:
        return "WebUI logs"
    return "Other logs"


async def _bridge(method: str, path: str, **kwargs) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.request(
            method,
            f"{settings.CHAT_BRIDGE_URL}{path}",
            headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
            **kwargs,
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Host-bridge error: {resp.text[:500]}")
    return resp.json()


async def _run_git(repo_root: str, *args: str) -> str:
    command = "git -C " + shlex.quote(repo_root) + " " + " ".join(shlex.quote(a) for a in args)
    data = await _bridge("POST", "/v1/exec", json={"command": command})
    if data["exit_code"] != 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(data["stderr"] or "").strip() or "git failed",
        )
    return (data["stdout"] or "").strip()


async def _registered_project_repos(db: AsyncSession) -> dict[str, tuple[str, str]]:
    """Every registered Project with a working_directory_path, as
    additional Git Control picker entries -- key f"project:{id}" (colon
    can't collide with a REPO_KEY_RE-validated manual key, which forbids
    it) mapped to (path, display label = project name). Projects without a
    working_directory_path set yet are omitted rather than shown as a
    broken entry."""
    result = await db.execute(select(Project).where(Project.working_directory_path.isnot(None)))
    return {f"project:{p.id}": (p.working_directory_path, p.name) for p in result.scalars().all()}


@router.get("/status")
async def get_system_control_status(
    repo: str | None = None, _admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    # Unknown/omitted repo key falls back to the default instead of 400ing --
    # a stale key in a saved link/bookmark should still load something.
    static_repos = _all_repos()
    project_repos = await _registered_project_repos(db)
    all_repos = {**static_repos, **{k: v[0] for k, v in project_repos.items()}}
    repo_key = repo if repo in all_repos else DEFAULT_REPO
    repo_root = all_repos[repo_key]
    branch = await _run_git(repo_root, "branch", "--show-current")
    head = await _run_git(repo_root, "rev-parse", "HEAD")
    short_head = await _run_git(repo_root, "rev-parse", "--short", "HEAD")
    last_commit = await _run_git(repo_root, "log", "-1", "--pretty=format:%H%n%an%n%ad%n%s")
    status_short = await _run_git(repo_root, "status", "--short")
    status_lines = [line for line in status_short.splitlines() if line.strip()]
    try:
        await _bridge("POST", "/v1/fs/mkdir", json={"path": BACKUP_DIR})
    except HTTPException:
        pass
    backup_listing = await _bridge("GET", "/v1/fs/list", params={"path": BACKUP_DIR})
    backups = [
        {
            "name": entry.get("name"),
            "path": entry.get("path"),
            "size": entry.get("size"),
            "type": entry.get("type"),
        }
        for entry in backup_listing.get("entries", [])
        if entry.get("type") == "file"
    ]
    backups.sort(key=lambda item: item["name"] or "")
    commit_lines = last_commit.splitlines()
    return {
        "git": {
            "repo_key": repo_key,
            "repo_root": repo_root,
            "branch": branch or "detached",
            "head": head,
            "short_head": short_head,
            "dirty_count": len(status_lines),
            "status_lines": status_lines,
            "last_commit": {
                "hash": commit_lines[0] if len(commit_lines) > 0 else head,
                "author": commit_lines[1] if len(commit_lines) > 1 else None,
                "date": commit_lines[2] if len(commit_lines) > 2 else None,
                "subject": commit_lines[3] if len(commit_lines) > 3 else None,
            },
        },
        "available_repos": [
            {"key": key, "path": path, "removable": key not in KNOWN_REPOS, "label": key, "kind": "system"}
            for key, path in sorted(static_repos.items())
        ]
        + [
            {"key": key, "path": path, "removable": False, "label": label, "kind": "project"}
            for key, (path, label) in sorted(project_repos.items(), key=lambda kv: kv[1][1].lower())
        ],
        "backups": {
            "path": BACKUP_DIR,
            "count": len(backups),
            "entries": backups,
        },
    }


@router.post("/commit")
async def commit_changes(
    payload: CommitRequest, _admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """Stages everything (`git add -A`) and commits with the given message --
    no partial/selective staging, since Git Control only ever shows the
    flat status_lines list, not a per-file selection UI. Never pushes:
    that's a separate, more consequential action this button deliberately
    doesn't take on."""
    project_repos = await _registered_project_repos(db)
    all_repos = {**_all_repos(), **{k: v[0] for k, v in project_repos.items()}}
    repo_key = payload.repo if payload.repo in all_repos else DEFAULT_REPO
    repo_root = all_repos[repo_key]
    await _run_git(repo_root, "add", "-A")
    await _run_git(repo_root, "commit", "-m", payload.message)
    last_commit = await _run_git(repo_root, "log", "-1", "--pretty=format:%H%n%an%n%ad%n%s")
    commit_lines = last_commit.splitlines()
    return {
        "repo_key": repo_key,
        "hash": commit_lines[0] if len(commit_lines) > 0 else None,
        "author": commit_lines[1] if len(commit_lines) > 1 else None,
        "date": commit_lines[2] if len(commit_lines) > 2 else None,
        "subject": commit_lines[3] if len(commit_lines) > 3 else None,
    }


# ---------------------------------------------------------------------------
# Backups -- targets are "hermes" (fixed, archives written flat into
# BACKUP_DIR, unchanged since before this system existed) or "project:<id>"
# (only for a Project with backup_enabled=true, archives written under
# Project.backup_location -- set explicitly at project registration, or
# defaulted to BACKUP_DIR/<slug-of-name> (e.g. "/root/backup/forgehub")
# whenever it's empty; that default is only ever computed on the fly here,
# never silently written back to the row). Each archive inside is named
# "<slug>-<YYYYmmdd-HHMMSS>.tar.gz". Deliberately separate storage per
# target -- per explicit operator request, a project's backups must never
# intermix with Hermes's or another project's. "all" is a write-only
# pseudo-target for POST /backups/run (fan-out to every currently-eligible
# target, each still landing in its own directory); it is not a listable
# target.
# ---------------------------------------------------------------------------
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _project_slug(project: Project) -> str:
    return _SLUG_RE.sub("-", project.name.lower()).strip("-") or str(project.id)


def _project_backup_location(project: Project) -> str:
    return project.backup_location or f"{BACKUP_DIR}/{_project_slug(project)}"


async def _get_project_or_404(project_id: str, db: AsyncSession) -> Project:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


async def _backup_dir_for_target(target: str, db: AsyncSession) -> str:
    if target == "hermes":
        return BACKUP_DIR
    if target.startswith("project:"):
        project = await _get_project_or_404(target.split(":", 1)[1], db)
        return _project_backup_location(project)
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown backup target '{target}'")


@router.get("/backup-targets")
async def list_backup_targets(
    _admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    result = await db.execute(select(Project).where(Project.backup_enabled.is_(True)))
    targets = [
        {
            "key": "hermes",
            "label": "Hermes",
            "kind": "system",
            "ready": True,
            "source": KNOWN_REPOS["hermes"],
            "location": BACKUP_DIR,
        }
    ]
    for project in result.scalars().all():
        targets.append(
            {
                "key": f"project:{project.id}",
                "label": project.name,
                "kind": "project",
                "ready": bool(project.working_directory_path),
                "source": project.working_directory_path,
                "location": _project_backup_location(project),
            }
        )
    return {"targets": targets}


async def _run_backup_for_target(target: str, db: AsyncSession) -> dict[str, Any]:
    if target == "hermes":
        # Explicit archive_name (not host-bridge's own default) so it's
        # subject to the same settings.TIMEZONE rule as project backups.
        archive_name = f"hermes-backup-{_now_local().strftime('%Y%m%d-%H%M%S')}.tar.gz"
        result = await _bridge(
            "POST",
            "/v1/system/hermes-backup",
            json={"source_path": KNOWN_REPOS["hermes"], "backup_dir": BACKUP_DIR, "archive_name": archive_name},
        )
        return {"target": target, "label": "Hermes", **result}

    if not target.startswith("project:"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown backup target '{target}'")
    project = await _get_project_or_404(target.split(":", 1)[1], db)
    if not project.backup_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Backup is not enabled for project '{project.name}' -- enable it on its registration first",
        )
    if not project.working_directory_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Project '{project.name}' has no working_directory_path set",
        )
    archive_name = f"{_project_slug(project)}-{_now_local().strftime('%Y%m%d-%H%M%S')}.tar.gz"
    result = await _bridge(
        "POST",
        "/v1/system/hermes-backup",
        json={
            "source_path": project.working_directory_path,
            "backup_dir": _project_backup_location(project),
            "archive_name": archive_name,
        },
    )
    return {"target": target, "label": project.name, **result}


class BackupRunRequest(BaseModel):
    target: str = "hermes"  # "hermes" | "project:<uuid>" | "all"


@router.post("/backups/run")
async def run_backup(
    payload: BackupRunRequest, _admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    if payload.target != "all":
        return {"results": [await _run_backup_for_target(payload.target, db)], "errors": []}

    result = await db.execute(
        select(Project).where(Project.backup_enabled.is_(True), Project.working_directory_path.isnot(None))
    )
    targets = ["hermes"] + [f"project:{p.id}" for p in result.scalars().all()]
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for t in targets:
        try:
            results.append(await _run_backup_for_target(t, db))
        except HTTPException as e:
            errors.append({"target": t, "detail": e.detail})
    return {"results": results, "errors": errors}


@router.get("/backups")
async def list_backups(
    target: str = "hermes", _admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    backup_dir = await _backup_dir_for_target(target, db)
    try:
        await _bridge("POST", "/v1/fs/mkdir", json={"path": backup_dir})
    except HTTPException:
        pass
    listing = await _bridge("GET", "/v1/fs/list", params={"path": backup_dir})
    entries = [
        {"name": e.get("name"), "path": e.get("path"), "size": e.get("size"), "type": e.get("type")}
        for e in listing.get("entries", [])
        if e.get("type") == "file"
    ]
    entries.sort(key=lambda item: item["name"] or "")
    return {"target": target, "path": backup_dir, "count": len(entries), "entries": entries}


@router.delete("/backups/{target}/{filename}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_backup(
    target: str, filename: str, _admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
) -> None:
    if "/" in filename or "\\" in filename or filename in (".", ".."):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")
    backup_dir = await _backup_dir_for_target(target, db)
    await _bridge("DELETE", "/v1/fs/delete", params={"path": f"{backup_dir}/{filename}", "recursive": False})


async def _scan_find(find_expr: str) -> list[dict[str, Any]]:
    """Runs `find SCAN_ROOT <prune clause> <find_expr> -printf ...` over the
    host-bridge -- find_expr is just the test/action part (e.g.
    `-type f -iname '*.bak*'`), the root and prune clause are shared by
    every scan so /mnt etc. are consistently excluded everywhere."""
    command = f"find {shlex.quote(SCAN_ROOT)} {_prune_clause()} {find_expr} -printf '%s|%T@|%p\\n'"
    data = await _bridge("POST", "/v1/exec", json={"command": command})
    if data["exit_code"] != 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(data["stderr"] or "").strip() or "scan failed",
        )
    results: list[dict[str, Any]] = []
    for line in (data["stdout"] or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            size_str, mtime_str, path = line.split("|", 2)
            mtime = datetime.fromtimestamp(float(mtime_str), tz=timezone.utc)
        except ValueError:
            continue
        results.append({"path": path, "name": path.rsplit("/", 1)[-1], "size": int(size_str), "mtime": mtime.isoformat()})
    return results


async def _script_categories(db: AsyncSession) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Reuses foundation.py's own script registry (same-process function
    call, not a second HTTP round-trip) rather than re-deriving "orphaned"
    from scratch -- _list_scripts() cross-references every profile's
    scripts/ dir against three reference sources (a cron job invoking the
    script by filename, an enabled Auditor check's command naming it, or
    another referenced script calling it by path in its own source, e.g. a
    cron-wrapper .sh invoking its .py implementation), so status="unused"
    IS the definition of an orphaned script -- not referenced by the Crons
    screen, the Auditor screen, or a chain starting from either (see
    foundation_cleanup.sh/foundation_daily_cleanup.sh/cleanup_old_logs.sh,
    found self-referencing and genuinely orphaned during the audit that
    prompted this card; foundation_audit.py/checklist_verifier.py/
    audit_work_dir.py/ecosystem_readonly_healthcheck.py were wrongly
    flagged here before the Auditor/chain cross-reference was added,
    2026-07-09).

    Duplicates are content-hash groups (sha256 of the file bytes, not just
    matching filenames) -- two scripts with the same name in different
    profiles' scripts/ dirs are NOT duplicates unless their content also
    matches.
    """
    from app.api.routes.foundation import _list_scripts  # local import: avoid a module-load-order cycle

    scripts, contents = await _list_scripts(db)

    old_scripts: list[dict[str, Any]] = []
    hash_groups: dict[str, list[dict[str, Any]]] = {}
    for s in scripts:
        if not s.exists or s.is_symlink:
            continue
        # Reuse the bytes _list_scripts already read off disk instead of
        # reading every script a second time just to hash it.
        content = contents.get((s.location, s.name))
        if content is None:
            continue
        try:
            mtime = datetime.fromtimestamp(Path(s.path).stat().st_mtime, tz=timezone.utc).isoformat()
        except OSError:
            continue
        entry = {"path": s.path, "name": f"{s.location}/{s.name}", "size": len(content), "mtime": mtime}
        if s.status == "unused":
            old_scripts.append(entry)
        hash_groups.setdefault(hashlib.sha256(content).hexdigest(), []).append(entry)

    duplicate_scripts = [entry for group in hash_groups.values() if len(group) > 1 for entry in group]
    return old_scripts, duplicate_scripts


@router.get("/cleanup-scan")
async def cleanup_scan(
    _admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """Read-only inventory of everything the ecosystem's cleanup scripts
    already consider fair game, grouped by type -- nothing is deleted
    here, this only answers "what would there be to clean." See
    POST /cleanup-run for the actual action (which only ever acts on the
    logs/cron-output/backups categories, never on scripts -- see its own
    docstring for why deleting a script is deliberately left manual).

    Five sources of truth for what "cleanup-worthy" means, each a
    directory match (not an extension filter) so rotated logs
    (errors.log.1, agent.log.3, ...) and non-.md cron output don't slip
    through:
    - */profiles/*/logs/* and */cron/logs/* -- every producer under a
      profile's own logs dir plus its cron execution logs (sub-grouped by
      _categorize_log).
    - *.bak* -- same definition ecosystem_cleanup.py's BACKUP_PATTERNS
      already uses (SOUL.md.bak*, .env.bak*, config.yaml.bak*, etc. all
      contain the literal substring "bak", one glob covers the whole set).
    - */cron/output/* -- per-run job output snapshots (any extension), not
      covered by any existing cleanup script but confirmed as
      cleanup-worthy by the operator.
    - Old/unused scripts and duplicate scripts -- see _script_categories.
    """
    groups: dict[str, list[dict[str, Any]]] = {}

    # The four scans below are independent (different find roots/filters and
    # a separate DB+filesystem pass for scripts) -- run concurrently instead
    # of as four sequential host-bridge round trips.
    log_files, backup_files, cron_output_files, (old_scripts, duplicate_scripts) = await asyncio.gather(
        _scan_find("-type f \\( -path '*/profiles/*/logs/*' -o -path '*/cron/logs/*' \\)"),
        _scan_find("-type f -iname '*.bak*'"),
        _scan_find("-type f -path '*/cron/output/*'"),
        _script_categories(db),
    )

    for f in log_files:
        groups.setdefault(_categorize_log(f["path"]), []).append(f)

    if backup_files:
        groups["Backup files"] = backup_files

    if cron_output_files:
        groups["Cron output files"] = cron_output_files
    if old_scripts:
        groups["Old/unused scripts"] = old_scripts
    if duplicate_scripts:
        groups["Duplicate scripts"] = duplicate_scripts

    categories = []
    for category, files in groups.items():
        files.sort(key=lambda f: -f["size"])
        categories.append(
            {"category": category, "count": len(files), "total_size": sum(f["size"] for f in files), "files": files}
        )
    categories.sort(key=lambda c: -c["total_size"])
    return {
        "root": SCAN_ROOT,
        "total_count": sum(c["count"] for c in categories),
        "total_size": sum(c["total_size"] for c in categories),
        "categories": categories,
    }


def _move_command(find_test: str, min_age_days: int, only_rotated: bool = False) -> str:
    """A single host-bridge exec: find eligible files, move each into
    /root/trash preserving its original absolute path (mirrors
    ecosystem_cleanup.py's own move_to_trash -- same TRASH_ROOT, same
    "rel = path with leading / stripped" layout), print one "MOVED: <path>"
    line per success. `only_rotated` additionally requires the basename to
    end in a numeric suffix (errors.log.1, agent.log.3, ...) -- this is
    what keeps a running agent's live, currently-open log untouched: the
    live file (agent.log, no suffix) never matches."""
    rotated_filter = " | grep -E '\\.[0-9]+$'" if only_rotated else ""
    trash_root = shlex.quote(TRASH_ROOT)
    return (
        f"find {shlex.quote(SCAN_ROOT)} {_prune_clause()} {find_test} -mtime +{min_age_days} -print"
        f"{rotated_filter}"
        " | while IFS= read -r src; do "
        '[ -z "$src" ] && continue; '
        f'rel="${{src#/}}"; dest={trash_root}"/$rel"; '
        'mkdir -p "$(dirname "$dest")" && mv -- "$src" "$dest" && echo "MOVED: $src"; '
        "done"
    )


@router.post("/cleanup-run")
async def cleanup_run(_admin: User = Depends(get_current_admin)) -> dict[str, Any]:
    """Sweeps cleanup-eligible files into TRASH_ROOT -- reversible, never
    deletes anything (see POST /cleanup-empty-trash for that, a separate
    action/button as of 2026-07-11; previously this endpoint did both in
    one click). Deliberately narrower than GET /cleanup-scan's full
    inventory:
    - Only ROTATED logs (errors.log.1, agent.log.3, ...) under
      */profiles/*/logs/* and */cron/logs/* -- the live, currently-open
      agent.log/errors.log/gateway.log/interrupt_debug.log are never
      matched, so a running Hermes agent's active log handle is never
      disturbed.
    - */cron/output/* and the rotated logs above: only files older than
      1 day -- nothing from today gets swept.
    - *.bak* files: only older than 30 days, matching
      ecosystem_cleanup.py's own RETENTION_DAYS for backups.
    """
    moved: list[str] = []
    sweep_errors: list[str] = []
    for command in (
        _move_command("-type f \\( -path '*/profiles/*/logs/*' -o -path '*/cron/logs/*' \\)", 1, only_rotated=True),
        _move_command("-type f -path '*/cron/output/*'", 1),
        _move_command("-type f -iname '*.bak*'", 30),
    ):
        data = await _bridge("POST", "/v1/exec", json={"command": command})
        for line in (data["stdout"] or "").splitlines():
            if line.startswith("MOVED: "):
                moved.append(line[len("MOVED: "):])
        sweep_errors.extend(line for line in (data["stderr"] or "").splitlines() if line.strip())

    return {
        "swept_count": len(moved),
        "swept": moved,
        "sweep_errors": sweep_errors,
        "trash_root": TRASH_ROOT,
    }


@router.post("/cleanup-empty-trash")
async def cleanup_empty_trash(_admin: User = Depends(get_current_admin)) -> dict[str, Any]:
    """Permanently deletes everything currently under TRASH_ROOT (the
    directory itself is kept, only its contents go) -- separate from
    POST /cleanup-run so an operator can review what got swept there
    before committing to deletion. Mirrors the external
    create_trash_cleanup_task.sh's own before/after item-count logic, but
    runs directly via host-bridge exec against the configurable
    TRASH_ROOT rather than that script's hardcoded /root/trash."""
    # nullglob must be re-enabled around EACH glob expansion, not just once
    # up front -- with it off, an empty-directory glob that matches nothing
    # stays as the literal unexpanded `TRASH_ROOT/*` string and counts as
    # one bogus "remaining" item instead of zero (caught 2026-07-11 testing
    # this endpoint: emptying an already-empty trash reported
    # remaining_items: 1). Mirrors create_trash_cleanup_task.sh's own
    # three separate shopt -s/-u pairs.
    trash_root = shlex.quote(TRASH_ROOT)
    command = (
        f"shopt -s dotglob nullglob; items=({trash_root}/*); shopt -u dotglob nullglob; before=${{#items[@]}}; "
        f"rm -rf -- {trash_root}/*; "
        f"shopt -s dotglob nullglob; items2=({trash_root}/*); shopt -u dotglob nullglob; after=${{#items2[@]}}; "
        'echo "deleted_items: $before"; echo "remaining_items: $after"'
    )
    data = await _bridge("POST", "/v1/exec", json={"command": command})
    if data["exit_code"] != 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(data["stderr"] or "").strip() or "emptying trash failed",
        )
    return {"trash_root": TRASH_ROOT, "output": (data["stdout"] or "").strip()}


# ---------------------------------------------------------------------------
# App config -- read/write UI for forgehub.config (see that file's own
# header comment). Every field here already has a settings.<NAME> default
# used elsewhere in this module; this section is the one place that turns
# a POST into a rewritten config file plus a live in-memory update, so an
# operator retuning a default doesn't need file access or a restart.
# ---------------------------------------------------------------------------
_APP_CONFIG_TEMPLATE = """# ForgeHub application defaults -- NOT secrets/credentials (those stay in
# .env, which core/config.py also loads). This file holds the domain-level
# default paths/behavior that used to be hardcoded constants scattered
# across route modules (mainly api/routes/system_control.py), so an
# operator can retune them without touching source code.
#
# Loaded by backend/app/core/config.py (Settings.model_config's env_file
# tuple) -- same dotenv KEY=VALUE format as .env, just a separate file
# because these are ForgeHub's own operational defaults, not
# infra/credential wiring. Editable from the app itself at Settings ->
# System defaults (admin only, GET/PUT /api/v1/system-control/config) --
# this file is regenerated whenever that form is saved, so hand edits made
# between saves are preserved but comments/layout always snap back to this
# canonical form.

# System Control -- Git Control
# Fixed system-level git checkout Git Control always offers, in addition
# to every registered Project with a working_directory_path (see
# system_control.py's module docstring for why Hermes isn't a Project).
HERMES_SOURCE_PATH={hermes_source_path}
# Key GET /status falls back to when `repo` is omitted/unknown.
GIT_CONTROL_DEFAULT_REPO={git_control_default_repo}

# System Control -- Backups
# Hermes backups land flat here; each backup-enabled project gets its own
# subdirectory (BACKUP_ROOT/<slug-of-name>) unless it sets its own
# Project.backup_location.
BACKUP_ROOT={backup_root}

# System Control -- Cleanup
# "Run Cleanup" moves eligible files here; "Empty trash" permanently
# deletes this directory's contents -- two separate buttons. Independent
# of the external "foundation-clear" Hermes cron, which always empties
# its own hardcoded /root/trash regardless of this setting.
TRASH_ROOT={trash_root}
# Root the Cleanup card's inventory scan walks.
CLEANUP_SCAN_ROOT={cleanup_scan_root}
# Paths/directory names pruned from that scan (JSON arrays -- pydantic-settings
# parses List[str] env values as JSON).
CLEANUP_PRUNE_PATHS={cleanup_prune_paths}
CLEANUP_PRUNE_NAMES={cleanup_prune_names}

# General
# IANA zone for timestamps ForgeHub itself generates (e.g. backup archive
# filenames) -- default matches the operator's actual timezone (UTC-3).
TIMEZONE={timezone}
"""


def _settings_to_config_out(s) -> dict[str, Any]:
    return {
        "hermes_source_path": s.HERMES_SOURCE_PATH,
        "git_control_default_repo": s.GIT_CONTROL_DEFAULT_REPO,
        "backup_root": s.BACKUP_ROOT,
        "trash_root": s.TRASH_ROOT,
        "cleanup_scan_root": s.CLEANUP_SCAN_ROOT,
        "cleanup_prune_paths": list(s.CLEANUP_PRUNE_PATHS),
        "cleanup_prune_names": list(s.CLEANUP_PRUNE_NAMES),
        "timezone": s.TIMEZONE,
    }


class AppConfigUpdate(BaseModel):
    hermes_source_path: str = Field(min_length=1, max_length=1024)
    git_control_default_repo: str = Field(min_length=1, max_length=64)
    backup_root: str = Field(min_length=1, max_length=1024)
    trash_root: str = Field(min_length=1, max_length=1024)
    cleanup_scan_root: str = Field(min_length=1, max_length=1024)
    cleanup_prune_paths: list[str] = Field(default_factory=list)
    cleanup_prune_names: list[str] = Field(default_factory=list)
    timezone: str = Field(min_length=1, max_length=64)


@router.get("/config")
async def get_app_config(_admin: User = Depends(get_current_admin)) -> dict[str, Any]:
    return _settings_to_config_out(settings)


@router.put("/config")
async def update_app_config(
    payload: AppConfigUpdate, _admin: User = Depends(get_current_admin)
) -> dict[str, Any]:
    try:
        ZoneInfo(payload.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"'{payload.timezone}' is not a valid IANA timezone"
        )
    # trash_root gets `rm -rf {trash_root}/*` run against it by POST
    # /cleanup-empty-trash -- guard against the obvious catastrophic typos
    # (empty, relative, or filesystem-root) before ever persisting it.
    trash_root = payload.trash_root.rstrip("/")
    if not trash_root.startswith("/") or trash_root in ("", "/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="trash_root must be an absolute path and not the filesystem root",
        )

    # Mutates the live singleton in place -- every module imported `settings`
    # once at load time (`from app.core.config import settings`), so they
    # all hold the SAME object; setting attributes on it takes effect on
    # the very next request, no restart needed.
    settings.HERMES_SOURCE_PATH = payload.hermes_source_path
    settings.GIT_CONTROL_DEFAULT_REPO = payload.git_control_default_repo
    settings.BACKUP_ROOT = payload.backup_root
    settings.TRASH_ROOT = trash_root
    settings.CLEANUP_SCAN_ROOT = payload.cleanup_scan_root
    settings.CLEANUP_PRUNE_PATHS = payload.cleanup_prune_paths
    settings.CLEANUP_PRUNE_NAMES = payload.cleanup_prune_names
    settings.TIMEZONE = payload.timezone

    _APP_CONFIG_FILE.write_text(
        _APP_CONFIG_TEMPLATE.format(
            hermes_source_path=settings.HERMES_SOURCE_PATH,
            git_control_default_repo=settings.GIT_CONTROL_DEFAULT_REPO,
            backup_root=settings.BACKUP_ROOT,
            trash_root=settings.TRASH_ROOT,
            cleanup_scan_root=settings.CLEANUP_SCAN_ROOT,
            cleanup_prune_paths=json.dumps(settings.CLEANUP_PRUNE_PATHS),
            cleanup_prune_names=json.dumps(settings.CLEANUP_PRUNE_NAMES),
            timezone=settings.TIMEZONE,
        )
    )

    # This module's own KNOWN_REPOS/DEFAULT_REPO/BACKUP_DIR/TRASH_ROOT/
    # SCAN_ROOT/PRUNE_PATHS/PRUNE_NAMES were computed ONCE from `settings`
    # at import time (see their definitions near the top of this file) --
    # a settings mutation doesn't retroactively change them, so refresh
    # them here too. Every request re-reads these module names directly
    # (they're not re-derived from `settings` per-request), so without
    # this the rest of Git Control/Backups/Cleanup would keep using stale
    # values until the process restarts.
    global KNOWN_REPOS, DEFAULT_REPO, BACKUP_DIR, TRASH_ROOT, SCAN_ROOT, PRUNE_PATHS, PRUNE_NAMES
    KNOWN_REPOS = {"hermes": settings.HERMES_SOURCE_PATH}
    DEFAULT_REPO = settings.GIT_CONTROL_DEFAULT_REPO
    BACKUP_DIR = settings.BACKUP_ROOT
    TRASH_ROOT = settings.TRASH_ROOT
    SCAN_ROOT = settings.CLEANUP_SCAN_ROOT
    PRUNE_PATHS = settings.CLEANUP_PRUNE_PATHS
    PRUNE_NAMES = settings.CLEANUP_PRUNE_NAMES

    return _settings_to_config_out(settings)

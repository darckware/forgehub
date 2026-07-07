"""Foundation agents routes — read vault data from filesystem.

Provides endpoints to:
- List all 8 baseline agents with their vault metadata
- Read each agent's SOUL.md
- Read each agent's sub-agents
- List skills per agent (from profile skills dir)
- Read/write agent memory (MEMORY.md)
- Read agent config (config.yaml highlights)
- Read/write any of the 6 well-known profile Markdown config files
  (SOUL.md, MEMORY.md, TOOLS.md, AGENTS.md, HEARTBEAT.md, USER.md) for
  ANY profile under /profiles, not just the 8 baseline agents -- see
  get_profile_file/update_profile_file below.
- List/edit/reset/delete `hermes cron` scheduled jobs across every
  per-profile jobs store (cron is per-profile by design, upstream issue
  #4707 -- each profile's gateway ticks its own cron/jobs.json). Reads
  prefer the most recently modified store per job and writes target the
  store the job actually lives in -- see _load_raw_jobs/list_cron_jobs/
  update_cron_job/reset_cron_job/delete_cron_job.
- List every profile's scripts/ dir -- the only place the hermes scheduler
  executes scripts from -- cross referenced against cron jobs that
  reference them, with basic existence/executable/symlink-health checks --
  see list_scripts below.
"""

import fcntl
import json
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from croniter import croniter
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/foundation", tags=["foundation"])

VAULT_DIR = Path("/foundation-agents")
PROFILES_DIR = Path("/profiles")
# Per-profile cron layout (hermes cron is per-profile by design, upstream
# issue #4707): each profile owns <profile>/cron/jobs.json (job store),
# <profile>/cron/logs/ (execution logs the scripts append themselves via
# <profile>/cron/cron_exec_log.sh -- their mtime is real execution
# evidence, independent of what jobs.json claims) and <profile>/scripts/
# (the only place the scheduler executes scripts from; symlinks resolving
# outside it are blocked). The old central dirs (/root/.hermes/crons and
# /root/.hermes/scripts, previously mounted as /hermes-cron and
# /hermes-scripts) were migrated into the athos profile on 2026-07-06 and
# removed, along with the stale central jobs.json snapshot.
# How far past next_run_at a job may be before it is considered stalled
# ("the scheduler is not actually running this") rather than merely between
# ticks. Generous enough for slow ticks/laptop resume, small enough to catch
# a dead scheduler within the same work session.
_CRON_OVERDUE_GRACE = timedelta(minutes=30)
# Every timestamp already in jobs.json (created_at, next_run_at, ...) uses
# this fixed offset (Brasília time, no DST since 2019) -- match it when we
# compute a new next_run_at on schedule edit, so it's consistent with what
# the gateway/CLI write.
_JOBS_TZ = timezone(timedelta(hours=-3))
BASELINE_AGENTS = [
    "athos",
    "atlas",
    "mnemosyne",
    "scriba",
    "themis",
    "aegis",
    "daedalus",
    "hephaestus",
]

# Allow-list for get_profile_file/update_profile_file -- these two routes
# accept an arbitrary `filename` path segment, so it must never be used to
# read/write anything outside this fixed set.
PROFILE_MARKDOWN_FILES = (
    "SOUL.md",
    "MEMORY.md",
    "TOOLS.md",
    "AGENTS.md",
    "HEARTBEAT.md",
    "USER.md",
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class SubAgentInfo(BaseModel):
    role: str
    function: str


class SkillInfo(BaseModel):
    name: str
    description: str
    category: str | None = None


class MemoryEntry(BaseModel):
    content: str


class FoundationAgentOut(BaseModel):
    profile: str
    name: str
    role: str
    layer: str
    runtime_tier: str | None = None
    mission: str | None = None
    dependencies_upstream: list[str] = []
    dependencies_downstream: list[str] = []
    sub_agents: list[SubAgentInfo] = []
    skills: list[SkillInfo] = []
    soul: str | None = None
    memory_content: str | None = None
    config_summary: dict[str, Any] | None = None


class FoundationAgentListOut(BaseModel):
    agents: list[FoundationAgentOut]


class MemoryUpdateIn(BaseModel):
    content: str


class ProfileFileOut(BaseModel):
    profile: str
    filename: str
    content: str | None = None


class ProfileFileUpdateIn(BaseModel):
    content: str


class CronJobOut(BaseModel):
    profile: str
    id: str
    name: str
    description: str | None = None
    script: str | None = None
    schedule_display: str | None = None
    enabled: bool
    state: str
    status: str
    # `status` above only reflects the enabled/paused flags; `health` says
    # whether the job is actually executing: ok | error | overdue (its
    # next_run_at is in the past -- the scheduler is not running it) |
    # never_ran | off. See _job_health.
    health: str
    next_run_at: str | None = None
    last_run_at: str | None = None
    last_status: str | None = None
    last_error: str | None = None
    # mtime of the job script's execution log under the owning profile's
    # cron/logs/ -- written by the script itself, so it is real execution
    # evidence.
    last_log_at: str | None = None
    deliver: str | None = None


class CronStoreErrorOut(BaseModel):
    """A per-profile jobs.json that failed to parse. Surfaced on the list
    endpoint instead of silently contributing zero jobs: a corrupted store
    also makes that profile's gateway refuse to tick ("Cron database
    corrupted and unrepairable"), so its jobs are not just hidden -- they
    have stopped running, and the UI must say so."""

    profile: str
    store: str
    error: str


class CronJobListOut(BaseModel):
    jobs: list[CronJobOut]
    store_errors: list[CronStoreErrorOut] = []


class CronJobUpdateIn(BaseModel):
    """Partial update -- omitted (None) fields are left unchanged."""

    name: str | None = None
    description: str | None = None  # maps to the stored "prompt" field
    schedule_display: str | None = None  # raw cron expression, e.g. "*/5 * * * *"
    deliver: str | None = None
    enabled: bool | None = None


class CronJobRefOut(BaseModel):
    """A cron job that references a given script, used to answer "which
    agent runs this and is it working" for the Scripts registry."""

    job_id: str
    job_name: str
    profile: str
    schedule_display: str | None = None
    enabled: bool
    last_status: str | None = None
    last_error: str | None = None


class ScriptOut(BaseModel):
    name: str
    location: str  # "central" or a profile slug
    agent: str  # profile slug that owns/executes this script, "—" for central
    description: str | None = None
    path: str
    exists: bool
    is_symlink: bool
    symlink_target: str | None = None
    executable: bool
    escapes_scripts_dir: bool = False
    status: str  # "ok" | "broken" | "unused"
    referenced_by: list[CronJobRefOut] = []


class ScriptListOut(BaseModel):
    scripts: list[ScriptOut]


class ScriptContentOut(BaseModel):
    content: str
    path: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_file_safe(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def _parse_vault_md(profile: str) -> dict[str, Any]:
    """Parse the vault AGENT.md for metadata."""
    vault_path = VAULT_DIR / f"{profile.upper()}.md"
    data: dict[str, Any] = {
        "profile": profile,
        "name": profile.capitalize(),
        "role": "",
        "layer": "",
        "runtime_tier": None,
        "mission": "",
        "dependencies_upstream": [],
        "dependencies_downstream": [],
    }
    content = _read_file_safe(vault_path)
    if content is None:
        return data

    # Extract fields from vault markdown
    for line in content.splitlines():
        line_stripped = line.strip()
        if line_stripped.startswith("- Role:"):
            data["role"] = line_stripped.split(":", 1)[1].strip()
        elif line_stripped.startswith("- Layer:"):
            data["layer"] = line_stripped.split(":", 1)[1].strip()
        elif line_stripped.startswith("- Runtime tier:"):
            data["runtime_tier"] = line_stripped.split(":", 1)[1].strip()
        elif line_stripped.startswith("- Nome:"):
            data["name"] = line_stripped.split(":", 1)[1].strip()

    # Extract mission section
    mission_lines = []
    in_mission = False
    for line in content.splitlines():
        if line.strip() == "## Missão":
            in_mission = True
            continue
        if in_mission:
            if line.startswith("## "):
                break
            if line.strip():
                mission_lines.append(line.strip())
    data["mission"] = " ".join(mission_lines) if mission_lines else None

    # Extract dependencies (Upstream/Downstream lines with [[AGENT]] refs)
    for line in content.splitlines():
        if line.strip().startswith("- Upstream:"):
            refs = re.findall(r"\[\[(\w+)\]\]", line)
            data["dependencies_upstream"] = refs
        elif line.strip().startswith("- Downstream:"):
            refs = re.findall(r"\[\[(\w+)\]\]", line)
            data["dependencies_downstream"] = refs

    return data


def _parse_subagents_md(profile: str) -> list[SubAgentInfo]:
    """Parse the vault SUBAGENTS.md for sub-agent list."""
    sub_path = VAULT_DIR / f"{profile.upper()}_SUBAGENTS.md"
    content = _read_file_safe(sub_path)
    if content is None:
        return []

    sub_agents: list[SubAgentInfo] = []
    # Parse markdown table rows (skip header + separator)
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("|") and not line.startswith("| Role") and not line.startswith("|-"):
            parts = [c.strip() for c in line.split("|") if c.strip()]
            if len(parts) >= 2:
                # Remove backticks from role
                role = parts[0].replace("`", "").strip()
                function = parts[1].strip()
                sub_agents.append(SubAgentInfo(role=role, function=function))
    return sub_agents


def _list_agent_skills(profile: str) -> list[SkillInfo]:
    """Scan the profile skills directory for skill metadata."""
    skills_dir = PROFILES_DIR / profile / "skills"
    if not skills_dir.is_dir():
        return []

    skills: list[SkillInfo] = []
    for category_dir in sorted(skills_dir.rglob("SKILL.md")):
        content = _read_file_safe(category_dir)
        if content is None:
            continue

        name = category_dir.parent.name
        description = ""
        category = category_dir.parent.parent.name
        if category == "skills":
            category = None

        # Parse YAML frontmatter-like description
        for line in content.splitlines():
            if line.startswith("description:"):
                desc = line.split(":", 1)[1].strip().strip('"').strip("'")
                description = desc
                break

        skills.append(SkillInfo(name=name, description=description, category=category))

    return skills


def _get_memory_path(profile: str) -> Path:
    return PROFILES_DIR / profile / "MEMORY.md"


def _get_soul_path(profile: str) -> Path:
    return PROFILES_DIR / profile / "SOUL.md"


def _job_status(enabled: bool, state: str) -> str:
    """Normalize the raw enabled/state fields jobs.json stores into one of
    the three states the UI cares about: active, paused, disabled."""
    if not enabled:
        return "disabled"
    if state == "paused":
        return "paused"
    return "active"


def _truncate_description(text: str | None) -> str | None:
    """Normalize a raw prompt into a display description.

    Deliberately does NOT truncate: this value round-trips back into
    `prompt` on PATCH /crons/{id} (see _update_cron_job) whenever the
    frontend's edit form is saved without touching the description field,
    since there is no separate get-single-job endpoint to fetch the
    untruncated prompt for editing. Truncating here previously caused
    silent, irreversible data loss on every such save. Visual truncation
    in list views belongs to the frontend (CSS `truncate`), not here.
    """
    return (text or "").strip() or None


def _cron_jobs_lock(store_file: Path):
    """Acquire the same advisory flock the `hermes` CLI/gateway use on
    <store dir>/.jobs.lock, so an edit from ForgeHub can't race a concurrent
    write from the live scheduler. Each store (central or per-profile) has
    its own lock next to its jobs.json. Returns an open file handle --
    caller must flock/unlock it."""
    store_file.parent.mkdir(parents=True, exist_ok=True)
    lock_path = store_file.parent / ".jobs.lock"
    lock_path.touch(exist_ok=True)
    return open(lock_path, "r+")


def _cron_store_files() -> list[Path]:
    """Every per-profile jobs.json store (there is no central store anymore
    -- see the per-profile layout note at the top of this module)."""
    stores: list[Path] = []
    if PROFILES_DIR.is_dir():
        for profile_dir in sorted(PROFILES_DIR.iterdir()):
            store = profile_dir / "cron" / "jobs.json"
            if store.is_file():
                stores.append(store)
    return stores


def _parse_store_jobs(store: Path) -> tuple[list[dict[str, Any]], str | None]:
    """Returns (jobs, error). A parse failure yields ([], <message>) rather
    than raising: mutation helpers skip broken stores, while the list
    endpoint reports them via CronStoreErrorOut."""
    content = _read_file_safe(store)
    if not content:
        return [], None
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return [], f"invalid JSON: {e}"
    jobs = data.get("jobs", []) if isinstance(data, dict) else data
    return ([j for j in jobs if isinstance(j, dict)] if isinstance(jobs, list) else []), None


def _cron_store_errors() -> list[CronStoreErrorOut]:
    """Per-profile stores that currently fail to parse (see
    CronStoreErrorOut for why these must be surfaced, not swallowed)."""
    errors: list[CronStoreErrorOut] = []
    for store in _cron_store_files():
        _, error = _parse_store_jobs(store)
        if error:
            errors.append(
                CronStoreErrorOut(profile=store.parent.parent.name, store=str(store), error=error)
            )
    return errors


def _load_raw_jobs() -> list[dict[str, Any]]:
    """Load all jobs from every per-profile store, deduplicated by id and
    name keeping the copy from the MOST RECENTLY MODIFIED store -- if a
    stale copy of a job ever lingers in another store (the scheduler has
    moved stores across hermes versions before), it must not shadow the
    live one. Each returned job carries its source store in "_store" so
    edit/delete/reset target the file the scheduler actually reads --
    CronJobOut never exposes that key."""
    entries: list[tuple[float, dict[str, Any]]] = []
    for store in _cron_store_files():
        try:
            mtime = store.stat().st_mtime
        except OSError:
            mtime = 0.0
        profile_default = store.parent.parent.name
        for job in _parse_store_jobs(store)[0]:
            job = dict(job)
            if not job.get("profile"):
                job["profile"] = profile_default
            job["_store"] = str(store)
            entries.append((mtime, job))

    # Newest store first; sort is stable, so within one store the original
    # order is preserved. First occurrence of an id or name wins.
    entries.sort(key=lambda entry: entry[0], reverse=True)
    jobs: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    for _, job in entries:
        job_id, job_name = job.get("id"), job.get("name")
        if (job_id and job_id in seen_ids) or (job_name and job_name in seen_names):
            continue
        if job_id:
            seen_ids.add(job_id)
        if job_name:
            seen_names.add(job_name)
        jobs.append(job)
    return jobs


def _last_log_at(script: str | None, profile: str | None) -> str | None:
    """mtime of the script's execution log under the owning profile's
    cron/logs/, if any. The scripts append to these logs themselves (via
    <profile>/cron/cron_exec_log.sh), so the mtime is direct evidence of
    the last real execution."""
    if not script or not profile:
        return None
    log_file = PROFILES_DIR / profile / "cron" / "logs" / (Path(script).stem + ".log")
    try:
        mtime = log_file.stat().st_mtime
    except OSError:
        return None
    return datetime.fromtimestamp(mtime, tz=_JOBS_TZ).isoformat()


def _job_health(
    enabled: bool,
    last_status: str | None,
    last_run_at: str | None,
    next_run_at: str | None,
    last_log_at: str | None,
) -> str:
    """Whether the job is actually executing -- unlike `status`, which only
    mirrors the enabled/paused flags (the Dashboard previously showed every
    job as "active" while the scheduler had silently stopped running them)."""
    if not enabled:
        return "off"
    if (last_status or "").lower() in ("error", "failed", "fail"):
        return "error"
    if next_run_at:
        try:
            next_run = datetime.fromisoformat(next_run_at)
        except ValueError:
            next_run = None
        if next_run is not None:
            if next_run.tzinfo is None:
                next_run = next_run.replace(tzinfo=_JOBS_TZ)
            if next_run < datetime.now(_JOBS_TZ) - _CRON_OVERDUE_GRACE:
                return "overdue"
    if not last_run_at and not last_log_at:
        return "never_ran"
    return "ok"


def _raw_job_to_out(raw_job: dict[str, Any]) -> CronJobOut:
    enabled = bool(raw_job.get("enabled", False))
    state = raw_job.get("state") or "scheduled"
    script = raw_job.get("script")
    profile = raw_job.get("profile") or "default"
    last_log = _last_log_at(script, profile)
    return CronJobOut(
        profile=profile,
        id=raw_job.get("id", ""),
        name=raw_job.get("name", ""),
        description=_truncate_description(raw_job.get("prompt")),
        script=script,
        schedule_display=(raw_job.get("schedule") or {}).get("display") or raw_job.get("schedule_display"),
        enabled=enabled,
        state=state,
        status=_job_status(enabled, state),
        health=_job_health(
            enabled,
            raw_job.get("last_status"),
            raw_job.get("last_run_at"),
            raw_job.get("next_run_at"),
            last_log,
        ),
        next_run_at=raw_job.get("next_run_at"),
        last_run_at=raw_job.get("last_run_at"),
        last_status=raw_job.get("last_status"),
        last_error=raw_job.get("last_error"),
        last_log_at=last_log,
        deliver=raw_job.get("deliver"),
    )


def _list_cron_jobs() -> list[CronJobOut]:
    """Read every profile's `hermes cron` job store (per-profile by design,
    see module docstring re #4707) and return every job."""
    jobs = [_raw_job_to_out(raw_job) for raw_job in _load_raw_jobs()]
    jobs.sort(key=lambda j: (j.profile, j.name))
    return jobs


def _atomic_write_jobs(store_file: Path, raw_jobs: list[dict[str, Any]]) -> None:
    """Caller must hold that store's .jobs.lock flock (see _cron_jobs_lock)."""
    fd, tmp_path = tempfile.mkstemp(dir=str(store_file.parent), suffix=".tmp", prefix=".jobs_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"jobs": raw_jobs}, f, indent=2)
        os.replace(tmp_path, store_file)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _find_job_store(job_id: str) -> Path | None:
    """The store file whose copy of this job is live (see _load_raw_jobs's
    freshest-store dedupe) -- the one all mutations must write to."""
    for job in _load_raw_jobs():
        if job.get("id") == job_id:
            return Path(job["_store"])
    return None


def _delete_cron_job(job_id: str) -> bool:
    """Remove a job from its live store under the same advisory lock the
    `hermes` CLI/gateway use. Returns False if the job_id wasn't found."""
    store = _find_job_store(job_id)
    if store is None:
        return False
    with _cron_jobs_lock(store) as lockf:
        fcntl.flock(lockf, fcntl.LOCK_EX)
        try:
            raw_jobs, _ = _parse_store_jobs(store)
            remaining = [j for j in raw_jobs if j.get("id") != job_id]
            if len(remaining) == len(raw_jobs):
                return False
            _atomic_write_jobs(store, remaining)
            return True
        finally:
            fcntl.flock(lockf, fcntl.LOCK_UN)


def _mutate_cron_job(job_id: str, mutate) -> CronJobOut | None:
    """Shared locate-lock-mutate-write path for update/reset: applies
    `mutate(target)` to the job's raw dict inside its live store, under
    that store's advisory lock. Returns None if the job_id wasn't found."""
    store = _find_job_store(job_id)
    if store is None:
        return None
    with _cron_jobs_lock(store) as lockf:
        fcntl.flock(lockf, fcntl.LOCK_EX)
        try:
            raw_jobs, _ = _parse_store_jobs(store)
            target = next((j for j in raw_jobs if j.get("id") == job_id), None)
            if target is None:
                return None
            mutate(target)
            _atomic_write_jobs(store, raw_jobs)
            if not target.get("profile"):
                target = {**target, "profile": store.parent.parent.name}
            return _raw_job_to_out(target)
        finally:
            fcntl.flock(lockf, fcntl.LOCK_UN)


def _update_cron_job(job_id: str, updates: CronJobUpdateIn) -> CronJobOut | None:
    """Apply a partial update to a job in its live store. Returns None if
    the job_id wasn't found. Raises ValueError if `schedule_display` is not
    a valid cron expression."""

    def mutate(target: dict[str, Any]) -> None:
        if updates.name is not None:
            target["name"] = updates.name
        if updates.description is not None:
            target["prompt"] = updates.description
        if updates.deliver is not None:
            target["deliver"] = updates.deliver
        if updates.enabled is not None:
            target["enabled"] = updates.enabled
            target["state"] = "scheduled" if updates.enabled else "paused"
            target["paused_at"] = None if updates.enabled else datetime.now(_JOBS_TZ).isoformat()
        if updates.schedule_display is not None:
            expr = updates.schedule_display.strip()
            try:
                next_run = croniter(expr, datetime.now(_JOBS_TZ)).get_next(datetime)
            except (ValueError, KeyError) as e:
                raise ValueError(f"Invalid cron expression {expr!r}: {e}") from e
            target["schedule"] = {"kind": "cron", "expr": expr, "display": expr}
            target["schedule_display"] = expr
            target["next_run_at"] = next_run.isoformat()

    return _mutate_cron_job(job_id, mutate)


def _reset_cron_job(job_id: str) -> CronJobOut | None:
    """Re-arm a job in place: clear its last error/status, force a stuck
    state back to scheduled (or paused, per its enabled flag) and recompute
    next_run_at from its cron expression when it has one. Deliberately does
    NOT touch `enabled` -- activating/deactivating stays a PUT concern
    (see _update_cron_job). Returns None if the job_id wasn't found."""

    def mutate(target: dict[str, Any]) -> None:
        enabled = bool(target.get("enabled", False))
        target["state"] = "scheduled" if enabled else "paused"
        target["last_status"] = None
        target["last_error"] = None
        expr = (target.get("schedule") or {}).get("expr") or target.get("schedule_display")
        if enabled and expr:
            try:
                next_run = croniter(expr, datetime.now(_JOBS_TZ)).get_next(datetime)
            except (ValueError, KeyError):
                # Non-cron schedules (interval kinds) keep their own
                # next_run_at -- clearing the error state is still useful.
                pass
            else:
                target["next_run_at"] = next_run.isoformat()

    return _mutate_cron_job(job_id, mutate)


# ---------------------------------------------------------------------------
# Scripts registry
# ---------------------------------------------------------------------------


def _parse_readme_descriptions() -> dict[str, str]:
    """Parse the `| script | função | cron | status |` table in each
    profile's cron/README_crons.md (athos carries the catalog migrated from
    the old central dir) for human descriptions of the scripts."""
    descriptions: dict[str, str] = {}
    if not PROFILES_DIR.is_dir():
        return descriptions
    for profile_dir in sorted(PROFILES_DIR.iterdir()):
        content = _read_file_safe(profile_dir / "cron" / "README_crons.md")
        if content is None:
            continue
        for line in content.splitlines():
            line = line.strip()
            if not line.startswith("|") or line.startswith("|--") or line.startswith("| Script"):
                continue
            parts = [c.strip() for c in line.split("|") if c.strip()]
            if len(parts) >= 2:
                name = parts[0].replace("`", "").strip()
                descriptions.setdefault(name, parts[1])
    return descriptions


_DOCSTRING_RE = re.compile(r'^\s*(?:"""|\'\'\')(.*?)(?:"""|\'\'\')', re.DOTALL)


def _extract_script_doc(path: Path) -> str | None:
    """Best-effort "what does this script do" for scripts with no
    README_crons.md entry: a Python module docstring, or the leading
    `#`-comment block (after the shebang) for shell/Python alike."""
    content = _read_file_safe(path)
    if content is None:
        return None

    if path.suffix == ".py":
        body = content
        if body.startswith("#!"):
            body = body.split("\n", 1)[1] if "\n" in body else ""
        match = _DOCSTRING_RE.match(body.lstrip())
        if match:
            doc = " ".join(match.group(1).split())
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


def _script_is_real_file(path: Path) -> bool:
    """Match by name/extension, not `Path.is_file()` -- that follows
    symlinks, and a symlink whose target is an absolute host path (see
    _HOST_PATH_REMAPS below) can't be stat'd from inside this container,
    making is_file() return False even for perfectly valid script
    symlinks. Broken/escaping symlinks still need to show up in the
    registry as "broken", not be silently filtered out here."""
    if path.name.startswith(".") or path.suffix not in (".sh", ".py", ".bash"):
        return False
    return path.is_symlink() or path.is_file()


# Symlinks under a profile's scripts/ dir store their target as the
# absolute path on the HOST, since that's how they were created outside
# this container. This container doesn't mount the host filesystem 1:1 --
# only specific dirs, at different container-side paths (PROFILES_DIR <-
# /root/.hermes/profiles) -- so a raw os.readlink() target can't be opened
# directly here. Translate the known host prefixes to their container-side
# mount before checking existence. Targets under the removed central dirs
# (/root/.hermes/crons, /root/.hermes/scripts) no longer remap -- such a
# symlink is genuinely broken now and should show as "broken".
_HOST_PATH_REMAPS = (
    ("/root/.hermes/profiles/", PROFILES_DIR),
)


def _remap_host_symlink_target(raw_target: str) -> Path | None:
    for prefix, container_dir in _HOST_PATH_REMAPS:
        if raw_target.startswith(prefix):
            return container_dir / raw_target[len(prefix):]
    return None


def _build_script_out(
    *,
    name: str,
    location: str,
    agent: str,
    path: Path,
    host_scripts_dir: str,
    description: str | None,
    jobs_by_script: dict[str, list[CronJobOut]],
) -> ScriptOut:
    is_symlink = path.is_symlink()
    symlink_target: str | None = None
    escapes_scripts_dir = False
    exists: bool

    if is_symlink:
        try:
            raw_target = os.readlink(path)
        except OSError:
            raw_target = None

        if raw_target and os.path.isabs(raw_target):
            symlink_target = raw_target
            escapes_scripts_dir = os.path.dirname(raw_target) != host_scripts_dir
            remapped = _remap_host_symlink_target(raw_target)
            exists = remapped.exists() if remapped is not None else False
        elif raw_target:
            resolved = (path.parent / raw_target).resolve()
            symlink_target = str(resolved)
            escapes_scripts_dir = str(resolved.parent) != str(path.parent.resolve())
            exists = resolved.exists()
        else:
            exists = False
    else:
        exists = path.exists()

    executable = exists and os.access(path, os.X_OK)
    refs = jobs_by_script.get(name, [])

    if not exists or escapes_scripts_dir:
        status = "broken"
    elif not refs:
        status = "unused"
    else:
        status = "ok"

    return ScriptOut(
        name=name,
        location=location,
        agent=agent,
        description=description,
        path=str(path),
        exists=exists,
        is_symlink=is_symlink,
        symlink_target=symlink_target,
        executable=executable,
        escapes_scripts_dir=escapes_scripts_dir,
        status=status,
        referenced_by=[
            CronJobRefOut(
                job_id=j.id,
                job_name=j.name,
                profile=j.profile,
                schedule_display=j.schedule_display,
                enabled=j.enabled,
                last_status=j.last_status,
                last_error=j.last_error,
            )
            for j in refs
        ],
    )


def _list_scripts() -> list[ScriptOut]:
    """List every profile's scripts/ dir (the only place the scheduler
    executes scripts from -- the old central catalog was migrated into the
    athos profile on 2026-07-06), cross-referenced with the cron jobs that
    invoke them by filename."""
    jobs = _list_cron_jobs()
    jobs_by_script: dict[str, list[CronJobOut]] = {}
    for job in jobs:
        if job.script:
            jobs_by_script.setdefault(job.script, []).append(job)

    descriptions = _parse_readme_descriptions()
    scripts: list[ScriptOut] = []

    if PROFILES_DIR.is_dir():
        for profile_dir in sorted(PROFILES_DIR.iterdir()):
            scripts_dir = profile_dir / "scripts"
            if not scripts_dir.is_dir():
                continue
            for entry in sorted(scripts_dir.iterdir()):
                if entry.is_dir() or not _script_is_real_file(entry):
                    continue
                scripts.append(
                    _build_script_out(
                        name=entry.name,
                        location=profile_dir.name,
                        agent=profile_dir.name,
                        path=entry,
                        host_scripts_dir=f"/root/.hermes/profiles/{profile_dir.name}/scripts",
                        description=descriptions.get(entry.name) or _extract_script_doc(entry),
                        jobs_by_script=jobs_by_script,
                    )
                )

    # Jobs that reference a script filename not found in any profile's
    # scripts dir -- surfaces the "missing script" case explicitly instead
    # of letting it silently vanish from the registry.
    all_seen_names = {s.name for s in scripts}
    for script_name, refs in jobs_by_script.items():
        if script_name in all_seen_names:
            continue
        for ref_job in refs:
            scripts.append(
                _build_script_out(
                    name=script_name,
                    location=ref_job.profile,
                    agent=ref_job.profile,
                    path=PROFILES_DIR / ref_job.profile / "scripts" / script_name,
                    host_scripts_dir=f"/root/.hermes/profiles/{ref_job.profile}/scripts",
                    description=None,
                    jobs_by_script=jobs_by_script,
                )
            )
        all_seen_names.add(script_name)

    scripts.sort(key=lambda s: (s.location, s.name))
    return scripts


def _resolve_script_read_path(location: str, name: str) -> Path | None:
    """Resolve a script's actual readable path for content display, same
    symlink-remap logic as _build_script_out. Returns None if unreadable.

    `location` is normally a profile name. The legacy values "central",
    "main" and "profile" (pre-2026-07-06 central-dirs layout, still present
    in old cron_scripts DB rows and frontend fallback candidates) resolve
    by searching every profile's scripts dir for the name instead."""
    if location in ("central", "main", "profile"):
        bases = (
            [p / "scripts" for p in sorted(PROFILES_DIR.iterdir()) if (p / "scripts").is_dir()]
            if PROFILES_DIR.is_dir()
            else []
        )
    else:
        bases = [PROFILES_DIR / location / "scripts"]

    for base in bases:
        candidate = base / name
        if candidate.is_symlink():
            try:
                raw_target = os.readlink(candidate)
            except OSError:
                continue
            if os.path.isabs(raw_target):
                remapped = _remap_host_symlink_target(raw_target)
                if remapped is not None and remapped.is_file():
                    return remapped
                continue
            resolved = (candidate.parent / raw_target).resolve()
            if resolved.is_file():
                return resolved
            continue
        if candidate.is_file():
            return candidate
    return None


def _get_profile_dir_or_404(profile: str) -> Path:
    """Resolve a profile directory, rejecting anything that isn't a plain
    lowercase-alphanumeric/hyphen slug (blocks path traversal via the
    `profile` path segment, e.g. "../../etc") and anything that doesn't
    exist on disk."""
    if not re.fullmatch(r"[a-z0-9-]+", profile):
        raise HTTPException(status_code=404, detail="Profile not found")
    profile_dir = PROFILES_DIR / profile
    if not profile_dir.is_dir():
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile_dir


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/agents", response_model=FoundationAgentListOut)
async def list_foundation_agents() -> FoundationAgentListOut:
    """List all 8 baseline agents with vault metadata, skills, and sub-agents."""
    agents: list[FoundationAgentOut] = []
    for profile in BASELINE_AGENTS:
        vault_data = _parse_vault_md(profile)
        sub_agents = _parse_subagents_md(profile)
        skills = _list_agent_skills(profile)
        soul_content = _read_file_safe(_get_soul_path(profile))
        memory_content = _read_file_safe(_get_memory_path(profile))

        agents.append(
            FoundationAgentOut(
                profile=profile,
                name=vault_data["name"],
                role=vault_data["role"],
                layer=vault_data["layer"],
                runtime_tier=vault_data["runtime_tier"],
                mission=vault_data["mission"],
                dependencies_upstream=vault_data["dependencies_upstream"],
                dependencies_downstream=vault_data["dependencies_downstream"],
                sub_agents=sub_agents,
                skills=skills,
                soul=soul_content,
                memory_content=memory_content,
            )
        )

    return FoundationAgentListOut(agents=agents)


@router.get("/agents/{profile}", response_model=FoundationAgentOut)
async def get_foundation_agent(profile: str) -> FoundationAgentOut:
    """Get a single Foundation agent's full data."""
    if profile.lower() not in BASELINE_AGENTS:
        raise HTTPException(status_code=404, detail="Agent not found in baseline")

    profile = profile.lower()
    vault_data = _parse_vault_md(profile)
    sub_agents = _parse_subagents_md(profile)
    skills = _list_agent_skills(profile)
    soul_content = _read_file_safe(_get_soul_path(profile))
    memory_content = _read_file_safe(_get_memory_path(profile))

    return FoundationAgentOut(
        profile=profile,
        name=vault_data["name"],
        role=vault_data["role"],
        layer=vault_data["layer"],
        runtime_tier=vault_data["runtime_tier"],
        mission=vault_data["mission"],
        dependencies_upstream=vault_data["dependencies_upstream"],
        dependencies_downstream=vault_data["dependencies_downstream"],
        sub_agents=sub_agents,
        skills=skills,
        soul=soul_content,
        memory_content=memory_content,
    )


@router.get("/agents/{profile}/soul")
async def get_agent_soul(profile: str) -> dict[str, str]:
    """Get the SOUL.md content for a given agent."""
    if profile.lower() not in BASELINE_AGENTS:
        raise HTTPException(status_code=404, detail="Agent not found in baseline")

    content = _read_file_safe(_get_soul_path(profile.lower()))
    if content is None:
        raise HTTPException(status_code=404, detail="SOUL.md not found")
    return {"profile": profile, "soul": content}


@router.put("/agents/{profile}/memory")
async def update_agent_memory(profile: str, payload: MemoryUpdateIn) -> dict[str, str]:
    """Write updated content to an agent's MEMORY.md file."""
    if profile.lower() not in BASELINE_AGENTS:
        raise HTTPException(status_code=404, detail="Agent not found in baseline")

    profile = profile.lower()
    memory_path = _get_memory_path(profile)

    try:
        memory_path.write_text(payload.content, encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write MEMORY.md: {e}") from e

    return {"profile": profile, "status": "updated", "path": str(memory_path)}


@router.get("/agents/{profile}/memory")
async def get_agent_memory(profile: str) -> dict[str, str | None]:
    """Read an agent's MEMORY.md content."""
    if profile.lower() not in BASELINE_AGENTS:
        raise HTTPException(status_code=404, detail="Agent not found in baseline")

    content = _read_file_safe(_get_memory_path(profile.lower()))
    return {"profile": profile, "memory": content}


class SkillContentOut(BaseModel):
    """Source SKILL.md of a registered skill, resolved from the profile
    skills trees (the same files hermes_sync registers skills from)."""

    name: str
    profile: str
    path: str  # host-side path, for display
    content: str


class SkillContentUpdateIn(BaseModel):
    content: str


def _find_skill_md(name: str) -> tuple[str, Path, str] | None:
    """Find a skill's SKILL.md across every profile's skills/ tree,
    matching the frontmatter `name:` or the skill's directory name -- the
    same fallback hermes_sync uses when registering skills. No path is
    built from the input (we only compare names against scanned files),
    so there is no traversal surface. Returns (profile, path, content)."""
    target = name.strip().lower()
    if not target or not PROFILES_DIR.is_dir():
        return None
    for profile_dir in sorted(PROFILES_DIR.iterdir()):
        skills_dir = profile_dir / "skills"
        if not skills_dir.is_dir():
            continue
        for skill_md in sorted(skills_dir.rglob("SKILL.md")):
            content = _read_file_safe(skill_md)
            if content is None:
                continue
            candidates = {skill_md.parent.name.lower()}
            for line in content.splitlines():
                if line.startswith("name:"):
                    candidates.add(line.split(":", 1)[1].strip().strip('"').strip("'").lower())
                    break
            if target in candidates:
                return profile_dir.name, skill_md, content
    return None


def _skill_content_out(name: str, profile: str, skill_md: Path, content: str) -> SkillContentOut:
    host_path = str(skill_md).replace(str(PROFILES_DIR), "/root/.hermes/profiles", 1)
    return SkillContentOut(name=name, profile=profile, path=host_path, content=content)


@router.get("/skills/{name}/content", response_model=SkillContentOut)
async def get_skill_content(name: str) -> SkillContentOut:
    """Source SKILL.md of a registered skill (see _find_skill_md)."""
    found = _find_skill_md(name)
    if found is None:
        raise HTTPException(status_code=404, detail="SKILL.md not found for this skill")
    profile, skill_md, content = found
    return _skill_content_out(name, profile, skill_md, content)


@router.put("/skills/{name}/content", response_model=SkillContentOut)
async def update_skill_content(name: str, payload: SkillContentUpdateIn) -> SkillContentOut:
    """Overwrite a skill's SKILL.md in the owning profile's skills tree
    (atomic tmp+rename). Only the file is written -- the DB skill row keeps
    its synced metadata until the next Hermes Foundation sync re-imports
    the frontmatter."""
    found = _find_skill_md(name)
    if found is None:
        raise HTTPException(status_code=404, detail="SKILL.md not found for this skill")
    profile, skill_md, _ = found
    fd, tmp_path = tempfile.mkstemp(dir=str(skill_md.parent), suffix=".tmp", prefix=".skill_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload.content)
        os.replace(tmp_path, skill_md)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return _skill_content_out(name, profile, skill_md, payload.content)


@router.get("/agents/{profile}/skills")
async def get_agent_skills(profile: str) -> list[SkillInfo]:
    """List all skills for a given agent profile."""
    if profile.lower() not in BASELINE_AGENTS:
        raise HTTPException(status_code=404, detail="Agent not found in baseline")

    return _list_agent_skills(profile.lower())


@router.get("/agents/{profile}/subagents")
async def get_agent_subagents(profile: str) -> list[SubAgentInfo]:
    """List all sub-agents for a given agent profile."""
    if profile.lower() not in BASELINE_AGENTS:
        raise HTTPException(status_code=404, detail="Agent not found in baseline")

    return _parse_subagents_md(profile.lower())


# ---------------------------------------------------------------------------
# Generic profile Markdown files (any profile under /profiles, not just
# the 8 baseline agents -- used by the Agent detail page's profile-file
# tabs in ForgeHub).
# ---------------------------------------------------------------------------


@router.get("/profiles/{profile}/files/{filename}", response_model=ProfileFileOut)
async def get_profile_file(profile: str, filename: str) -> ProfileFileOut:
    """Read one of a profile's well-known Markdown config files. `filename`
    is checked against PROFILE_MARKDOWN_FILES -- this must never be used
    to read arbitrary files from a profile directory."""
    if filename not in PROFILE_MARKDOWN_FILES:
        raise HTTPException(status_code=404, detail="Unknown profile file")
    profile_dir = _get_profile_dir_or_404(profile.lower())
    content = _read_file_safe(profile_dir / filename)
    return ProfileFileOut(profile=profile.lower(), filename=filename, content=content)


@router.put("/profiles/{profile}/files/{filename}", response_model=ProfileFileOut)
async def update_profile_file(
    profile: str, filename: str, payload: ProfileFileUpdateIn
) -> ProfileFileOut:
    """Write one of a profile's well-known Markdown config files. Same
    allow-list restriction as get_profile_file."""
    if filename not in PROFILE_MARKDOWN_FILES:
        raise HTTPException(status_code=404, detail="Unknown profile file")
    profile_dir = _get_profile_dir_or_404(profile.lower())
    path = profile_dir / filename
    try:
        path.write_text(payload.content, encoding="utf-8")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to write {filename}: {e}") from e
    return ProfileFileOut(profile=profile.lower(), filename=filename, content=payload.content)


# ---------------------------------------------------------------------------
# Cron jobs (per-profile `hermes cron` job stores -- see module docstring
# re #4707)
# ---------------------------------------------------------------------------


@router.get("/crons", response_model=CronJobListOut)
async def list_cron_jobs() -> CronJobListOut:
    """List every scheduled `hermes cron` job, with its description,
    schedule, owning profile, and active/paused/disabled status. Stores
    that fail to parse are reported in `store_errors` -- a corrupted store
    means that profile's scheduler has stopped running its jobs entirely."""
    return CronJobListOut(jobs=_list_cron_jobs(), store_errors=_cron_store_errors())


@router.put("/crons/{job_id}", response_model=CronJobOut)
async def update_cron_job(job_id: str, payload: CronJobUpdateIn) -> CronJobOut:
    """Apply a partial edit (name/description/schedule/deliver/enabled) to
    a job in the shared cron store, under the same advisory lock the
    `hermes` CLI/gateway use."""
    try:
        updated = _update_cron_job(job_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if updated is None:
        raise HTTPException(status_code=404, detail="Cron job not found")
    return updated


@router.post("/crons/{job_id}/reset", response_model=CronJobOut)
async def reset_cron_job(job_id: str) -> CronJobOut:
    """Re-arm a job: clear its last error/status and recompute its next run
    from the schedule, without changing whether it is enabled. Backs the
    reset action on the Crons page and Dashboard card."""
    reset = _reset_cron_job(job_id)
    if reset is None:
        raise HTTPException(status_code=404, detail="Cron job not found")
    return reset


@router.delete("/crons/{job_id}")
async def delete_cron_job(job_id: str) -> dict[str, str]:
    """Remove a job from the shared cron store, under the same advisory
    lock the `hermes` CLI/gateway use, so this can't race a concurrent
    scheduler write."""
    if not _delete_cron_job(job_id):
        raise HTTPException(status_code=404, detail="Cron job not found")
    return {"id": job_id, "status": "deleted"}


# ---------------------------------------------------------------------------
# Scripts registry
# ---------------------------------------------------------------------------


@router.get("/scripts", response_model=ScriptListOut)
async def list_scripts() -> ScriptListOut:
    """List the central scripts catalog plus every profile's own scripts/
    dir, each with its owning agent, description, and a health check
    (exists / symlink escapes its scripts dir / referenced by a cron job)."""
    return ScriptListOut(scripts=_list_scripts())


@router.get("/scripts/{location}/{name}/content", response_model=ScriptContentOut)
async def get_script_content(location: str, name: str) -> ScriptContentOut:
    """Read a script's raw source -- used by the Crons/Scripts pages' file
    viewer and "send to chat" actions. `location` is "central" or a profile
    slug; `name` must be a bare filename (no path separators)."""
    if "/" in name or "\\" in name or name in (".", ".."):
        raise HTTPException(status_code=400, detail="Invalid script name")
    if location != "central":
        _get_profile_dir_or_404(location)

    resolved = _resolve_script_read_path(location, name)
    if resolved is None:
        raise HTTPException(status_code=404, detail="Script file not found or unreadable")

    content = _read_file_safe(resolved)
    if content is None:
        raise HTTPException(status_code=404, detail="Script file not found or unreadable")
    return ScriptContentOut(content=content, path=str(resolved))

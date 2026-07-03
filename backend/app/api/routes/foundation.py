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
- List/edit/delete `hermes cron` scheduled jobs from the shared cron
  store (jobs.json under /hermes-cron -- the same file the `hermes` CLI
  and gateway scheduler read/write since jobs were unified into one root
  store, see upstream issue #32091) -- see list_cron_jobs/update_cron_job/
  delete_cron_job.
- List the central scripts catalog (/hermes-cron's real script files,
  the single source of truth symlinked into every profile's
  ~/.hermes/scripts/) plus each profile's own scripts/ dir, cross
  referenced against cron jobs that reference them, with basic
  existence/executable/symlink-health checks -- see list_scripts below.
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
CRON_SHARED_DIR = Path("/hermes-cron")
CRON_JOBS_FILE = CRON_SHARED_DIR / "jobs.json"
CRON_README = CRON_SHARED_DIR / "README_crons.md"
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
    next_run_at: str | None = None
    last_run_at: str | None = None
    last_status: str | None = None
    last_error: str | None = None
    deliver: str | None = None


class CronJobListOut(BaseModel):
    jobs: list[CronJobOut]


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


def _cron_jobs_lock():
    """Acquire the same advisory flock the `hermes` CLI/gateway use on
    <cron dir>/.jobs.lock, so a delete from ForgeHub can't race a concurrent
    write from the live scheduler. Returns an open file handle -- caller
    must flock/unlock it (use as a context manager via contextlib if more
    call sites need this; only delete_cron_job does today)."""
    CRON_SHARED_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = CRON_SHARED_DIR / ".jobs.lock"
    lock_path.touch(exist_ok=True)
    return open(lock_path, "r+")


def _load_raw_jobs() -> list[dict[str, Any]]:
    """Load all jobs: central store first, then per-profile cron/jobs.json
    files for any jobs not already present (deduplicated by id and name).
    Jobs that were never migrated to the shared store (#32091) still appear
    this way; edit/delete operations continue to target the central store only."""
    central_jobs: list[dict[str, Any]] = []
    content = _read_file_safe(CRON_JOBS_FILE)
    if content:
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                central_jobs = data.get("jobs", [])
            elif isinstance(data, list):
                central_jobs = list(data)
        except json.JSONDecodeError:
            pass

    central_ids: set[str] = {j["id"] for j in central_jobs if j.get("id")}
    central_names: set[str] = {j["name"] for j in central_jobs if j.get("name")}

    extra_jobs: list[dict[str, Any]] = []
    if PROFILES_DIR.is_dir():
        for profile_dir in sorted(PROFILES_DIR.iterdir()):
            profile_cron_file = profile_dir / "cron" / "jobs.json"
            pcontent = _read_file_safe(profile_cron_file)
            if not pcontent:
                continue
            try:
                pdata = json.loads(pcontent)
                pjobs: list[dict[str, Any]] = (
                    pdata.get("jobs", pdata) if isinstance(pdata, dict) else pdata
                )
                if not isinstance(pjobs, list):
                    continue
            except json.JSONDecodeError:
                continue
            for pjob in pjobs:
                pid = pjob.get("id")
                pname = pjob.get("name")
                if (pid and pid in central_ids) or (pname and pname in central_names):
                    continue
                pjob = dict(pjob)
                if not pjob.get("profile"):
                    pjob["profile"] = profile_dir.name
                extra_jobs.append(pjob)
                if pid:
                    central_ids.add(pid)
                if pname:
                    central_names.add(pname)

    return central_jobs + extra_jobs


def _raw_job_to_out(raw_job: dict[str, Any]) -> CronJobOut:
    enabled = bool(raw_job.get("enabled", False))
    state = raw_job.get("state") or "scheduled"
    return CronJobOut(
        profile=raw_job.get("profile") or "default",
        id=raw_job.get("id", ""),
        name=raw_job.get("name", ""),
        description=_truncate_description(raw_job.get("prompt")),
        script=raw_job.get("script"),
        schedule_display=(raw_job.get("schedule") or {}).get("display") or raw_job.get("schedule_display"),
        enabled=enabled,
        state=state,
        status=_job_status(enabled, state),
        next_run_at=raw_job.get("next_run_at"),
        last_run_at=raw_job.get("last_run_at"),
        last_status=raw_job.get("last_status"),
        last_error=raw_job.get("last_error"),
        deliver=raw_job.get("deliver"),
    )


def _list_cron_jobs() -> list[CronJobOut]:
    """Read the shared `hermes cron` job store (jobs.json under
    /hermes-cron -- see module docstring re #32091) and return every job."""
    jobs = [_raw_job_to_out(raw_job) for raw_job in _load_raw_jobs()]
    jobs.sort(key=lambda j: (j.profile, j.name))
    return jobs


def _atomic_write_jobs(raw_jobs: list[dict[str, Any]]) -> None:
    """Caller must hold the .jobs.lock flock (see _cron_jobs_lock)."""
    fd, tmp_path = tempfile.mkstemp(dir=str(CRON_JOBS_FILE.parent), suffix=".tmp", prefix=".jobs_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"jobs": raw_jobs}, f, indent=2)
        os.replace(tmp_path, CRON_JOBS_FILE)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _delete_cron_job(job_id: str) -> bool:
    """Remove a job from the shared store under the same advisory lock the
    `hermes` CLI/gateway use. Returns False if the job_id wasn't found."""
    with _cron_jobs_lock() as lockf:
        fcntl.flock(lockf, fcntl.LOCK_EX)
        try:
            raw_jobs = _load_raw_jobs()
            remaining = [j for j in raw_jobs if j.get("id") != job_id]
            if len(remaining) == len(raw_jobs):
                return False
            _atomic_write_jobs(remaining)
            return True
        finally:
            fcntl.flock(lockf, fcntl.LOCK_UN)


def _update_cron_job(job_id: str, updates: CronJobUpdateIn) -> CronJobOut | None:
    """Apply a partial update to a job in the shared store under the same
    advisory lock the `hermes` CLI/gateway use. Returns None if the job_id
    wasn't found. Raises ValueError if `schedule_display` is not a valid
    cron expression."""
    with _cron_jobs_lock() as lockf:
        fcntl.flock(lockf, fcntl.LOCK_EX)
        try:
            raw_jobs = _load_raw_jobs()
            target = next((j for j in raw_jobs if j.get("id") == job_id), None)
            if target is None:
                return None

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

            _atomic_write_jobs(raw_jobs)
            return _raw_job_to_out(target)
        finally:
            fcntl.flock(lockf, fcntl.LOCK_UN)


# ---------------------------------------------------------------------------
# Scripts registry
# ---------------------------------------------------------------------------

_CRON_DIR_SKIP_NAMES = {"jobs.json", "README_crons.md", ".jobs.lock", ".tick.lock"}


def _parse_readme_descriptions() -> dict[str, str]:
    """Parse the `| script | função | cron | status |` table in
    README_crons.md for human descriptions of the central scripts."""
    content = _read_file_safe(CRON_README)
    if content is None:
        return {}
    descriptions: dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line.startswith("|") or line.startswith("|--") or line.startswith("| Script"):
            continue
        parts = [c.strip() for c in line.split("|") if c.strip()]
        if len(parts) >= 2:
            name = parts[0].replace("`", "").strip()
            descriptions[name] = parts[1]
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
# absolute path on the HOST (e.g. "/root/.hermes/cron/x.sh"), since that's
# how they were created outside this container. This container doesn't
# mount the host filesystem 1:1 -- only specific dirs, at different
# container-side paths (PROFILES_DIR <- /root/.hermes/profiles,
# CRON_SHARED_DIR <- /root/.hermes/cron) -- so a raw os.readlink() target
# can't be opened directly here. Translate the known host prefixes to
# their container-side mount before checking existence.
_HOST_PATH_REMAPS = (
    ("/root/.hermes/cron/", CRON_SHARED_DIR),
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
    """Combine the central scripts catalog (/hermes-cron's real script
    files -- single source of truth for every profile's ~/.hermes/scripts/
    symlinks) with each profile's own scripts/ dir, cross-referenced with
    the cron jobs (shared store) that invoke them by filename."""
    jobs = _list_cron_jobs()
    jobs_by_script: dict[str, list[CronJobOut]] = {}
    for job in jobs:
        if job.script:
            jobs_by_script.setdefault(job.script, []).append(job)

    descriptions = _parse_readme_descriptions()
    scripts: list[ScriptOut] = []
    seen_central: set[str] = set()

    if CRON_SHARED_DIR.is_dir():
        for entry in sorted(CRON_SHARED_DIR.iterdir()):
            if entry.name in _CRON_DIR_SKIP_NAMES or entry.name.startswith("."):
                continue
            if entry.is_dir():
                continue
            if not _script_is_real_file(entry):
                continue
            seen_central.add(entry.name)
            scripts.append(
                _build_script_out(
                    name=entry.name,
                    location="central",
                    agent="—",
                    path=entry,
                    host_scripts_dir="/root/.hermes/cron",
                    description=descriptions.get(entry.name) or _extract_script_doc(entry),
                    jobs_by_script=jobs_by_script,
                )
            )

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

    # Jobs that reference a script filename not found in any scanned
    # location (central or profile) -- surfaces the "missing script" case
    # explicitly instead of letting it silently vanish from the registry.
    all_seen_names = seen_central | {s.name for s in scripts}
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

    scripts.sort(key=lambda s: (s.location != "central", s.location, s.name))
    return scripts


HERMES_SCRIPTS_DIR = Path("/hermes-scripts")


def _resolve_script_read_path(location: str, name: str) -> Path | None:
    """Resolve a script's actual readable path for content display, same
    symlink-remap logic as _build_script_out (a profile-owned script can be
    a symlink whose absolute host target -- e.g. /root/.hermes/cron/x.sh --
    isn't directly reachable from inside this container, only via the
    CRON_SHARED_DIR/PROFILES_DIR mounts). Returns None if unreadable.

    location "main" → /hermes-scripts (added alongside the DB-backed
    cron_scripts registry, see api/routes/cron_scripts.py)."""
    if location == "central":
        base = CRON_SHARED_DIR
    elif location == "main":
        base = HERMES_SCRIPTS_DIR
    else:
        base = PROFILES_DIR / location / "scripts"
    candidate = base / name

    if candidate.is_symlink():
        try:
            raw_target = os.readlink(candidate)
        except OSError:
            return None
        if os.path.isabs(raw_target):
            remapped = _remap_host_symlink_target(raw_target)
            return remapped if remapped is not None and remapped.is_file() else None
        resolved = (candidate.parent / raw_target).resolve()
        return resolved if resolved.is_file() else None

    return candidate if candidate.is_file() else None


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
# Cron jobs (shared `hermes cron` job store -- see module docstring re #32091)
# ---------------------------------------------------------------------------


@router.get("/crons", response_model=CronJobListOut)
async def list_cron_jobs() -> CronJobListOut:
    """List every scheduled `hermes cron` job, with its description,
    schedule, owning profile, and active/paused/disabled status."""
    return CronJobListOut(jobs=_list_cron_jobs())


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

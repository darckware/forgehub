"""Per-agent profile Markdown files (SOUL.md, IDENTITY.md, TOOLS.md, ...).

Every agent in the ecosystem -- Hermes profile agents and external CLI
runtimes alike -- is defined by the same small set of Markdown files living
in its own home directory. What differs is *where* that directory is:

    runtime_type   home directory
    -----------    --------------------------------------
    hermes         /root/.hermes/profiles/<profile_slug>
    claude         /root/.claude                  (Porthos)
    codex          /root/.codex                   (Aramis)
    agy            /root/.gemini/config           (Dartan)
    openclaw       /root/.openclaw/workspace      (Vector)

Those four external paths are *defaults*, not hardcoded truth: `Agent.home_path`
overrides them, so a runtime that moves its config (or a second agent on the
same runtime) is a field edit rather than a code change. Until 2026-07-26 the
only reader of profile files was foundation.py's /profiles/{profile}/files/...,
which walks the /profiles mount and therefore could only ever see the eight
Hermes profiles -- the four external agents had no way to show their own
identity files in ForgeHub at all.

Container vs host paths
-----------------------
`home_path` is always stored as the *host* canonical path (same convention as
`Agent.source_path`), because that is what an operator reads and what the
Foundation docs cite. `resolve_home_dir` then tries, in order:

  1. the host path as-is  -- true under ./dev.sh, where uvicorn runs on the host;
  2. the named bind mount -- /root/.hermes/profiles is mounted at /profiles;
  3. /host-root/<path>    -- docker-compose.yml already bind-mounts the whole
                             host filesystem at /host-root for the Docs domain,
                             which is what makes the four external runtime
                             homes reachable without adding new mounts.

Nothing is guessed: a directory is only used if it actually exists.

Path safety
-----------
`filename` arrives from a URL path segment, so it is checked against the
per-agent allow-list built by `allowed_filenames()` and the resolved file is
required to sit directly inside the resolved home directory. This module must
never be able to read or write anything outside that directory.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# The canonical profile file set, in the order an operator provisions them:
# soul first (what the agent is), then identity/user/tools, then the shared
# bootstrap/link files, then the operational ones. CONTINUITY.md is generated
# by the agent's own memory adapter on first run, so it is routinely absent.
CORE_PROFILE_FILES: tuple[str, ...] = (
    "SOUL.md",
    "IDENTITY.md",
    "USER.md",
    "TOOLS.md",
    "AGENTS.md",
    "FOUNDATION_LINK.md",
    "HEARTBEAT.md",
    "MEMORY.md",
    "CONTINUITY.md",
)

# Files that only exist for a given runtime, appended after CORE_PROFILE_FILES.
# Claude Code reads /root/.claude/CLAUDE.md as its native always-loaded
# entrypoint -- the same role AGENTS.md plays for Codex -- so Porthos' home
# has both and the UI must expose it.
RUNTIME_EXTRA_FILES: dict[str, tuple[str, ...]] = {
    "claude": ("CLAUDE.md",),
}

# Default home directory per runtime_type for agents that are not Hermes
# profiles. Sourced from each agent's canonical Foundation contract
# (/root/.hermes/foundation/agents/{PORTHOS,ARAMIS,DARTAN,VECTOR}.md).
RUNTIME_DEFAULT_HOMES: dict[str, str] = {
    "claude": "/root/.claude",
    "codex": "/root/.codex",
    "agy": "/root/.gemini/config",
    "openclaw": "/root/.openclaw/workspace",
}

HERMES_PROFILES_ROOT = "/root/.hermes/profiles"

# Host prefix -> container prefix for the named bind mounts, longest prefix
# wins. Must stay in sync with docker-compose.yml's backend volumes.
HOST_PATH_MOUNTS: tuple[tuple[str, str], ...] = (
    (HERMES_PROFILES_ROOT, "/profiles"),
)

# Catch-all mount of the whole host filesystem (docker-compose.yml: `/:/host-root`).
# It is what makes the external runtime homes -- /root/.claude, /root/.codex,
# /root/.gemini/config, /root/.openclaw/workspace -- readable from the
# container without a bind mount per runtime.
HOST_ROOT_MOUNT = "/host-root"


@dataclass(frozen=True)
class ProfileFileInfo:
    filename: str
    path: str
    exists: bool
    size: int | None
    modified_at: datetime | None


def default_home_path(runtime_type: str | None, profile_slug: str | None) -> str | None:
    """The conventional home directory for an agent, ignoring any explicit
    `home_path` override. Returns None when the agent is neither a Hermes
    profile nor a known external runtime -- a manually created agent with no
    filesystem presence has no profile files, and that is not an error."""
    if runtime_type and runtime_type in RUNTIME_DEFAULT_HOMES:
        return RUNTIME_DEFAULT_HOMES[runtime_type]
    if profile_slug:
        return f"{HERMES_PROFILES_ROOT}/{profile_slug}"
    return None


def effective_home_path(
    home_path: str | None, runtime_type: str | None, profile_slug: str | None
) -> str | None:
    """The home directory actually used: the registered override if set,
    otherwise the runtime convention."""
    if home_path and home_path.strip():
        return home_path.strip().rstrip("/") or "/"
    return default_home_path(runtime_type, profile_slug)


def container_path(host_path: str) -> str | None:
    """Translate a host path to the equivalent path inside the backend
    container via HOST_PATH_MOUNTS. None when no mount covers it."""
    normalized = host_path.rstrip("/") or "/"
    for host_prefix, mounted in sorted(
        HOST_PATH_MOUNTS, key=lambda pair: len(pair[0]), reverse=True
    ):
        if normalized == host_prefix:
            return mounted
        if normalized.startswith(host_prefix + "/"):
            return mounted + normalized[len(host_prefix) :]
    return None


def resolve_home_dir(host_path: str | None) -> Path | None:
    """Resolve a host home path to a directory readable from this process,
    trying the host path itself first (./dev.sh runs uvicorn on the host) and
    then the container mount. None when neither exists."""
    if not host_path:
        return None
    candidates = [Path(host_path)]
    mapped = container_path(host_path)
    if mapped:
        candidates.append(Path(mapped))
    candidates.append(Path(HOST_ROOT_MOUNT + "/" + host_path.lstrip("/")))
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def subagents_filename(profile_slug: str | None) -> str | None:
    """`<PROFILE>_SUBAGENTS.md` -- present only for agents that orchestrate
    sub-agents (e.g. KAIROS_SUBAGENTS.md). Same casing rule the Foundation
    contract filenames use (see hermes_sync._contract_filename)."""
    if not profile_slug:
        return None
    return profile_slug.upper().replace("-", "_") + "_SUBAGENTS.md"


def allowed_filenames(runtime_type: str | None, profile_slug: str | None) -> list[str]:
    """The full ordered allow-list of profile files for one agent. This is the
    only thing that makes a `filename` path segment acceptable."""
    names = list(CORE_PROFILE_FILES)
    names.extend(RUNTIME_EXTRA_FILES.get(runtime_type or "", ()))
    subagents = subagents_filename(profile_slug)
    if subagents:
        names.append(subagents)
    return names


def resolve_file(home_dir: Path, filename: str, allowed: list[str]) -> Path | None:
    """Resolve `filename` inside `home_dir`, rejecting anything outside the
    allow-list or outside the directory itself (symlink escapes included)."""
    if filename not in allowed:
        return None
    candidate = home_dir / filename
    try:
        parent = candidate.resolve().parent
    except OSError:
        return None
    if parent != home_dir.resolve():
        return None
    return candidate


def stat_file(path: Path, filename: str, host_home: str) -> ProfileFileInfo:
    host_file = f"{host_home.rstrip('/')}/{filename}"
    try:
        stat = path.stat()
    except OSError:
        return ProfileFileInfo(
            filename=filename, path=host_file, exists=False, size=None, modified_at=None
        )
    return ProfileFileInfo(
        filename=filename,
        path=host_file,
        exists=True,
        size=stat.st_size,
        modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
    )

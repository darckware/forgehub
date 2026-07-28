"""Reconcile the agent registry with what is actually installed on the host.

The existing sync (`hermes_sync.py`) reads the Hermes Foundation *documents*:
it is the authority for who an agent is (layer, mission, role, sub-agents,
skills). It cannot be the authority for what an agent *runs*, because that is
not written in a contract -- it is a directory on disk and a CLI on PATH. That
gap is how Kairos ended up registered with `runtime_type` NULL: its contract
lists it like every other agent, but nothing in the docs says "this is a Hermes
profile", so the doc-driven sync had nothing to copy and the MCP screens read
it as "no runtime would ever load a server for this agent".

This module answers the other question, from evidence:

    profile directory exists  ->  /root/.hermes/profiles/<slug>   => hermes
    runtime home exists       ->  /root/.claude, /root/.codex,
                                   /root/.gemini/config,
                                   /root/.openclaw/workspace      => that runtime

Deliberately conservative:

  * it only *fills in* a missing `runtime_type`; a value already on file is
    never overwritten, because changing a runtime changes how the agent is
    executed (`agent_runs.py` maps it to a real command line). A registered
    value that contradicts the disk is reported, not "corrected";
  * it never creates or deletes agents. A profile on disk with no registered
    agent is reported so an operator can decide -- inventing rows here would
    make a scratch directory look like a member of the roster.

DB-free and pure, like hermes_sync: the route layer applies whatever this
returns.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.core import agent_mcp, agent_profile_files


@dataclass
class RuntimeDetection:
    """What the filesystem says about one agent."""

    runtime_type: str | None = None
    evidence: str | None = None
    home_path: str | None = None
    home_resolved: bool = False
    mcp_config_path: str | None = None
    mcp_config_exists: bool = False


@dataclass
class RuntimeSyncPlan:
    """One agent's reconciliation outcome, before anything is written."""

    agent_id: str
    agent_name: str
    detected: RuntimeDetection
    fill_runtime_type: str | None = None
    issues: list[str] = field(default_factory=list)


def _hermes_profile_dir(profile_slug: str | None) -> Path | None:
    if not profile_slug:
        return None
    return agent_profile_files.resolve_home_dir(
        f"{agent_profile_files.HERMES_PROFILES_ROOT}/{profile_slug}"
    )


def detect_runtime(
    *, profile_slug: str | None, runtime_type: str | None, home_path: str | None
) -> RuntimeDetection:
    """What this agent actually is, judged by what exists on disk.

    A Hermes profile directory wins over a runtime home: the eight (now nine)
    profile agents have a `/root/.hermes/profiles/<slug>` directory of their
    own, while the external runtimes share fixed homes that would otherwise
    match several agents at once.
    """
    detection = RuntimeDetection()

    if _hermes_profile_dir(profile_slug) is not None:
        detection.runtime_type = "hermes"
        detection.evidence = f"{agent_profile_files.HERMES_PROFILES_ROOT}/{profile_slug} exists"
    else:
        # Fall back to the runtime whose conventional home this agent points at
        # (explicitly via home_path, or implicitly through its runtime_type).
        effective = agent_profile_files.effective_home_path(home_path, runtime_type, profile_slug)
        for runtime, default_home in agent_profile_files.RUNTIME_DEFAULT_HOMES.items():
            if effective and effective.rstrip("/") == default_home.rstrip("/"):
                if agent_profile_files.resolve_home_dir(default_home) is not None:
                    detection.runtime_type = runtime
                    detection.evidence = f"{default_home} exists"
                break

    resolved_runtime = detection.runtime_type or runtime_type
    detection.home_path = agent_profile_files.effective_home_path(
        home_path, resolved_runtime, profile_slug
    )
    detection.home_resolved = agent_profile_files.resolve_home_dir(detection.home_path) is not None

    fmt = agent_mcp.format_for(resolved_runtime)
    if fmt is not None:
        detection.mcp_config_path = agent_mcp.config_host_path(detection.home_path, fmt)
        detection.mcp_config_exists = (
            agent_mcp.resolve_host_file(detection.mcp_config_path) is not None
        )
    return detection


def plan_for_agent(
    *, agent_id: str, agent_name: str, profile_slug: str | None, runtime_type: str | None,
    home_path: str | None,
) -> RuntimeSyncPlan:
    detected = detect_runtime(
        profile_slug=profile_slug, runtime_type=runtime_type, home_path=home_path
    )
    plan = RuntimeSyncPlan(agent_id=agent_id, agent_name=agent_name, detected=detected)

    if not runtime_type and detected.runtime_type:
        plan.fill_runtime_type = detected.runtime_type
    elif runtime_type and detected.runtime_type and detected.runtime_type != runtime_type:
        plan.issues.append(
            f"registered as {runtime_type!r} but the filesystem says {detected.runtime_type!r} "
            f"({detected.evidence}) — left as is; change it on the agent page if the registry is wrong"
        )
    elif not runtime_type and not detected.runtime_type:
        plan.issues.append(
            "no runtime_type and nothing on disk to infer one from — "
            "no runtime would load an MCP server for this agent"
        )

    if detected.home_path and not detected.home_resolved:
        plan.issues.append(f"home directory not reachable from the backend: {detected.home_path}")
    return plan


def list_profile_dirs() -> list[str]:
    """Every Hermes profile directory currently on disk."""
    root = agent_profile_files.resolve_home_dir(agent_profile_files.HERMES_PROFILES_ROOT)
    if root is None:
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))


def unregistered_profiles(registered_slugs: set[str]) -> list[str]:
    """Hermes profiles present on disk that no registered agent claims."""
    return [slug for slug in list_profile_dirs() if slug not in registered_slugs]

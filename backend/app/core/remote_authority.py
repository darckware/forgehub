"""Machine-scoped remote authority. Empty scopes never grant access.

Two separate actions. `remote_access.execute` runs library scripts and approved
proposals. `remote_access.direct` runs commands through the human-configured
agent list (api/routes/direct_access.py); neither implies
the other.

Above both sits one switch (Marcelo, 2026-11-06: "a pausa bloqueia todos os
agentes"): while paused, no agent reaches a machine through ForgeHub, by any
route. People, their schedules and the Workspace terminal are not affected.
"""
import uuid
from datetime import datetime, timezone

import yaml
from fastapi import HTTPException
from sqlalchemy import select

from app.core import agent_mcp
from app.core.agent_profile_files import EXTERNAL_RUNTIMES
from app.db.models.governance import AgentRemoteAccessControl, AuthorityDelegation, DELEGATION_RISK_ORDER
from app.db.models.server import HostGroupMember
from app.db.models.agent import Agent

ACTION = "remote_access.execute"
DIRECT_ACTION = "remote_access.direct"
DIRECT_DURATIONS_HOURS = (0, 1, 4, 24)
# Storage only. Never serialize this sentinel to tools or screens.
DIRECT_NO_EXPIRY = datetime(9999, 1, 1, tzinfo=timezone.utc)
# Marcelo's rule (2026-11-06): only these environments skip the confirmation.
# Everything else counts as sensitive, an unknown or blank value included.
NON_SENSITIVE_ENVIRONMENTS = frozenset({"test", "dev", "lab"})
RISK = {"read": "low", "change": "medium", "destructive": "high"}
# The single row of agent_remote_access_control, created by its migration.
CONTROL_ID = uuid.UUID("6f1d2c4e-8a35-4b7e-9c10-3e5a7b9d1f24")
PAUSED_CODE = "AGENT_REMOTE_ACCESS_PAUSED"
# What a Hermes profile's `forgehub` entry must run and expose to use each permission.
_MAINTENANCE_MCP_FILES = ("factory_server.py", "forgehub_messages_mcp.py")
_DIRECT_TOOL = "run_remote_command"
_SCRIPTS_TOOL = "run_maintenance_script"


async def agent_access_control(db, lock=False):
    query = select(AgentRemoteAccessControl).where(AgentRemoteAccessControl.id == CONTROL_ID)
    return await db.scalar(query.with_for_update(read=True) if lock else query)


async def require_agent_access_active(db, lock=False):
    """403 while paused. A missing row refuses too: not knowing is never "active".
    `lock` holds the row FOR SHARE until the caller commits, so a pause waits for a
    run already being recorded and the next one sees it. Refuse before anything is
    spent, an approved proposal's claim included."""
    control = await agent_access_control(db, lock)
    if control is None or control.paused:
        raise HTTPException(403, {"code": PAUSED_CODE, "message": (
            "Agent access to machines through ForgeHub is paused by a human admin. "
            "Nothing was run; do not retry until it is reactivated.")})


def hermes_tool_problem(profile_config: dict, tool: str) -> str | None:
    """Why a Hermes profile can't call this maintenance tool; None when it can."""
    entry = (profile_config.get("mcp_servers") or {}).get("forgehub")
    if not isinstance(entry, dict) or entry.get("enabled") is False:
        return "PROFILE_WITHOUT_FORGEHUB_MCP"
    if not any(str(arg).endswith(_MAINTENANCE_MCP_FILES) for arg in entry.get("args") or []):
        return "PROFILE_MCP_WITHOUT_MAINTENANCE_TOOLS"
    tools = entry.get("tools") or {}
    if tool in (tools.get("exclude") or []) or ("include" in tools and tool not in (tools["include"] or [])):
        return "PROFILE_MCP_WITHOUT_MAINTENANCE_TOOLS"
    return None


def hermes_direct_problem(profile_config: dict) -> str | None:
    """Why a Hermes profile can't call run_remote_command; None when it can."""
    return hermes_tool_problem(profile_config, _DIRECT_TOOL)


def hermes_scripts_problem(profile_config: dict) -> str | None:
    """Why a Hermes profile can't call run_maintenance_script; None when it can."""
    return hermes_tool_problem(profile_config, _SCRIPTS_TOOL)


def agent_tool_problems(agent) -> tuple[str | None, str | None]:
    """(commands reason, scripts reason): why this agent could not use direct
    access (run_remote_command) or library scripts (run_maintenance_script);
    None = it can. External runtimes get the run credential through their session
    config. Hermes gets it through the XDG_ variable (host-bridge/app.py), and the
    tool must reach it: Lara's and Maia's profiles filter it out. Read from the
    runtime's own file, not a copy, and once for both answers."""
    if agent.runtime_type in EXTERNAL_RUNTIMES:
        return None, None
    if agent.runtime_type != "hermes" or not agent.profile_slug:
        return "RUNTIME_WITHOUT_RUN_CREDENTIAL", "RUNTIME_WITHOUT_RUN_CREDENTIAL"
    fmt = agent_mcp.format_for("hermes")
    resolved = agent_mcp.resolve_host_file(agent_mcp.config_host_path(agent.effective_home_path, fmt))
    if resolved is None:
        return "PROFILE_NOT_READABLE", "PROFILE_NOT_READABLE"
    try:
        config = yaml.safe_load(resolved.read_text())
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return "PROFILE_NOT_READABLE", "PROFILE_NOT_READABLE"
    config = config if isinstance(config, dict) else {}
    return hermes_direct_problem(config), hermes_scripts_problem(config)


def direct_access_problem(agent) -> str | None:
    """Why this agent could not use a direct access (run_remote_command), or None."""
    return agent_tool_problems(agent)[0]


def scripts_access_problem(agent) -> str | None:
    """Why this agent could not run library scripts (run_maintenance_script), or None."""
    return agent_tool_problems(agent)[1]


def delegation_covers(row, server_id, groups):
    return str(server_id) in (row.servers or []) or bool(set(row.host_groups or []) & {str(g) for g in groups})


def is_sensitive_machine(server) -> bool:
    """The one place that decides which machines need the confirmation."""
    return (server.environment or "").strip().lower() not in NON_SENSITIVE_ENVIRONMENTS


def _active_delegations(agent_ids):
    now = datetime.now(timezone.utc)
    return select(AuthorityDelegation).where(
        AuthorityDelegation.grantee_type == "agent", AuthorityDelegation.grantee_id.in_(agent_ids),
        AuthorityDelegation.status == "active", AuthorityDelegation.revoked_at.is_(None),
        AuthorityDelegation.valid_from <= now, AuthorityDelegation.expires_at > now,
    )


async def remote_delegations(db, agent_ids, product_id=None, project_id=None):
    rows = (await db.scalars(_active_delegations(agent_ids))).all()
    return [r for r in rows if ACTION in r.allowed_actions
            and (not r.product_id or r.product_id == product_id)
            and (not r.project_id or r.project_id == project_id)]


async def direct_accesses(db, agent_id, lock=False):
    """An agent's active direct configurations. `lock` holds them FOR SHARE until the
    caller commits, so closing one waits for a command already being recorded
    and the next command sees it closed."""
    agent_query = select(Agent).where(Agent.id == agent_id)
    agent = await db.scalar(agent_query.with_for_update(read=True) if lock else agent_query)
    if not agent or not agent.is_active or agent.status != "active" or not agent.direct_access_allowed:
        return []
    query = _active_delegations([agent_id])
    if lock:
        query = query.with_for_update(read=True)
    return [r for r in (await db.scalars(query)).all() if DIRECT_ACTION in r.allowed_actions]


def direct_access_for(rows, server_id, elevation=False):
    """The longest-lasting configuration covering a machine. Restricted groups
    store a snapshot; all_machines includes newly prepared machines too."""
    covering = [r for r in rows if (r.all_machines or str(server_id) in (r.servers or [])) and (r.allow_elevation or not elevation)]
    return max(covering, key=lambda r: r.expires_at, default=None)


def direct_coverage_expands(previous, all_machines, server_ids):
    """Whether this change needs a fresh human confirmation of coverage."""
    if previous is not None and previous.all_machines:
        return False
    return all_machines or bool({str(s) for s in server_ids} - set(previous.servers if previous else []))


async def require_direct(db, agent_id, servers, elevation=False, lock=False):
    """{server id: covering access}, or 403 naming what is missing."""
    rows = await direct_accesses(db, agent_id, lock)
    if not servers or any(direct_access_for(rows, s.id) is None for s in servers):
        raise HTTPException(403, {"code": "NO_DIRECT_ACCESS",
                                  "message": "No open direct access covers every one of these machines"})
    chosen = {s.id: direct_access_for(rows, s.id, elevation) for s in servers}
    if denied := [s.name for s in servers if chosen[s.id] is None]:
        raise HTTPException(403, {"code": "ELEVATION_NOT_ALLOWED", "message": (
            "This command looks like elevation (sudo, su, docker...) and the access to "
            f"{', '.join(denied)} was opened without it. Ask a human admin to change the agent configuration.")})
    return chosen


async def machine_ceilings(db, agent_ids, servers, product_id=None, project_id=None):
    rows = await remote_delegations(db, agent_ids, product_id, project_id)
    members = (await db.execute(select(HostGroupMember.server_id, HostGroupMember.group_id)
                               .where(HostGroupMember.server_id.in_([s.id for s in servers])))).all()
    groups = {}
    for sid, gid in members:
        groups.setdefault(sid, set()).add(gid)
    ceilings = {}
    for aid in agent_ids:
        per_machine = []
        for server in servers:
            risks = [r.max_risk for r in rows if r.grantee_id == aid and delegation_covers(r, server.id, groups.get(server.id, set()))]
            if not risks:
                break
            per_machine.append(max(risks, key=lambda r: DELEGATION_RISK_ORDER[r]))
        else:
            if per_machine:
                ceilings[aid] = min(per_machine, key=lambda r: DELEGATION_RISK_ORDER[r])
    return ceilings


async def require_remote(db, principal, servers, risk="read", product_id=None, project_id=None):
    if principal.principal_type != "agent":
        raise HTTPException(403, "Individual agent credential required")
    ceilings = await machine_ceilings(db, [principal.principal_id], servers, product_id, project_id)
    ceiling = ceilings.get(principal.principal_id)
    if ceiling is None or DELEGATION_RISK_ORDER[ceiling] < DELEGATION_RISK_ORDER[RISK[risk]]:
        raise HTTPException(403, "No active delegation covers these machines and risk")


async def project_product_id(db, project):
    if project is None:
        return None
    from app.db.models.product import ProductVersion
    return await db.scalar(select(ProductVersion.product_id).where(ProductVersion.id == project.product_version_id))


def require_running_remote_task(demand):
    """A remote task must still be the dispatched attempt addressed to the agent."""
    if demand.dispatch_status in ("completed", "failed"):
        raise HTTPException(403, {"code": "TASK_FINISHED", "message": "This task has finished; no command was sent"})
    if demand.dispatch_status not in ("dispatched", "running"):
        raise HTTPException(403, {"code": "TASK_NOT_RUNNING", "message": "This task has no running dispatch"})


def require_remote_task_credential(principal, demand):
    """A dispatch token can act only inside its own still-running task."""
    require_running_remote_task(demand)
    if (not demand.agent_run_id or principal.principal_id != demand.target_agent_id
            or getattr(principal, "credential_label", None) != f"dispatch:{demand.agent_run_id}"):
        raise HTTPException(403, {"code": "TASK_CREDENTIAL_MISMATCH",
            "message": "Use the credential issued to this task dispatch; no command was sent"})

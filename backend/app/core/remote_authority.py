"""Machine-scoped remote authority. Empty scopes never grant access.

Two separate actions. `remote_access.execute` runs library scripts and approved
proposals. `remote_access.direct` runs any command, only through a temporary
opening made by a human admin (api/routes/direct_access.py); neither implies
the other.
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select

from app.db.models.governance import AuthorityDelegation, DELEGATION_RISK_ORDER
from app.db.models.server import HostGroupMember

ACTION = "remote_access.execute"
DIRECT_ACTION = "remote_access.direct"
DIRECT_DURATIONS_HOURS = (1, 4, 24)
# Marcelo's rule (2026-11-06): only these environments skip the confirmation.
# Everything else counts as sensitive, an unknown or blank value included.
NON_SENSITIVE_ENVIRONMENTS = frozenset({"test", "dev", "lab"})
RISK = {"read": "low", "change": "medium", "destructive": "high"}


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
    """An agent's open direct accesses. `lock` holds them FOR SHARE until the
    caller commits, so closing one waits for a command already being recorded
    and the next command sees it closed."""
    query = _active_delegations([agent_id])
    if lock:
        query = query.with_for_update(read=True)
    return [r for r in (await db.scalars(query)).all() if DIRECT_ACTION in r.allowed_actions and r.purpose]


def direct_access_for(rows, server_id, elevation=False):
    """The access covering one machine, the longest-lasting first. Coverage is
    `servers` only: an opening stores the group's members of that moment, so a
    machine added to the group later never skips the sensitive confirmation."""
    covering = [r for r in rows if str(server_id) in (r.servers or []) and (r.allow_elevation or not elevation)]
    return max(covering, key=lambda r: r.expires_at, default=None)


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
            f"{', '.join(denied)} was opened without it. Ask for a new opening with sudo/docker allowed.")})
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

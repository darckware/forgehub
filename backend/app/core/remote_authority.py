"""Machine-scoped remote authority. Empty scopes never grant access."""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select

from app.db.models.governance import AuthorityDelegation, DELEGATION_RISK_ORDER
from app.db.models.server import HostGroupMember

ACTION = "remote_access.execute"
RISK = {"read": "low", "change": "medium", "destructive": "high"}


def delegation_covers(row, server_id, groups):
    return str(server_id) in (row.servers or []) or bool(set(row.host_groups or []) & {str(g) for g in groups})


async def remote_delegations(db, agent_ids, product_id=None, project_id=None):
    now = datetime.now(timezone.utc)
    rows = (await db.scalars(select(AuthorityDelegation).where(
        AuthorityDelegation.grantee_type == "agent", AuthorityDelegation.grantee_id.in_(agent_ids),
        AuthorityDelegation.status == "active", AuthorityDelegation.revoked_at.is_(None),
        AuthorityDelegation.valid_from <= now, AuthorityDelegation.expires_at > now,
    ))).all()
    return [r for r in rows if ACTION in r.allowed_actions
            and (not r.product_id or r.product_id == product_id)
            and (not r.project_id or r.project_id == project_id)]


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

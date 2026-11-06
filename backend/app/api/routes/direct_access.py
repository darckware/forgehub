"""Direct, temporary remote access (Marcelo, 2026-11-06, option A).

A human admin opens an access for an agent on chosen machines for 1, 4 or 24
hours; inside it, the agent runs commands through ForgeHub with no approval per
command. The agent never gets the SSH key: ForgeHub connects with the vault's
key on the machine's existing account and records everything.

The opening is a dedicated route and not `/governed/authority-delegations`,
which refuses this action: only here are the fixed durations, the agent's
runtime and the sensitive confirmation enforced.
"""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import host_execution as host
from app.api.schemas.direct_access import (
    DirectAccessClosed, DirectAccessMachine, DirectAccessOpen, DirectAccessOut, DirectCommandCreate,
)
from app.api.schemas.host_execution import HostExecutionDetail
from app.core.agent_profile_files import EXTERNAL_RUNTIMES
from app.core.deps import ActorPrincipal, get_actor_principal, get_maintenance_agent
from app.core.maintenance_proposals import looks_elevated, refuse_literal_secret
from app.core.remote_authority import DIRECT_ACTION, is_sensitive_machine, require_direct
from app.db.base import get_db
from app.db.models.agent import Agent
from app.db.models.governance import AuditEvent, AuthorityDelegation
from app.db.models.host_execution import HostExecutionResult
from app.db.models.notification import Notification
from app.db.models.server import Server
from app.db.models.user import User

router = APIRouter(tags=["remote-access"])
ADMIN = "/api/v1/remote-access/direct"
RUNNING_NOTICE = (
    "New commands are refused from now on. A command already running is not interrupted: "
    "it finishes or reaches its own timeout, as any execution does."
)


def _human_admin(principal: ActorPrincipal) -> None:
    if principal.principal_type != "user" or not principal.is_admin:
        raise HTTPException(403, "Only a human admin opens or closes a direct access")


def _audit_machines(db, event: str, actor: str, servers: list[Server], agent: str, reason: str | None) -> None:
    """One line in each machine's own history."""
    for server in servers:
        db.add(AuditEvent(entity_type="server", entity_id=server.id, event_type=event, actor=actor,
                          payload={"agent": agent, "reason": reason}))


async def _out(db: AsyncSession, rows: list[AuthorityDelegation]) -> list[DirectAccessOut]:
    server_ids = {uuid.UUID(s) for r in rows for s in r.servers}
    servers = {s.id: s for s in (await db.scalars(select(Server).where(Server.id.in_(server_ids)))).all()}
    agents = dict((await db.execute(select(Agent.id, Agent.name).where(
        Agent.id.in_({r.grantee_id for r in rows})))).all())
    users = dict((await db.execute(select(User.id, User.username).where(
        User.id.in_({r.grantor_user_id for r in rows})))).all())
    out = []
    for row in rows:
        machines = [servers[uuid.UUID(s)] for s in row.servers if uuid.UUID(s) in servers]
        out.append(DirectAccessOut(
            id=row.id, agent_id=row.grantee_id, agent_name=agents.get(row.grantee_id, "?"), purpose=row.purpose,
            allow_elevation=row.allow_elevation, reason=row.reason, granted_by=users.get(row.grantor_user_id),
            opened_at=row.valid_from, expires_at=row.expires_at,
            machines=[DirectAccessMachine(id=m.id, name=m.name, sensitive=is_sensitive_machine(m))
                      for m in sorted(machines, key=lambda m: m.name)],
        ))
    return out


@router.get(ADMIN, response_model=list[DirectAccessOut])
async def list_direct_accesses(
    principal: ActorPrincipal = Depends(get_actor_principal), db: AsyncSession = Depends(get_db),
):
    _human_admin(principal)
    now = datetime.now(timezone.utc)
    rows = (await db.scalars(select(AuthorityDelegation).where(
        AuthorityDelegation.status == "active", AuthorityDelegation.revoked_at.is_(None),
        AuthorityDelegation.purpose.is_not(None), AuthorityDelegation.expires_at > now,
    ).order_by(AuthorityDelegation.expires_at))).all()
    return await _out(db, [r for r in rows if DIRECT_ACTION in r.allowed_actions])


@router.post(ADMIN, response_model=DirectAccessOut, status_code=status.HTTP_201_CREATED)
async def open_direct_access(
    payload: DirectAccessOpen,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
):
    _human_admin(principal)
    refuse_literal_secret(payload.reason)
    agent = await db.get(Agent, payload.agent_id)
    if not agent or not agent.is_active or agent.status != "active":
        raise HTTPException(422, "Active agent not found")
    if agent.runtime_type not in EXTERNAL_RUNTIMES:
        raise HTTPException(422, "Only Claude, Codex and agy agents receive a run credential")
    servers, _ = await host.resolve_targets(db, payload.server_ids, payload.group_ids)
    if not servers:
        raise HTTPException(422, "Pick at least one machine or a group with machines")
    sensitive = [s.name for s in servers if is_sensitive_machine(s)]
    if sensitive and not payload.confirm_sensitive:
        raise HTTPException(409, {"code": "SENSITIVE_CONFIRMATION_REQUIRED", "machines": sensitive,
                                  "message": "This opening includes sensitive machines and needs confirmation"})
    now = datetime.now(timezone.utc)
    access = AuthorityDelegation(
        grantor_user_id=principal.principal_id, grantee_type="agent", grantee_id=agent.id,
        allowed_actions=[DIRECT_ACTION], max_risk="high", valid_from=now,
        expires_at=now + timedelta(hours=payload.duration_hours),
        # Machines of this moment: see direct_access_for. The groups stay as a record.
        servers=[str(s.id) for s in servers], host_groups=[str(g) for g in payload.group_ids],
        reason=payload.reason, purpose=payload.purpose, allow_elevation=payload.allow_elevation,
    )
    db.add(access)
    await db.flush()
    db.add(AuditEvent(
        entity_type="authority_delegation", entity_id=access.id, event_type="direct_access_opened",
        actor=principal.display_name,
        payload={"agent_id": str(agent.id), "agent": agent.name, "machines": [s.name for s in servers],
                 "groups": access.host_groups, "reason": payload.reason, "purpose": payload.purpose,
                 "duration_hours": payload.duration_hours, "allow_elevation": payload.allow_elevation,
                 "sensitive_machines": sensitive,
                 "sensitive_confirmed_by": principal.display_name if sensitive else None},
    ))
    _audit_machines(db, "direct_access_opened", principal.display_name, servers, agent.name, payload.reason)
    db.add(Notification(
        source="system", severity="warning" if sensitive else "info", title="Acesso remoto direto aberto",
        message=f"{principal.display_name} abriu acesso direto para {agent.name} por {payload.duration_hours} h.",
        event_key=f"direct-access:opened:{access.id}", occurred_at=now,
    ))
    await db.commit()
    await db.refresh(access)
    return (await _out(db, [access]))[0]


@router.post(ADMIN + "/{access_id}:close", response_model=DirectAccessClosed)
async def close_direct_access(
    access_id: uuid.UUID,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
):
    _human_admin(principal)
    # Waits for a command holding this row FOR SHARE: that one counts as already running.
    access = await db.scalar(select(AuthorityDelegation).where(
        AuthorityDelegation.id == access_id).with_for_update())
    if access is None or DIRECT_ACTION not in access.allowed_actions:
        raise HTTPException(404, "Direct access not found")
    now = datetime.now(timezone.utc)
    if access.status != "active" or access.revoked_at or access.expires_at <= now:
        raise HTTPException(409, "This direct access is already closed")
    access.status, access.revoked_at = "revoked", now
    running = await db.scalar(select(func.count()).select_from(HostExecutionResult).where(
        HostExecutionResult.delegation_id == access.id,
        HostExecutionResult.status.in_(host.ACTIVE_RESULT_STATUSES),
    )) or 0
    agent = await db.get(Agent, access.grantee_id)
    name = agent.name if agent else str(access.grantee_id)
    db.add(AuditEvent(entity_type="authority_delegation", entity_id=access.id, event_type="direct_access_closed",
                      actor=principal.display_name, payload={"agent": name, "running_commands": running}))
    servers = (await db.scalars(select(Server).where(Server.id.in_([uuid.UUID(s) for s in access.servers])))).all()
    _audit_machines(db, "direct_access_closed", principal.display_name, list(servers), name, None)
    db.add(Notification(source="system", severity="info", title="Acesso remoto direto encerrado",
                        message=f"{principal.display_name} encerrou o acesso direto de {name}.",
                        event_key=f"direct-access:closed:{access.id}", occurred_at=now))
    await db.commit()
    return DirectAccessClosed(id=access.id, closed_at=now, running_commands=running, notice=RUNNING_NOTICE)


def _machines_conflict(code: str, message: str, names: list[str]) -> HTTPException:
    return HTTPException(409, {"code": code, "message": f"{message}: {', '.join(names)}", "machines": names})


@router.post("/api/v1/host-executions/agent/commands", response_model=HostExecutionDetail,
             status_code=status.HTTP_201_CREATED)
async def run_direct_command(
    payload: DirectCommandCreate,
    principal: ActorPrincipal = Depends(get_maintenance_agent),
    db: AsyncSession = Depends(get_db),
):
    refuse_literal_secret(payload.command)
    refuse_literal_secret(payload.reason)
    servers, _ = await host.resolve_targets(db, payload.server_ids, [])
    agent = await db.get(Agent, principal.principal_id)
    demand_id = await host._check_against_task(
        db, agent, SimpleNamespace(message_number=payload.message_number), None, servers)
    elevation = looks_elevated(payload.command)
    await require_direct(db, agent.id, servers, elevation)
    readiness = await host._agent_readiness(db)
    if blocked := [s.name for s in servers if not readiness.get(s.id, (False, ""))[0]]:
        raise _machines_conflict("LOGIN_NOT_READY", "ForgeHub has no working login on", blocked)

    # Decided under locks, released by launch_execution's commit: two commands can't
    # both find a machine free, and closing an access waits for this one to be recorded.
    await db.scalars(select(Server.id).where(Server.id.in_([s.id for s in servers]))
                     .order_by(Server.id).with_for_update(key_share=True))
    chosen = await require_direct(db, agent.id, servers, elevation, lock=True)
    busy = await host.busy_server_ids(db)
    if taken := [s.name for s in servers if s.id in busy]:
        await db.rollback()
        raise _machines_conflict("MACHINE_BUSY", "Already running another command, try again later", taken)
    execution = await host.launch_execution(
        db, servers=servers, command=payload.command, shell=payload.shell, timeout_seconds=payload.timeout_seconds,
        actor=principal.display_name,
        target_summary=servers[0].name if len(servers) == 1 else f"{len(servers)} machine(s)",
        trigger="agent", agent_id=agent.id, agent_demand_id=demand_id, reason=payload.reason.strip(),
        direct_access={sid: access.id for sid, access in chosen.items()},
    )
    return await host._detail(db, execution)

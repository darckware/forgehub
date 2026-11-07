"""Direct, temporary remote access (Marcelo, 2026-11-06, option A).

A human admin opens an access for an agent on chosen machines for 1, 4 or 24
hours; inside it, the agent runs commands through ForgeHub with no approval per
command. The agent never gets the SSH key: ForgeHub connects with the vault's
key on the machine's existing account and records everything.

The opening is a dedicated route and not `/governed/authority-delegations`,
which refuses this action: only here are the fixed durations, the agent's
runtime and the sensitive confirmation enforced.

Two things sit around it, both only for a human admin: the list of agents that
may get an access (`Agent.direct_access_allowed`), and the pause, which stops
every agent on every route (core/remote_authority.py) and closes nothing: an
access still valid at reactivation counts again, its clock having kept running.
"""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import host_execution as host
from app.api.schemas.direct_access import (
    AgentAccessControlOut, AgentAccessPause, DirectAccessClosed, DirectAccessMachine, DirectAccessOpen,
    DirectAccessOut, DirectAgentOut, DirectAgentRemoved, DirectCommandCreate,
)
from app.api.schemas.host_execution import HostExecutionDetail
from app.core.deps import ActorPrincipal, get_actor_principal, get_maintenance_agent
from app.core.maintenance_proposals import looks_elevated, refuse_literal_secret
from app.core.remote_authority import (
    CONTROL_ID, DIRECT_ACTION, agent_access_control, direct_access_problem, is_sensitive_machine, require_agent_access_active,
    require_direct,
)
from app.db.base import get_db
from app.db.models.agent import Agent
from app.db.models.governance import AgentRemoteAccessControl, AuditEvent, AuthorityDelegation
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
    # Removing the agent from the list waits for this row, and sees this opening to close it.
    agent = await db.scalar(select(Agent).where(Agent.id == payload.agent_id).with_for_update(read=True))
    if not agent or not agent.is_active or agent.status != "active":
        raise HTTPException(422, "Active agent not found")
    if not agent.direct_access_allowed:
        raise HTTPException(422, {"code": "AGENT_NOT_LISTED", "message": "This agent is not on the direct access list"})
    if problem := direct_access_problem(agent):
        raise HTTPException(422, {"code": problem, "message": "This agent cannot use a direct access"})
    await require_agent_access_active(db, lock=True)
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
    agent = await db.get(Agent, access.grantee_id)
    name = agent.name if agent else str(access.grantee_id)
    running = await _close(db, access, principal.display_name, name, now)
    await db.commit()
    return DirectAccessClosed(id=access.id, closed_at=now, running_commands=running, notice=RUNNING_NOTICE)


async def _close(db: AsyncSession, access: AuthorityDelegation, actor: str, agent: str, now: datetime,
                 cause: str | None = None) -> int:
    """Revokes a locked access and records it. Returns the machines still running."""
    access.status, access.revoked_at = "revoked", now
    running = await db.scalar(select(func.count()).select_from(HostExecutionResult).where(
        HostExecutionResult.delegation_id == access.id,
        HostExecutionResult.status.in_(host.ACTIVE_RESULT_STATUSES),
    )) or 0
    db.add(AuditEvent(entity_type="authority_delegation", entity_id=access.id, event_type="direct_access_closed",
                      actor=actor, payload={"agent": agent, "running_commands": running, "cause": cause}))
    servers = (await db.scalars(select(Server).where(Server.id.in_([uuid.UUID(s) for s in access.servers])))).all()
    _audit_machines(db, "direct_access_closed", actor, list(servers), agent, cause)
    db.add(Notification(source="system", severity="info", title="Acesso remoto direto encerrado",
                        message=f"{actor} encerrou o acesso direto de {agent}.",
                        event_key=f"direct-access:closed:{access.id}", occurred_at=now))
    return running


@router.get(ADMIN + "/agents", response_model=list[DirectAgentOut])
async def list_direct_agents(
    principal: ActorPrincipal = Depends(get_actor_principal), db: AsyncSession = Depends(get_db),
):
    """Every active agent: the list, plus who can join it and why the rest can't."""
    _human_admin(principal)
    rows = (await db.scalars(select(Agent).where(Agent.is_active.is_(True), Agent.status == "active")
                             .order_by(Agent.name))).all()
    return [DirectAgentOut(id=a.id, name=a.name, runtime_type=a.runtime_type, allowed=a.direct_access_allowed,
                           unsupported_reason=direct_access_problem(a)) for a in rows]


@router.post(ADMIN + "/agents/{agent_id}", response_model=DirectAgentOut, status_code=status.HTTP_201_CREATED)
async def add_direct_agent(
    agent_id: uuid.UUID,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
):
    _human_admin(principal)
    agent = await db.scalar(select(Agent).where(Agent.id == agent_id).with_for_update())
    if not agent or not agent.is_active or agent.status != "active":
        raise HTTPException(404, "Active agent not found")
    if agent.direct_access_allowed:
        raise HTTPException(409, "This agent is already on the list")
    if problem := direct_access_problem(agent):
        raise HTTPException(422, {"code": problem, "message": "This agent cannot use a direct access"})
    agent.direct_access_allowed = True
    db.add(AuditEvent(entity_type="agent", entity_id=agent.id, event_type="direct_access_agent_added",
                      actor=principal.display_name, payload={"agent": agent.name}))
    await db.commit()
    return DirectAgentOut(id=agent.id, name=agent.name, runtime_type=agent.runtime_type, allowed=True,
                          unsupported_reason=None)


@router.delete(ADMIN + "/agents/{agent_id}", response_model=DirectAgentRemoved)
async def remove_direct_agent(
    agent_id: uuid.UUID,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
):
    """Off the list and every open access closed, in one transaction. Locks in the
    order an opening takes them: the agent's row, then each access (waiting for a
    command being recorded, which then counts as already running)."""
    _human_admin(principal)
    agent = await db.scalar(select(Agent).where(Agent.id == agent_id).with_for_update())
    if not agent or not agent.direct_access_allowed:
        raise HTTPException(404, "This agent is not on the list")
    agent.direct_access_allowed = False
    now = datetime.now(timezone.utc)
    rows = (await db.scalars(select(AuthorityDelegation).where(
        AuthorityDelegation.grantee_type == "agent", AuthorityDelegation.grantee_id == agent.id,
        AuthorityDelegation.status == "active", AuthorityDelegation.revoked_at.is_(None),
        AuthorityDelegation.expires_at > now,
    ).with_for_update())).all()
    accesses = [r for r in rows if DIRECT_ACTION in r.allowed_actions]
    running = 0
    for access in accesses:
        running += await _close(db, access, principal.display_name, agent.name, now, "agent_removed_from_list")
    db.add(AuditEvent(entity_type="agent", entity_id=agent.id, event_type="direct_access_agent_removed",
                      actor=principal.display_name,
                      payload={"agent": agent.name, "closed_accesses": [str(a.id) for a in accesses],
                               "running_commands": running}))
    await db.commit()
    return DirectAgentRemoved(agent_id=agent.id, closed_accesses=len(accesses), running_commands=running,
                              notice=RUNNING_NOTICE)


def _control_out(control: AgentRemoteAccessControl) -> AgentAccessControlOut:
    return AgentAccessControlOut(paused=control.paused, paused_at=control.paused_at, paused_by=control.paused_by,
                                 reason=control.reason)


async def _control_for_change(db: AsyncSession) -> AgentRemoteAccessControl:
    """FOR UPDATE: waits for any run holding the row FOR SHARE, already being recorded."""
    control = await db.scalar(select(AgentRemoteAccessControl).where(
        AgentRemoteAccessControl.id == CONTROL_ID).with_for_update())
    if control is None:
        control = AgentRemoteAccessControl(id=CONTROL_ID)
        db.add(control)
    return control


@router.get(ADMIN + "/control", response_model=AgentAccessControlOut)
async def get_agent_access_control(
    principal: ActorPrincipal = Depends(get_actor_principal), db: AsyncSession = Depends(get_db),
):
    _human_admin(principal)
    control = await agent_access_control(db)
    # Same answer the routes give to a missing row: not active.
    return _control_out(control) if control else AgentAccessControlOut(paused=True, paused_at=None, paused_by=None, reason=None)


@router.post(ADMIN + "/control:pause", response_model=AgentAccessControlOut)
async def pause_agent_access(
    payload: AgentAccessPause,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
):
    _human_admin(principal)
    reason = (payload.reason or "").strip() or None
    if reason:
        refuse_literal_secret(reason)
    control = await _control_for_change(db)
    if control.paused:
        raise HTTPException(409, "Agent access is already paused")
    now = datetime.now(timezone.utc)
    control.paused, control.paused_at, control.paused_by, control.reason = True, now, principal.display_name, reason
    db.add(AuditEvent(entity_type="agent_remote_access", entity_id=CONTROL_ID, event_type="agent_remote_access_paused",
                      actor=principal.display_name, payload={"reason": reason}))
    db.add(Notification(source="system", severity="warning", title="Acesso de agentes às máquinas pausado",
                        message=f"{principal.display_name} pausou o acesso de todos os agentes pelo ForgeHub.",
                        event_key=f"agent-remote-access:paused:{now.isoformat()}", occurred_at=now))
    await db.commit()
    return _control_out(control)


@router.post(ADMIN + "/control:resume", response_model=AgentAccessControlOut)
async def resume_agent_access(
    principal: ActorPrincipal = Depends(get_actor_principal), db: AsyncSession = Depends(get_db),
):
    _human_admin(principal)
    control = await _control_for_change(db)
    if control.paused is False:
        raise HTTPException(409, "Agent access is not paused")
    paused_since = control.paused_at
    now = datetime.now(timezone.utc)
    control.paused, control.paused_at, control.paused_by, control.reason = False, None, None, None
    db.add(AuditEvent(entity_type="agent_remote_access", entity_id=CONTROL_ID, event_type="agent_remote_access_resumed",
                      actor=principal.display_name,
                      payload={"paused_since": paused_since.isoformat() if paused_since else None}))
    db.add(Notification(source="system", severity="info", title="Acesso de agentes às máquinas reativado",
                        message=f"{principal.display_name} reativou o acesso dos agentes pelo ForgeHub.",
                        event_key=f"agent-remote-access:resumed:{now.isoformat()}", occurred_at=now))
    await db.commit()
    return _control_out(control)


def _machines_conflict(code: str, message: str, names: list[str]) -> HTTPException:
    return HTTPException(409, {"code": code, "message": f"{message}: {', '.join(names)}", "machines": names})


@router.post("/api/v1/host-executions/agent/commands", response_model=HostExecutionDetail,
             status_code=status.HTTP_201_CREATED)
async def run_direct_command(
    payload: DirectCommandCreate,
    principal: ActorPrincipal = Depends(get_maintenance_agent),
    db: AsyncSession = Depends(get_db),
):
    await require_agent_access_active(db)
    refuse_literal_secret(payload.command)
    refuse_literal_secret(payload.reason)
    servers, _ = await host.resolve_targets(db, payload.server_ids, [])
    agent = await db.get(Agent, principal.principal_id)
    if not agent.direct_access_allowed:
        raise HTTPException(403, {"code": "AGENT_NOT_LISTED", "message": "You are not on the direct access list"})
    demand_id = await host._check_against_task(
        db, agent, SimpleNamespace(message_number=payload.message_number), None, servers)
    elevation = looks_elevated(payload.command)
    await require_direct(db, agent.id, servers, elevation)
    readiness = await host._agent_readiness(db)
    if blocked := [s.name for s in servers if not readiness.get(s.id, (False, ""))[0]]:
        raise _machines_conflict("LOGIN_NOT_READY", "ForgeHub has no working login on", blocked)

    # Decided under locks, released by launch_execution's commit: two commands can't
    # both find a machine free, and closing an access or pausing waits for this one to be recorded.
    await require_agent_access_active(db, lock=True)
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

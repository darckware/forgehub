"""Collaborative execution in an active session with Marcelo
(docs/architecture/REMOTE_ACCESS_RULE.md, "Execução colaborativa autorizada em
sessão ativa"). Inactive unless settings.REMOTE_COLLABORATION_ENABLED with a
valid REMOTE_COLLABORATION_OWNER_USER_ID; no MCP tool or screen uses it yet.

Human side (prefix /api/v1/remote-access/collaboration): only the configured
owner, as an admin, through a JWT whose `sid` is a live browser session of his.
He opens a session (one agent, its running task and run, one machine, one
operation) and authorizes each command beforehand, byte for byte.

Agent side (POST /api/v1/host-executions/agent/collaborative-commands): the
agent's dispatch credential runs one authorized command, once, after
core/remote_collaboration.require_collaboration re-checks every binding.
"""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import host_execution as host
from app.api.schemas.host_execution import HostExecutionDetail
from app.api.schemas.remote_collaboration import (
    CollaborationCommandCreate, CollaborationCommandOut, CollaborationEnd, CollaborationSessionCreate,
    CollaborationSessionOut, CollaborativeCommandRun,
)
from app.core.deps import ActorPrincipal, bearer_scheme, get_actor_principal, get_maintenance_agent
from app.core.maintenance_proposals import looks_elevated, refuse_literal_secret
from app.core.remote_authority import (
    require_agent_access_active, require_direct, require_running_remote_task,
)
from app.core.remote_collaboration import (
    audit_session, command_sha256, configured_owner, machine_not_runnable, owner_session_live, refuse,
    require_collaboration, require_coding_agent,
    require_demand_bound, require_owner_valid, require_session_current, revoke_unused_commands,
)
from app.core.security import decode_access_token
from app.core.user_session import session_hash
from app.db.base import get_db
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand
from app.db.models.notification import Notification
from app.db.models.remote_collaboration import RemoteCollaborationCommand, RemoteCollaborationSession
from app.db.models.server import Server
from app.db.models.user_session import UserSession

router = APIRouter(tags=["remote-access"])
HUMAN = "/api/v1/remote-access/collaboration"


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def get_collaboration_owner(
    principal: ActorPrincipal = Depends(get_actor_principal),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> tuple[ActorPrincipal, UserSession]:
    """The configured owner, as an admin, in a live browser session of his own."""
    owner_id = configured_owner()
    denied = refuse("COLLABORATION_OWNER_ONLY",
                    "Only the configured owner, in a live browser session, manages collaborative sessions.")
    if principal.principal_type != "user" or not principal.is_admin or principal.principal_id != owner_id:
        raise denied
    if credentials is None or credentials.credentials.startswith("agt_"):
        raise denied
    payload = decode_access_token(credentials.credentials) or {}
    sid = payload.get("sid")
    if not isinstance(sid, str) or not sid or len(sid) > 128:
        raise denied
    row = await db.scalar(select(UserSession).where(
        UserSession.token_hash == session_hash(sid), UserSession.user_id == owner_id,
        UserSession.is_active.is_(True), UserSession.expires_at > _now()))
    if row is None:
        raise denied
    return principal, row


async def _locked_session(db, session_id: uuid.UUID) -> RemoteCollaborationSession:
    session = await db.scalar(select(RemoteCollaborationSession).where(RemoteCollaborationSession.id == session_id)
                              .with_for_update().execution_options(populate_existing=True))
    if session is None:
        raise HTTPException(404, "Collaborative session not found")
    return session


def _not_runnable(server: Server, shell: str | None = None) -> None:
    """422 MACHINE_NOT_RUNNABLE when launch_execution would skip this machine."""
    if reason := machine_not_runnable(server, shell):
        raise HTTPException(422, {"code": "MACHINE_NOT_RUNNABLE", "machines": [server.name],
                                  "message": f"{server.name} can't run this: {reason}"})


async def _dead_reason(db, session: RemoteCollaborationSession) -> str | None:
    """Why a session still marked active can no longer be used, or None if it can."""
    if session.user_session_id is None:
        return "owner_session_removed"
    if session.server_id is None:
        return "machine_removed"
    if session.expires_at <= _now():
        return "expired"
    if not await owner_session_live(db, session):
        return "owner_session_ended"
    demand = await db.get(AgentDemand, session.agent_demand_id)
    try:
        require_demand_bound(session, demand)
        require_running_remote_task(demand)
    except HTTPException:
        return "run_ended"
    return None


async def _out(db, sessions: list[RemoteCollaborationSession]) -> list[CollaborationSessionOut]:
    if not sessions:
        return []
    agents = dict((await db.execute(select(Agent.id, Agent.name).where(
        Agent.id.in_({s.agent_id for s in sessions})))).all())
    servers = dict((await db.execute(select(Server.id, Server.name).where(
        Server.id.in_({s.server_id for s in sessions if s.server_id is not None})))).all())
    numbers = dict((await db.execute(select(AgentDemand.id, AgentDemand.number).where(
        AgentDemand.id.in_({s.agent_demand_id for s in sessions})))).all())
    commands: dict[uuid.UUID, list] = {s.id: [] for s in sessions}
    for row in (await db.scalars(select(RemoteCollaborationCommand).where(
            RemoteCollaborationCommand.session_id.in_(list(commands))).order_by(
            RemoteCollaborationCommand.created_at))).all():
        commands[row.session_id].append(CollaborationCommandOut.model_validate(row))
    # `status` is what was recorded; a row still "active" that can no longer be
    # used (run ended, owner logged out elsewhere, expired, binding removed) reads
    # effective_status="inactive" with the same reason the validator would refuse.
    dead = {s.id: await _dead_reason(db, s) for s in sessions if s.status == "active"}
    return [CollaborationSessionOut(
        id=s.id, agent_id=s.agent_id, agent_name=agents.get(s.agent_id), message_number=numbers.get(s.agent_demand_id),
        agent_run_id=s.agent_run_id, server_id=s.server_id, server_name=servers.get(s.server_id),
        operation=s.operation, allow_elevation=s.allow_elevation, status=s.status, expires_at=s.expires_at,
        created_at=s.created_at, ended_at=s.ended_at, ended_by=s.ended_by, end_reason=s.end_reason,
        commands=commands[s.id],
        effective_status=s.status if s.status != "active" else ("inactive" if dead[s.id] else "active"),
        dead_reason=dead.get(s.id),
    ) for s in sessions]


@router.get(HUMAN + "/sessions", response_model=list[CollaborationSessionOut])
async def list_collaboration_sessions(
    owner: tuple = Depends(get_collaboration_owner), db: AsyncSession = Depends(get_db),
):
    rows = (await db.scalars(select(RemoteCollaborationSession).order_by(
        RemoteCollaborationSession.created_at.desc()).limit(50))).all()
    return await _out(db, list(rows))


@router.post(HUMAN + "/sessions", response_model=CollaborationSessionOut, status_code=status.HTTP_201_CREATED)
async def open_collaboration_session(
    payload: CollaborationSessionCreate,
    owner: tuple = Depends(get_collaboration_owner),
    db: AsyncSession = Depends(get_db),
):
    principal, user_session = owner
    refuse_literal_secret(payload.operation)
    # Task first: completion holds it FOR UPDATE and may create a reply whose
    # FK needs KEY SHARE on Agent. Taking Agent FOR UPDATE first deadlocks that
    # finalizer against this opening's later task lock.
    demand = await db.scalar(select(AgentDemand).where(AgentDemand.number == payload.message_number)
                             .with_for_update(read=True).execution_options(populate_existing=True))
    await require_agent_access_active(db)
    # Serializes openings for one agent; the partial unique index backs it up.
    agent = await db.scalar(select(Agent).where(Agent.id == payload.agent_id).with_for_update()
                            .execution_options(populate_existing=True))
    if agent is None or not agent.is_active or agent.status != "active":
        raise HTTPException(404, {"code": "AGENT_NOT_FOUND", "message": "Active agent not found"})
    require_coding_agent(agent)
    if demand is None or demand.target_agent_id != agent.id or demand.origin_type != "task" or demand.status == "archived":
        raise HTTPException(422, {"code": "TASK_NOT_ADDRESSED_TO_AGENT",
                                  "message": f"Message #{payload.message_number} is not a task addressed to {agent.name}"})
    require_running_remote_task(demand)
    if not demand.agent_run_id:
        raise HTTPException(403, {"code": "TASK_NOT_RUNNING", "message": "This task has no running dispatch"})
    server = await db.get(Server, payload.server_id)
    if server is None:
        raise HTTPException(404, "Machine not found")
    await host._check_task_maintenance_scope(db, demand, None, [server])
    await require_direct(db, agent.id, [server], elevation=payload.allow_elevation, lock=True)
    _not_runnable(server)

    now = _now()
    existing = (await db.scalars(select(RemoteCollaborationSession).where(
        RemoteCollaborationSession.agent_id == agent.id, RemoteCollaborationSession.status == "active",
    ).with_for_update())).all()
    for old in existing:
        reason = await _dead_reason(db, old)
        if reason is None:
            raise HTTPException(409, {"code": "COLLABORATION_SESSION_ALREADY_ACTIVE",
                                      "message": f"{agent.name} already has an active collaborative session; end it first",
                                      "session_id": str(old.id)})
        old.status, old.ended_at, old.ended_by, old.end_reason = "ended", now, "system", reason
        revoked = await revoke_unused_commands(db, old.id)
        audit_session(db, old, "remote_collaboration_ended", "system",
               {"agent": agent.name, "end_reason": reason, "revoked_commands": revoked})
    await db.flush()

    session = RemoteCollaborationSession(
        owner_user_id=principal.principal_id, user_session_id=user_session.id, agent_id=agent.id,
        agent_demand_id=demand.id, agent_run_id=demand.agent_run_id, server_id=server.id,
        operation=payload.operation, allow_elevation=payload.allow_elevation, status="active",
        expires_at=now + timedelta(minutes=payload.duration_minutes),
    )
    db.add(session)
    await db.flush()
    audit_session(db, session, "remote_collaboration_opened", principal.display_name, {
        "agent": agent.name, "agent_id": str(agent.id), "message_number": demand.number,
        "agent_run_id": demand.agent_run_id, "server": server.name, "operation": payload.operation,
        "allow_elevation": payload.allow_elevation, "expires_at": session.expires_at.isoformat(),
    })
    db.add(Notification(source="system", severity="warning", title="Sessão colaborativa aberta",
                        message=(f"{principal.display_name} abriu uma sessão colaborativa de {agent.name} em "
                                 f"{server.name} (tarefa #{demand.number}): {payload.operation}"),
                        event_key=f"remote-collaboration:opened:{session.id}", occurred_at=now))
    await db.commit()
    await db.refresh(session)
    return (await _out(db, [session]))[0]


@router.post(HUMAN + "/sessions/{session_id}/commands", response_model=CollaborationCommandOut,
             status_code=status.HTTP_201_CREATED)
async def authorize_collaboration_command(
    session_id: uuid.UUID,
    payload: CollaborationCommandCreate,
    owner: tuple = Depends(get_collaboration_owner),
    db: AsyncSession = Depends(get_db),
):
    principal, _ = owner
    refuse_literal_secret(payload.command)
    await require_agent_access_active(db)
    # Opening and execution lock agent before session. Keep the same order so
    # authorizing a command cannot deadlock with a concurrent session opening.
    agent = await db.scalar(select(Agent).join(
        RemoteCollaborationSession, RemoteCollaborationSession.agent_id == Agent.id).where(
        RemoteCollaborationSession.id == session_id).with_for_update(read=True, of=Agent)
        .execution_options(populate_existing=True))
    session = require_session_current(await _locked_session(db, session_id))
    require_coding_agent(agent)
    await require_owner_valid(db, configured_owner(), session)
    if not await owner_session_live(db, session):
        raise refuse("COLLABORATION_OWNER_SESSION_ENDED", "The owner's session that opened this collaboration has ended.")
    demand = await db.get(AgentDemand, session.agent_demand_id, populate_existing=True)
    require_demand_bound(session, demand)
    require_running_remote_task(demand)
    server = await db.get(Server, session.server_id, populate_existing=True)
    if server is None:
        raise refuse("COLLABORATION_MACHINE_MISMATCH", "The session's machine no longer exists.")
    await host._check_task_maintenance_scope(db, demand, None, [server])
    await require_direct(db, session.agent_id, [server],
                         elevation=payload.allow_elevation or looks_elevated(payload.command), lock=True)
    _not_runnable(server, payload.shell)
    if payload.allow_elevation and not session.allow_elevation:
        raise HTTPException(422, {"code": "ELEVATION_NOT_ALLOWED",
                                  "message": "This session was opened without elevation"})
    if looks_elevated(payload.command) and not payload.allow_elevation:
        raise HTTPException(422, {"code": "ELEVATION_NOT_ALLOWED",
                                  "message": "This command looks like elevation; authorize it with allow_elevation"})
    entry = RemoteCollaborationCommand(
        session_id=session.id, command=payload.command, shell=payload.shell,
        command_sha256=command_sha256(payload.command), allow_elevation=payload.allow_elevation,
        authorized_by=principal.display_name, status="authorized",
    )
    db.add(entry)
    await db.flush()
    audit_session(db, session, "remote_collaboration_command_authorized", principal.display_name, {
        "command_id": str(entry.id), "command_sha256": entry.command_sha256, "shell": entry.shell,
        "allow_elevation": entry.allow_elevation,
        # The operation is the owner's declared purpose, not a machine-checked
        # scope: what binds is his byte-for-byte authorization of this command,
        # recorded here against the purpose he gave (review #42352).
        "operation": session.operation,
    })
    await db.commit()
    await db.refresh(entry)
    return CollaborationCommandOut.model_validate(entry)


@router.post(HUMAN + "/sessions/{session_id}/commands/{command_id}:revoke", response_model=CollaborationCommandOut)
async def revoke_collaboration_command(
    session_id: uuid.UUID,
    command_id: uuid.UUID,
    owner: tuple = Depends(get_collaboration_owner),
    db: AsyncSession = Depends(get_db),
):
    principal, _ = owner
    session = await _locked_session(db, session_id)
    entry = await db.scalar(select(RemoteCollaborationCommand).where(
        RemoteCollaborationCommand.id == command_id, RemoteCollaborationCommand.session_id == session.id,
    ).with_for_update())
    if entry is None:
        raise HTTPException(404, "Authorized command not found")
    if entry.status != "authorized":
        raise HTTPException(409, {"code": "COMMAND_NOT_REVOCABLE", "message": f"This command is already {entry.status}"})
    entry.status = "revoked"
    audit_session(db, session, "remote_collaboration_command_revoked", principal.display_name,
           {"command_id": str(entry.id), "command_sha256": entry.command_sha256})
    await db.commit()
    await db.refresh(entry)
    return CollaborationCommandOut.model_validate(entry)


@router.post(HUMAN + "/sessions/{session_id}:end", response_model=CollaborationSessionOut)
async def end_collaboration_session(
    session_id: uuid.UUID,
    payload: CollaborationEnd | None = None,
    owner: tuple = Depends(get_collaboration_owner),
    db: AsyncSession = Depends(get_db),
):
    """FOR UPDATE on the session: a command being recorded (holding it FOR SHARE)
    finishes first; the next one sees the session ended."""
    principal, _ = owner
    reason = ((payload.reason if payload else None) or "").strip() or None
    if reason:
        refuse_literal_secret(reason)
    session = await _locked_session(db, session_id)
    if session.status != "active":
        raise HTTPException(409, {"code": "COLLABORATION_SESSION_NOT_ACTIVE", "message": "This session already ended"})
    now = _now()
    session.status, session.ended_at, session.ended_by = "ended", now, principal.display_name
    session.end_reason = reason or "owner_ended"
    revoked = await revoke_unused_commands(db, session.id)
    agent_name = await db.scalar(select(Agent.name).where(Agent.id == session.agent_id))
    audit_session(db, session, "remote_collaboration_ended", principal.display_name,
           {"agent": agent_name, "end_reason": session.end_reason, "revoked_commands": revoked})
    db.add(Notification(source="system", severity="info", title="Sessão colaborativa encerrada",
                        message=f"{principal.display_name} encerrou a sessão colaborativa de {agent_name}.",
                        event_key=f"remote-collaboration:ended:{session.id}", occurred_at=now))
    await db.commit()
    await db.refresh(session)
    return (await _out(db, [session]))[0]


@router.post("/api/v1/host-executions/agent/collaborative-commands", response_model=HostExecutionDetail,
             status_code=status.HTTP_201_CREATED)
async def run_collaborative_command(
    payload: CollaborativeCommandRun,
    principal: ActorPrincipal = Depends(get_maintenance_agent),
    db: AsyncSession = Depends(get_db),
):
    configured_owner()
    refuse_literal_secret(payload.command)
    refuse_literal_secret(payload.reason)
    checks = dict(principal=principal, session_id=payload.session_id, command_id=payload.command_id,
                  command=payload.command, shell=payload.shell, message_number=payload.message_number,
                  server_ids=payload.server_ids)
    found = await require_collaboration(db, **checks, lock=False)
    server_id, server_name = found.server.id, found.server.name
    # The unlocked pass held the task FOR SHARE: release it before the readiness
    # probe (network calls), or task completion/reprocessing would wait on them.
    # The locked pass below re-validates everything.
    await db.rollback()
    readiness = await host._agent_readiness(db)
    await db.rollback()
    if not readiness.get(server_id, (False, ""))[0]:
        raise HTTPException(409, {"code": "LOGIN_NOT_READY", "machines": [server_name],
                                  "message": f"ForgeHub has no working login on: {server_name}"})

    # Decided under locks, released by launch_execution's commit: logout, end,
    # revocation, task completion and pause wait for this command to be recorded,
    # and two calls can't both consume the same authorization.
    found = await require_collaboration(db, **checks, lock=True)
    if found.server.id in await host.busy_server_ids(db):
        await db.rollback()
        raise HTTPException(409, {"code": "MACHINE_BUSY", "machines": [found.server.name],
                                  "message": f"Already running another command, try again later: {found.server.name}"})
    # Under the same locks: anything launch_execution would mark `skipped` (access
    # turned off, no login/address, shell vs OS) is refused here, so the
    # authorization is never spent on a run that doesn't happen.
    if reason := machine_not_runnable(found.server, payload.shell):
        name = found.server.name
        await db.rollback()
        raise HTTPException(409, {"code": "MACHINE_NOT_RUNNABLE", "machines": [name],
                                  "message": f"{name} can't run this command now: {reason}"})
    session, entry, demand = found.session, found.command, found.demand

    async def consume(execution) -> None:
        # Same transaction as the execution: single use even under a race.
        entry.status, entry.used_at, entry.execution_id = "used", _now(), execution.id
        audit_session(db, session, "remote_collaboration_command_run", principal.display_name, {
            "command_id": str(entry.id), "command_sha256": entry.command_sha256, "execution_id": str(execution.id),
            "execution_command_sha256": command_sha256(execution.command),
            "server_id": str(session.server_id), "message_number": demand.number,
            "agent_run_id": demand.agent_run_id, "owner_user_id": str(found.owner_id),
        })

    execution = await host.launch_execution(
        db, servers=[found.server], command=payload.command, shell=payload.shell,
        timeout_seconds=payload.timeout_seconds, actor=principal.display_name, target_summary=found.server.name,
        trigger="agent", agent_id=found.agent.id, agent_demand_id=demand.id, reason=payload.reason,
        direct_access=found.direct_access, before_commit=consume,
    )
    return await host._detail(db, execution)

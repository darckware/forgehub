"""Fail-closed enforcement of collaborative execution in an active session with
Marcelo (docs/architecture/REMOTE_ACCESS_RULE.md, "Execução colaborativa
autorizada em sessão ativa"). Off unless settings.REMOTE_COLLABORATION_ENABLED
and a valid REMOTE_COLLABORATION_OWNER_USER_ID. This gate applies only to the
collaborative API; it does not govern the separate authorized direct development
mode in Foundation's 2026-11-14 policy.

`require_collaboration` is the one gate an agent command passes. It re-reads
every binding on each call -- nothing is cached -- so the session dies with the
first of: Marcelo's browser session ending (logout, revocation, timeout), the
task's run finishing or being replaced, expiry, the global pause, or an explicit
end. Any failure is a 403 with its own code and nothing runs.
"""
import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import settings
from app.core.maintenance_proposals import looks_elevated
from app.core.remote_authority import (
    require_agent_access_active, require_direct, require_remote_task_credential,
)
from app.db.models.agent import Agent, AgentServiceCredential
from app.db.models.governance import AuditEvent
from app.db.models.demand import AgentDemand
from app.db.models.remote_collaboration import RemoteCollaborationCommand, RemoteCollaborationSession
from app.db.models.server import Server
from app.db.models.user import User
from app.db.models.user_session import UserSession

SESSION_ENTITY = "remote_collaboration_session"
CODING_RUNTIMES = frozenset({"claude", "codex", "agy"})


def require_coding_agent(agent: Agent | None) -> None:
    """Collaboration never extends the exception to Hermes or unknown runtimes."""
    if agent is None or not agent.is_active or agent.status != "active" or agent.runtime_type not in CODING_RUNTIMES:
        raise refuse("COLLABORATION_AGENT_INELIGIBLE", "Only active claude/codex/agy coding agents may collaborate.")


def command_sha256(command: str) -> str:
    return hashlib.sha256(command.encode("utf-8")).hexdigest()


def refuse(code: str, message: str, status: int = 403) -> HTTPException:
    return HTTPException(status, {"code": code, "message": message + " Nothing was run."})


def configured_owner() -> uuid.UUID:
    """The owner's UUID, or 403 COLLABORATION_DISABLED: switch off, owner empty or invalid."""
    if not settings.REMOTE_COLLABORATION_ENABLED:
        raise refuse("COLLABORATION_DISABLED", "Collaborative execution is not enabled in ForgeHub.")
    try:
        return uuid.UUID(str(settings.REMOTE_COLLABORATION_OWNER_USER_ID).strip())
    except ValueError:
        raise refuse("COLLABORATION_DISABLED", "Collaborative execution has no valid owner configured.") from None


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def owner_session_live(db, session: RemoteCollaborationSession, lock: bool = False) -> bool:
    """The owner's browser session bound at opening is still active and in date.
    `lock` holds it FOR SHARE, so a logout waits for a command being recorded.
    A NULL binding (the browser session row was purged) is never live."""
    if session.user_session_id is None:
        return False
    query = select(UserSession).where(UserSession.id == session.user_session_id).execution_options(
        populate_existing=True)
    row = await db.scalar(query.with_for_update(read=True) if lock else query)
    return bool(row and row.user_id == session.owner_user_id and row.is_active and row.expires_at > _now())


async def require_owner_valid(db, owner_id: uuid.UUID, session: RemoteCollaborationSession) -> None:
    if session.owner_user_id != owner_id:
        raise refuse("COLLABORATION_OWNER_MISMATCH", "This session was not opened by the configured owner.")
    owner = await db.get(User, session.owner_user_id, populate_existing=True)
    if owner is None or not owner.is_active or not owner.is_admin:
        raise refuse("COLLABORATION_OWNER_MISMATCH", "The session owner is no longer an active admin.")


def require_session_current(session: RemoteCollaborationSession | None) -> RemoteCollaborationSession:
    if session is None or session.status != "active":
        raise refuse("COLLABORATION_SESSION_NOT_ACTIVE", "This collaborative session is not active.")
    if session.user_session_id is None or session.server_id is None:
        # Its owner's browser session or its machine was deleted (ON DELETE SET NULL).
        raise refuse("COLLABORATION_SESSION_NOT_ACTIVE", "This collaborative session lost its owner session or machine.")
    if session.expires_at <= _now():
        raise refuse("COLLABORATION_SESSION_EXPIRED", "This collaborative session has expired.")
    return session


def machine_not_runnable(server: Server, shell: str | None = None) -> str | None:
    """Why launch_execution would mark this machine `skipped` -- the very
    `skip_reason` it uses, minus "busy", which callers judge separately. With no
    shell (opening a session) only the shell-independent conditions count."""
    from app.api.routes.host_execution import skip_reason
    if shell is None:
        return skip_reason(server, "sh", set(), shell_agnostic=True)
    return skip_reason(server, shell, set())


def require_demand_bound(session: RemoteCollaborationSession, demand: AgentDemand | None) -> None:
    """The task is the session's own and still carries the run it was opened with."""
    if demand is None or demand.id != session.agent_demand_id:
        raise refuse("COLLABORATION_RUN_MISMATCH", "This task is not the one bound to the session.")
    if demand.origin_type != "task" or demand.target_agent_id != session.agent_id or demand.status == "archived":
        raise refuse("COLLABORATION_RUN_MISMATCH", "This task is no longer a task addressed to the session's agent.")
    if not demand.agent_run_id or demand.agent_run_id != session.agent_run_id:
        raise refuse("COLLABORATION_RUN_MISMATCH", "The task's run is not the one the session was opened with.")


@dataclass
class Collaboration:
    session: RemoteCollaborationSession
    command: RemoteCollaborationCommand
    demand: AgentDemand
    server: Server
    agent: Agent
    owner_id: uuid.UUID
    direct_access: dict[uuid.UUID, uuid.UUID]


async def require_collaboration(
    db, *, principal, session_id, command_id, command: str, shell: str, message_number: int, server_ids, lock: bool,
) -> Collaboration:
    """Every check of the rule, in one place. Rows are read in lock order (task,
    pause, agent, machine, session, owner session, credential, grant, command) and judged afterwards; on the
    locked pass they stay locked until the caller's commit."""
    owner_id = configured_owner()

    # Completion and reprocessing lock the task exclusively: held FOR SHARE on
    # both passes (as host._check_against_task does), the run cannot end while
    # an admitted command is being recorded.
    demand = await db.scalar(select(AgentDemand).where(AgentDemand.number == message_number)
                             .with_for_update(read=True).execution_options(populate_existing=True))
    await require_agent_access_active(db, lock=lock)

    # Lock the agent before the collaboration session, matching session opening
    # (agent -> session) and direct configuration (agent -> grants). A runtime
    # change or removal from the direct list cannot pass the final check.
    agent_query = select(Agent).where(Agent.id == principal.principal_id).execution_options(populate_existing=True)
    agent = await db.scalar(agent_query.with_for_update(read=True) if lock else agent_query)

    session_query = select(RemoteCollaborationSession).where(
        RemoteCollaborationSession.id == session_id).execution_options(populate_existing=True)
    if lock:
        # The machine row first, then the session. `key_share=True` without
        # `read=True` is FOR NO KEY UPDATE in SQLAlchemy (not FOR KEY SHARE), the
        # same lock run_direct_command takes: held until launch_execution's
        # commit, it blocks any concurrent edit of the machine (login, address,
        # key ref) and conflicts with run_direct_command's and another
        # collaborative call's lock, so neither can pass `busy_server_ids` on this
        # machine at the same time (the script route takes no machine lock)
        # (test_locked_pass_blocks_machine_edits_and_other_launches_until_commit).
        peek = await db.scalar(select(RemoteCollaborationSession.server_id).where(
            RemoteCollaborationSession.id == session_id))
        if peek is not None:
            await db.scalars(select(Server.id).where(Server.id == peek).with_for_update(key_share=True))
        session_query = session_query.with_for_update(read=True)
    session = require_session_current(await db.scalar(session_query))
    await require_owner_valid(db, owner_id, session)
    if not await owner_session_live(db, session, lock):
        raise refuse("COLLABORATION_OWNER_SESSION_ENDED", "The owner's session that opened this collaboration has ended.")

    if (principal.principal_type != "agent" or principal.credential_id is None
            or principal.principal_id != session.agent_id):
        raise refuse("COLLABORATION_AGENT_MISMATCH", "This session belongs to another agent.")
    require_coding_agent(agent)

    require_demand_bound(session, demand)
    # A principal authenticated before readiness is only a snapshot. Re-read
    # its exact credential on both passes; FOR SHARE on the final pass prevents
    # revocation, deletion, or rebinding until the execution recording commits.
    require_remote_task_credential(principal, demand)
    credential_query = select(AgentServiceCredential).where(
        AgentServiceCredential.id == principal.credential_id).execution_options(populate_existing=True)
    credential = await db.scalar(credential_query.with_for_update(read=True) if lock else credential_query)
    if (credential is None or credential.agent_id != agent.id
            or credential.label != f"dispatch:{demand.agent_run_id}"
            or credential.revoked_at is not None
            or (credential.expires_at is not None and credential.expires_at <= _now())):
        raise refuse("TASK_CREDENTIAL_MISMATCH", "The credential issued to this task dispatch is no longer valid.")

    wanted = [uuid.UUID(str(s)) for s in server_ids]
    if wanted != [session.server_id]:
        raise refuse("COLLABORATION_MACHINE_MISMATCH", "Only the machine authorized for this session may be targeted.")
    server = await db.get(Server, session.server_id, populate_existing=True)
    if server is None:
        raise refuse("COLLABORATION_MACHINE_MISMATCH", "The session's machine no longer exists.")
    # The collaborative session narrows an existing grant; it never grants
    # machine access itself. Re-read expiry, revocation, listing and scope on
    # both passes, holding the grant through launch_execution's commit.
    from app.api.routes import host_execution as host
    await host._check_against_task(
        db, agent, SimpleNamespace(message_number=message_number), None, [server], principal=principal)
    selected = await require_direct(db, agent.id, [server], elevation=looks_elevated(command), lock=lock)

    command_query = select(RemoteCollaborationCommand).where(
        RemoteCollaborationCommand.id == command_id,
        RemoteCollaborationCommand.session_id == session.id,
    ).execution_options(populate_existing=True)
    entry = await db.scalar(command_query.with_for_update() if lock else command_query)
    if (entry is None or entry.status != "authorized" or entry.command != command or entry.shell != shell
            or entry.command_sha256 != command_sha256(command)):
        raise refuse("COLLABORATION_COMMAND_NOT_AUTHORIZED",
                     "This exact command is not an unused authorization of this session.")
    if looks_elevated(command) and not (entry.allow_elevation and session.allow_elevation):
        raise refuse("ELEVATION_NOT_ALLOWED",
                     "This command looks like elevation and was not authorized with it.")
    return Collaboration(session=session, command=entry, demand=demand, server=server, agent=agent,
                         owner_id=owner_id, direct_access={sid: grant.id for sid, grant in selected.items()})


def audit_session(db, session: RemoteCollaborationSession, event: str, actor: str, payload: dict) -> None:
    """The session's own trail plus one line in the machine's history. Never a secret."""
    body = {"session_id": str(session.id), **payload}
    db.add(AuditEvent(entity_type=SESSION_ENTITY, entity_id=session.id, event_type=event, actor=actor, payload=body))
    if session.server_id is not None:
        db.add(AuditEvent(entity_type="server", entity_id=session.server_id, event_type=event, actor=actor,
                          payload=body))


async def revoke_unused_commands(db, session_id: uuid.UUID) -> list[str]:
    rows = (await db.scalars(select(RemoteCollaborationCommand).where(
        RemoteCollaborationCommand.session_id == session_id, RemoteCollaborationCommand.status == "authorized",
    ).with_for_update())).all()
    for row in rows:
        row.status = "revoked"
    return [str(r.id) for r in rows]


async def end_sessions_for_logout(db, token_hash: str, actor: str) -> None:
    """Marks the collaborative sessions bound to this browser session ended
    (`owner_logged_out`). Called by /auth/logout *before* it deactivates the
    UserSession, so locks are taken in the same order as an agent command
    (collaborative session, then browser session). Even without this, the
    validator refuses once the browser session is inactive."""
    rows = (await db.scalars(select(RemoteCollaborationSession).join(
        UserSession, UserSession.id == RemoteCollaborationSession.user_session_id).where(
        UserSession.token_hash == token_hash, RemoteCollaborationSession.status == "active",
    ).with_for_update(of=RemoteCollaborationSession))).all()
    now = _now()
    for session in rows:
        session.status, session.ended_at, session.ended_by, session.end_reason = "ended", now, actor, "owner_logged_out"
        revoked = await revoke_unused_commands(db, session.id)
        audit_session(db, session, "remote_collaboration_ended", actor,
                      {"end_reason": "owner_logged_out", "revoked_commands": revoked})

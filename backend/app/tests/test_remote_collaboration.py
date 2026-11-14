"""Collaborative execution in an active session with Marcelo: real FastAPI and
test Postgres; the bridge is simulated. The switch is flipped per test with
monkeypatch -- production keeps it off."""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, or_, select, update

from app.api.routes import host_execution as host
from app.core import host_exec_runner
from app.core.config import settings
from app.core.remote_authority import CONTROL_ID, DIRECT_ACTION, DIRECT_NO_EXPIRY, agent_access_control
from app.core.security import create_access_token
from app.core.user_session import session_hash
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent, AgentServiceCredential
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent, AuthorityDelegation
from app.db.models.host_execution import HostExecution, HostExecutionResult
from app.db.models.notification import Notification
from app.db.models.remote_collaboration import RemoteCollaborationCommand, RemoteCollaborationSession
from app.db.models.server import Server
from app.db.models.user import User
from app.db.models.user_session import UserSession
from app.main import app
from app.tests.fixtures.managed_machine import mark_managed_machine

HUMAN = "/api/v1/remote-access/collaboration"
RUN = "/api/v1/host-executions/agent/collaborative-commands"
DIRECT_RUN = "/api/v1/host-executions/agent/commands"
CONTROL = "/api/v1/remote-access/direct/control"


def _session_row(user, live=True):
    sid = secrets.token_urlsafe(32)
    row = UserSession(user_id=user.id, token_hash=session_hash(sid), is_active=live,
                      expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    return sid, row


def _token(user, sid=None):
    claims = {"sid": sid} if sid else None
    return {"Authorization": "Bearer " + create_access_token(user.username, extra_claims=claims)}


def _agent_token(tag, name):
    return f"agt_collab_{name}_{tag}"


@pytest_asyncio.fixture
async def ctx(monkeypatch):
    tag = uuid.uuid4().hex
    run_id, other_run = "collab-run-" + tag[:16], "collab-other-" + tag[:16]
    tokens = {k: _agent_token(tag, k) for k in ("agent", "manual", "other")}
    async with AsyncSessionLocal() as db:
        owner = User(username="collab-owner-" + tag, hashed_password="unused", is_admin=True)
        admin = User(username="collab-admin-" + tag, hashed_password="unused", is_admin=True)
        agent = Agent(name="collab-agent-" + tag, agent_type="executor", runtime_type="claude", direct_access_allowed=True)
        other = Agent(name="collab-other-" + tag, agent_type="executor", runtime_type="codex", direct_access_allowed=True)
        lab = mark_managed_machine(Server(name="collab-lab-" + tag, ip_address="192.0.2.61", os_family="linux",
                                          environment="lab"))
        lab2 = mark_managed_machine(Server(name="collab-lab2-" + tag, ip_address="192.0.2.62", os_family="linux",
                                           environment="lab"))
        db.add_all([owner, admin, agent, other, lab, lab2])
        await db.flush()
        task = AgentDemand(from_agent="t", from_agent_id=agent.id, target_agent_id=agent.id, subject="t", body="t",
                           origin_type="task", dispatch_status="running", agent_run_id=run_id)
        other_task = AgentDemand(from_agent="t", from_agent_id=other.id, target_agent_id=other.id, subject="o",
                                 body="t", origin_type="task", dispatch_status="running", agent_run_id=other_run)
        owner_sid, owner_session = _session_row(owner)
        admin_sid, admin_session = _session_row(admin)
        db.add_all([task, other_task, owner_session, admin_session])
        for row, label, token in ((agent, f"dispatch:{run_id}", tokens["agent"]), (agent, "manual", tokens["manual"]),
                                  (other, f"dispatch:{other_run}", tokens["other"])):
            db.add(AgentServiceCredential(agent_id=row.id, label=label,
                                          token_hash=hashlib.sha256(token.encode()).hexdigest()))
        grant = AuthorityDelegation(
            grantor_user_id=owner.id, grantee_type="agent", grantee_id=agent.id,
            allowed_actions=[DIRECT_ACTION], servers=[str(lab.id), str(lab2.id)],
            valid_from=datetime.now(timezone.utc) - timedelta(minutes=1), expires_at=DIRECT_NO_EXPIRY,
            open_ended=True, allow_elevation=True,
        )
        db.add(grant)
        db.add(AuthorityDelegation(
            grantor_user_id=owner.id, grantee_type="agent", grantee_id=other.id,
            allowed_actions=[DIRECT_ACTION], servers=[str(lab.id), str(lab2.id)],
            valid_from=datetime.now(timezone.utc) - timedelta(minutes=1), expires_at=DIRECT_NO_EXPIRY,
            open_ended=True, allow_elevation=True,
        ))
        await db.commit()
        credential_id = await db.scalar(select(AgentServiceCredential.id).where(
            AgentServiceCredential.agent_id == agent.id, AgentServiceCredential.label == f"dispatch:{run_id}"))

    monkeypatch.setattr(settings, "REMOTE_COLLABORATION_ENABLED", True)
    monkeypatch.setattr(settings, "REMOTE_COLLABORATION_OWNER_USER_ID", str(owner.id))
    machines = [lab, lab2]

    async def readiness(db):
        return {m.id: (True, "complete") for m in machines}

    calls = []

    async def remote(*args):
        calls.append(args)
        return dict(exit_code=0, stdout="ok\n", stderr="", duration_ms=1, failure=None)

    monkeypatch.setattr(host, "_agent_readiness", readiness)
    monkeypatch.setattr(host_exec_runner, "call_bridge_exec", remote)
    agents = [agent.id, other.id]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield SimpleNamespace(
            client=client, owner=owner, admin=admin, agent=agent, grant=grant, other=other, lab=lab, lab2=lab2, task=task,
            other_task=other_task, run_id=run_id, credential_id=credential_id, owner_session=owner_session, calls=calls, tag=tag,
            owner_h=_token(owner, owner_sid), owner_nosid_h=_token(owner), admin_h=_token(admin, admin_sid),
            agent_h={"Authorization": "Bearer " + tokens["agent"]},
            manual_h={"Authorization": "Bearer " + tokens["manual"]},
            other_h={"Authorization": "Bearer " + tokens["other"]},
        )
    for pending in list(host_exec_runner._running.values()):
        await pending
    async with AsyncSessionLocal() as db:
        session_ids = (await db.scalars(select(RemoteCollaborationSession.id).where(
            RemoteCollaborationSession.agent_id.in_(agents)))).all()
        run_ids = (await db.scalars(select(HostExecution.id).where(HostExecution.agent_id.in_(agents)))).all()
        task_ids = list((await db.scalars(select(AgentDemand.id).where(AgentDemand.target_agent_id.in_(agents)))).all())
        await db.execute(delete(Notification).where(Notification.event_key.in_([f"demand-reply:{tid}" for tid in task_ids])))
        ids = [m.id for m in machines]
        if session_ids:
            await db.execute(delete(Notification).where(or_(*[
                Notification.event_key.like(f"remote-collaboration:%:{s}") for s in session_ids])))
        await db.execute(delete(AuditEvent).where(or_(
            AuditEvent.entity_id.in_(list(session_ids) + list(run_ids) + ids + agents + task_ids),
            AuditEvent.actor.in_([owner.username, admin.username]))))
        await db.execute(delete(RemoteCollaborationSession).where(RemoteCollaborationSession.agent_id.in_(agents)))
        await db.execute(delete(HostExecution).where(HostExecution.agent_id.in_(agents)))
        await db.execute(delete(AgentServiceCredential).where(AgentServiceCredential.agent_id.in_(agents)))
        await db.execute(delete(AgentDemand).where(AgentDemand.target_agent_id.in_(agents)))
        await db.execute(delete(Server).where(Server.id.in_(ids)))
        await db.execute(delete(AuthorityDelegation).where(AuthorityDelegation.grantee_id.in_(agents)))
        await db.execute(delete(Agent).where(Agent.id.in_(agents)))
        await db.execute(delete(User).where(User.id.in_([owner.id, admin.id])))
        await db.commit()


@pytest_asyncio.fixture
async def pausable(ctx):
    """Always leaves the switch active: the database is shared by the whole suite."""
    yield ctx
    async with AsyncSessionLocal() as db:
        control = await agent_access_control(db)
        control.paused, control.paused_at, control.paused_by, control.reason = False, None, None, None
        await db.execute(delete(AuditEvent).where(AuditEvent.entity_id == CONTROL_ID,
                                                  AuditEvent.actor == ctx.owner.username))
        await db.execute(delete(Notification).where(Notification.event_key.like("agent-remote-access:%"),
                                                    Notification.message.like(f"{ctx.owner.username}%")))
        await db.commit()


def code(response):
    detail = response.json()["detail"]
    return detail["code"] if isinstance(detail, dict) else detail


async def open_session(c, *, agent=None, task=None, server=None, expect=201, **extra):
    body = {"agent_id": str((agent or c.agent).id), "message_number": (task or c.task).number,
            "server_id": str((server or c.lab).id), "operation": "Restart the web service", **extra}
    r = await c.client.post(HUMAN + "/sessions", json=body, headers=c.owner_h)
    assert r.status_code == expect, r.text
    return r.json()


async def authorize(c, session, command="uname -a", expect=201, **extra):
    r = await c.client.post(f"{HUMAN}/sessions/{session['id']}/commands", json={"command": command, **extra},
                            headers=c.owner_h)
    assert r.status_code == expect, r.text
    return r.json()


def run_body(c, session, entry, **extra):
    return {"session_id": session["id"], "command_id": entry["id"], "command": entry["command"],
            "shell": entry["shell"], "message_number": c.task.number, "server_ids": [session["server_id"]],
            "reason": "Restart requested by Marcelo", **extra}


async def run(c, session, entry, headers=None, **extra):
    return await c.client.post(RUN, json=run_body(c, session, entry, **extra), headers=headers or c.agent_h)


async def finished(execution_id):
    pending = host_exec_runner._running.get(uuid.UUID(execution_id))
    if pending:
        await pending


async def command_row(entry):
    async with AsyncSessionLocal() as db:
        return await db.get(RemoteCollaborationCommand, uuid.UUID(entry["id"]))


async def session_row(session):
    async with AsyncSessionLocal() as db:
        return await db.get(RemoteCollaborationSession, uuid.UUID(session["id"]))


# --- the switch and the owner -------------------------------------------------

@pytest.mark.asyncio
async def test_disabled_switch_refuses_agent_and_human_routes(ctx, monkeypatch):
    c = ctx
    session = await open_session(c)
    entry = await authorize(c, session)
    for enabled, owner in ((False, str(c.owner.id)), (True, ""), (True, "not-a-uuid")):
        monkeypatch.setattr(settings, "REMOTE_COLLABORATION_ENABLED", enabled)
        monkeypatch.setattr(settings, "REMOTE_COLLABORATION_OWNER_USER_ID", owner)
        r = await run(c, session, entry)
        assert r.status_code == 403 and code(r) == "COLLABORATION_DISABLED"
        for response in (
            await c.client.get(HUMAN + "/sessions", headers=c.owner_h),
            await c.client.post(HUMAN + "/sessions", json={"agent_id": str(c.agent.id),
                "message_number": c.task.number, "server_id": str(c.lab.id), "operation": "x"}, headers=c.owner_h),
            await c.client.post(f"{HUMAN}/sessions/{session['id']}/commands", json={"command": "id"},
                                headers=c.owner_h),
            await c.client.post(f"{HUMAN}/sessions/{session['id']}:end", json={}, headers=c.owner_h),
        ):
            assert response.status_code == 403 and code(response) == "COLLABORATION_DISABLED"
    assert (await command_row(entry)).status == "authorized"
    assert c.calls == []


@pytest.mark.asyncio
async def test_only_the_owner_in_a_live_session_manages_sessions(ctx):
    c = ctx
    body = {"agent_id": str(c.agent.id), "message_number": c.task.number, "server_id": str(c.lab.id),
            "operation": "x"}
    # Another admin, even in a live session of his own.
    r = await c.client.post(HUMAN + "/sessions", json=body, headers=c.admin_h)
    assert r.status_code == 403 and code(r) == "COLLABORATION_OWNER_ONLY"
    # The owner's JWT without a session id.
    r = await c.client.post(HUMAN + "/sessions", json=body, headers=c.owner_nosid_h)
    assert r.status_code == 403 and code(r) == "COLLABORATION_OWNER_ONLY"
    assert (await c.client.get(HUMAN + "/sessions", headers=c.owner_nosid_h)).status_code == 403
    # The owner's JWT naming a session that isn't live (the middleware or the route refuses).
    r = await c.client.post(HUMAN + "/sessions", json=body, headers=_token(c.owner, "no-such-session"))
    assert r.status_code in (401, 403)
    # An agent credential never manages sessions.
    r = await c.client.post(HUMAN + "/sessions", json=body, headers=c.agent_h)
    assert r.status_code in (401, 403)
    async with AsyncSessionLocal() as db:
        assert not (await db.scalars(select(RemoteCollaborationSession).where(
            RemoteCollaborationSession.agent_id == c.agent.id))).all()


# --- the happy path and single use -------------------------------------------

@pytest.mark.asyncio
async def test_runs_exactly_the_authorized_command_once_and_audits_it(ctx):
    c = ctx
    session = await open_session(c)
    assert session["status"] == "active" and session["agent_run_id"] == c.run_id
    entry = await authorize(c, session)
    assert entry["status"] == "authorized"
    assert entry["command_sha256"] == hashlib.sha256(b"uname -a").hexdigest()

    r = await run(c, session, entry)
    assert r.status_code == 201, r.text
    data = r.json()
    await finished(data["id"])
    assert data["trigger"] == "agent" and data["reason"] == "Restart requested by Marcelo"
    assert len(c.calls) == 1
    used = await command_row(entry)
    assert used.status == "used" and str(used.execution_id) == data["id"] and used.used_at is not None
    async with AsyncSessionLocal() as db:
        execution = await db.get(HostExecution, uuid.UUID(data["id"]))
        assert execution.agent_id == c.agent.id and execution.agent_demand_id == c.task.id
        events = (await db.scalars(select(AuditEvent).where(
            AuditEvent.event_type == "remote_collaboration_command_run",
            AuditEvent.entity_id.in_([uuid.UUID(session["id"]), c.lab.id])))).all()
    assert {e.entity_type for e in events} == {"remote_collaboration_session", "server"}
    payload = events[0].payload
    assert payload["command_sha256"] == entry["command_sha256"] and payload["execution_id"] == data["id"]
    assert payload["message_number"] == c.task.number and payload["agent_run_id"] == c.run_id
    assert payload["owner_user_id"] == str(c.owner.id) and payload["server_id"] == str(c.lab.id)
    assert "command" not in payload

    again = await run(c, session, entry)
    assert again.status_code == 403 and code(again) == "COLLABORATION_COMMAND_NOT_AUTHORIZED"
    assert len(c.calls) == 1

    listed = (await c.client.get(HUMAN + "/sessions", headers=c.owner_h)).json()
    mine = next(s for s in listed if s["id"] == session["id"])
    assert [cmd["status"] for cmd in mine["commands"]] == ["used"]
    assert mine["message_number"] == c.task.number and mine["server_name"] == c.lab.name


@pytest.mark.asyncio
async def test_two_concurrent_calls_consume_the_command_once(ctx):
    import asyncio
    c = ctx
    session = await open_session(c)
    entry = await authorize(c, session)
    first, second = await asyncio.gather(run(c, session, entry), run(c, session, entry))
    statuses = sorted([first.status_code, second.status_code])
    assert statuses[0] == 201 and statuses[1] in (403, 409), (first.text, second.text)
    winner = first if first.status_code == 201 else second
    await finished(winner.json()["id"])
    assert len(c.calls) == 1
    assert str((await command_row(entry)).execution_id) == winner.json()["id"]


@pytest.mark.asyncio
async def test_command_must_match_text_shell_and_session(ctx):
    c = ctx
    session = await open_session(c)
    entry = await authorize(c, session)
    other_session = await open_session(c, agent=c.other, task=c.other_task, server=c.lab2)
    foreign = await authorize(c, other_session, "hostname")
    for change in ({"command": "uname -a "}, {"command": "uname -r"}, {"shell": "powershell"},
                   {"command_id": foreign["id"], "command": "hostname"}):
        r = await run(c, session, entry, **change)
        assert r.status_code == 403 and code(r) == "COLLABORATION_COMMAND_NOT_AUTHORIZED", change
    r = await run(c, session, entry, command_id=str(uuid.uuid4()))
    assert r.status_code == 403 and code(r) == "COLLABORATION_COMMAND_NOT_AUTHORIZED"
    assert c.calls == [] and (await command_row(entry)).status == "authorized"


@pytest.mark.asyncio
async def test_revoked_command_is_refused(ctx):
    c = ctx
    session = await open_session(c)
    entry = await authorize(c, session)
    r = await c.client.post(f"{HUMAN}/sessions/{session['id']}/commands/{entry['id']}:revoke", headers=c.owner_h)
    assert r.status_code == 200 and r.json()["status"] == "revoked"
    r = await run(c, session, entry)
    assert r.status_code == 403 and code(r) == "COLLABORATION_COMMAND_NOT_AUTHORIZED"
    again = await c.client.post(f"{HUMAN}/sessions/{session['id']}/commands/{entry['id']}:revoke",
                                headers=c.owner_h)
    assert again.status_code == 409


# --- machine, agent, credential, task and run ---------------------------------

@pytest.mark.asyncio
async def test_wrong_machine_is_refused(ctx):
    c = ctx
    session = await open_session(c)
    entry = await authorize(c, session)
    for machines in ([str(c.lab2.id)], [str(c.lab.id), str(c.lab2.id)]):
        r = await run(c, session, entry, server_ids=machines)
        assert r.status_code == 403 and code(r) == "COLLABORATION_MACHINE_MISMATCH"
    assert c.calls == []


@pytest.mark.asyncio
async def test_wrong_agent_or_non_dispatch_credential_is_refused(ctx):
    c = ctx
    session = await open_session(c)
    entry = await authorize(c, session)
    r = await run(c, session, entry, headers=c.other_h)
    assert r.status_code == 403 and code(r) == "COLLABORATION_AGENT_MISMATCH"
    r = await run(c, session, entry, headers=c.manual_h)
    assert r.status_code == 403 and code(r) == "TASK_CREDENTIAL_MISMATCH"
    assert c.calls == [] and (await command_row(entry)).status == "authorized"


@pytest.mark.asyncio
async def test_finished_task_or_changed_run_ends_the_session(ctx):
    c = ctx
    session = await open_session(c)
    entry = await authorize(c, session)
    async with AsyncSessionLocal() as db:
        await db.execute(update(AgentDemand).where(AgentDemand.id == c.task.id).values(dispatch_status="completed"))
        await db.commit()
    r = await run(c, session, entry)
    assert r.status_code == 403 and code(r) == "TASK_FINISHED"
    # A new run of the same task: its own credential is valid, but the session was opened for the old run.
    new_run = "collab-new-" + c.tag[:16]
    new_token = _agent_token(c.tag, "newrun")
    async with AsyncSessionLocal() as db:
        await db.execute(update(AgentDemand).where(AgentDemand.id == c.task.id).values(
            dispatch_status="running", agent_run_id=new_run))
        db.add(AgentServiceCredential(agent_id=c.agent.id, label=f"dispatch:{new_run}",
                                      token_hash=hashlib.sha256(new_token.encode()).hexdigest()))
        await db.commit()
    r = await run(c, session, entry, headers={"Authorization": "Bearer " + new_token})
    assert r.status_code == 403 and code(r) == "COLLABORATION_RUN_MISMATCH"
    # Another task of the agent is not the session's task either.
    r = await run(c, session, entry, message_number=c.other_task.number)
    assert r.status_code == 403 and code(r) == "COLLABORATION_RUN_MISMATCH"
    assert c.calls == []


# --- ending: logout, owner session, expiry, explicit end, pause ---------------

@pytest.mark.asyncio
async def test_owner_logout_ends_the_session_and_revokes_unused_commands(ctx):
    c = ctx
    session = await open_session(c)
    entry = await authorize(c, session)
    r = await c.client.post("/api/v1/auth/logout", headers=c.owner_h)
    assert r.status_code == 204, r.text
    row = await session_row(session)
    assert row.status == "ended" and row.end_reason == "owner_logged_out"
    assert (await command_row(entry)).status == "revoked"
    r = await run(c, session, entry)
    assert r.status_code == 403 and code(r) == "COLLABORATION_SESSION_NOT_ACTIVE"
    assert c.calls == []


@pytest.mark.asyncio
async def test_owner_session_revoked_or_timed_out_refuses(ctx):
    c = ctx
    session = await open_session(c)
    entry = await authorize(c, session)
    for values in ({"is_active": False}, {"is_active": True, "expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}):
        async with AsyncSessionLocal() as db:
            await db.execute(update(UserSession).where(UserSession.id == c.owner_session.id).values(**values))
            await db.commit()
        r = await run(c, session, entry)
        assert r.status_code == 403 and code(r) == "COLLABORATION_OWNER_SESSION_ENDED"
    assert c.calls == []


@pytest.mark.asyncio
async def test_owner_no_longer_admin_refuses(ctx):
    c = ctx
    session = await open_session(c)
    entry = await authorize(c, session)
    async with AsyncSessionLocal() as db:
        await db.execute(update(User).where(User.id == c.owner.id).values(is_admin=False))
        await db.commit()
    r = await run(c, session, entry)
    assert r.status_code == 403 and code(r) == "COLLABORATION_OWNER_MISMATCH"


@pytest.mark.asyncio
async def test_expired_session_is_refused(ctx):
    c = ctx
    session = await open_session(c, duration_minutes=1)
    entry = await authorize(c, session)
    async with AsyncSessionLocal() as db:
        await db.execute(update(RemoteCollaborationSession).where(
            RemoteCollaborationSession.id == uuid.UUID(session["id"])).values(
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
        await db.commit()
    r = await run(c, session, entry)
    assert r.status_code == 403 and code(r) == "COLLABORATION_SESSION_EXPIRED"
    r = await c.client.post(f"{HUMAN}/sessions/{session['id']}/commands", json={"command": "id"}, headers=c.owner_h)
    assert r.status_code == 403 and code(r) == "COLLABORATION_SESSION_EXPIRED"
    assert c.calls == []


@pytest.mark.asyncio
async def test_ended_session_refuses_and_revokes_unused_commands(ctx):
    c = ctx
    session = await open_session(c)
    entry = await authorize(c, session)
    r = await c.client.post(f"{HUMAN}/sessions/{session['id']}:end", json={"reason": "Done"}, headers=c.owner_h)
    assert r.status_code == 200, r.text
    ended = r.json()
    assert ended["status"] == "ended" and ended["end_reason"] == "Done" and ended["ended_by"] == c.owner.username
    assert [cmd["status"] for cmd in ended["commands"]] == ["revoked"]
    r = await run(c, session, entry)
    assert r.status_code == 403 and code(r) == "COLLABORATION_SESSION_NOT_ACTIVE"
    r = await c.client.post(f"{HUMAN}/sessions/{session['id']}/commands", json={"command": "id"}, headers=c.owner_h)
    assert r.status_code == 403 and code(r) == "COLLABORATION_SESSION_NOT_ACTIVE"
    again = await c.client.post(f"{HUMAN}/sessions/{session['id']}:end", json={}, headers=c.owner_h)
    assert again.status_code == 409
    async with AsyncSessionLocal() as db:
        history = (await db.scalars(select(AuditEvent).where(
            AuditEvent.entity_id == c.lab.id, AuditEvent.event_type == "remote_collaboration_ended"))).all()
    assert len(history) == 1
    assert c.calls == []


@pytest.mark.asyncio
async def test_global_pause_refuses(pausable):
    c = pausable
    session = await open_session(c)
    entry = await authorize(c, session)
    r = await c.client.post(CONTROL + ":pause", json={"reason": None}, headers=c.owner_h)
    assert r.status_code == 200, r.text
    r = await run(c, session, entry)
    assert r.status_code == 403 and code(r) == "AGENT_REMOTE_ACCESS_PAUSED"
    await open_session(c, agent=c.other, task=c.other_task, expect=403)
    r = await c.client.post(CONTROL + ":resume", headers=c.owner_h)
    assert r.status_code == 200
    r = await run(c, session, entry)
    assert r.status_code == 201, r.text
    await finished(r.json()["id"])


# --- elevation ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_elevation_needs_both_session_and_command(ctx):
    c = ctx
    plain = await open_session(c)
    # Authorization refuses elevation beyond the session, and an undeclared elevated command.
    await authorize(c, plain, "id", allow_elevation=True, expect=422)
    await authorize(c, plain, "sudo systemctl restart nginx", expect=422)
    # A row written past the human route (defence in depth): the agent gate refuses it too.
    async with AsyncSessionLocal() as db:
        row = RemoteCollaborationCommand(session_id=uuid.UUID(plain["id"]), command="sudo id", shell="sh",
                                         command_sha256=hashlib.sha256(b"sudo id").hexdigest(),
                                         allow_elevation=True, authorized_by="test")
        db.add(row)
        await db.commit()
        forged = {"id": str(row.id), "command": "sudo id", "shell": "sh"}
    r = await run(c, plain, forged)
    assert r.status_code == 403 and code(r) == "ELEVATION_NOT_ALLOWED"
    await c.client.post(f"{HUMAN}/sessions/{plain['id']}:end", json={}, headers=c.owner_h)

    elevated = await open_session(c, allow_elevation=True)
    async with AsyncSessionLocal() as db:
        row = RemoteCollaborationCommand(session_id=uuid.UUID(elevated["id"]), command="sudo id", shell="sh",
                                         command_sha256=hashlib.sha256(b"sudo id").hexdigest(),
                                         allow_elevation=False, authorized_by="test")
        db.add(row)
        await db.commit()
        undeclared = {"id": str(row.id), "command": "sudo id", "shell": "sh"}
    r = await run(c, elevated, undeclared)
    assert r.status_code == 403 and code(r) == "ELEVATION_NOT_ALLOWED"
    entry = await authorize(c, elevated, "sudo systemctl restart nginx", allow_elevation=True)
    r = await run(c, elevated, entry)
    assert r.status_code == 201, r.text
    await finished(r.json()["id"])
    assert len(c.calls) == 1


# --- opening -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_one_active_session_per_agent(ctx):
    c = ctx
    first = await open_session(c)
    r = await c.client.post(HUMAN + "/sessions", json={"agent_id": str(c.agent.id), "message_number": c.task.number,
                                                       "server_id": str(c.lab2.id), "operation": "Other"},
                            headers=c.owner_h)
    assert r.status_code == 409 and code(r) == "COLLABORATION_SESSION_ALREADY_ACTIVE"
    # Once the first can no longer be used, a new opening ends it and proceeds.
    async with AsyncSessionLocal() as db:
        await db.execute(update(RemoteCollaborationSession).where(
            RemoteCollaborationSession.id == uuid.UUID(first["id"])).values(
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
        await db.commit()
    second = await open_session(c, server=c.lab2)
    old = await session_row(first)
    assert old.status == "ended" and old.end_reason == "expired"
    assert second["server_id"] == str(c.lab2.id)


@pytest.mark.asyncio
async def test_opening_requires_a_running_task_of_that_agent_and_a_managed_machine(ctx):
    c = ctx
    # Task of another agent.
    r = await c.client.post(HUMAN + "/sessions", json={"agent_id": str(c.agent.id),
        "message_number": c.other_task.number, "server_id": str(c.lab.id), "operation": "x"}, headers=c.owner_h)
    assert r.status_code == 422 and code(r) == "TASK_NOT_ADDRESSED_TO_AGENT"
    # A literal secret in the operation.
    await open_session(c, operation="use password=hunter2hunter2", expect=422)
    # A machine not reconfigured with the darckware account.
    async with AsyncSessionLocal() as db:
        await db.execute(update(Server).where(Server.id == c.lab2.id).values(remote_user="root"))
        await db.commit()
    r = await c.client.post(HUMAN + "/sessions", json={"agent_id": str(c.agent.id), "message_number": c.task.number,
        "server_id": str(c.lab2.id), "operation": "x"}, headers=c.owner_h)
    assert r.status_code == 403 and code(r) == "MACHINE_RECONFIGURATION_REQUIRED"
    # A finished task.
    async with AsyncSessionLocal() as db:
        await db.execute(update(AgentDemand).where(AgentDemand.id == c.task.id).values(dispatch_status="completed"))
        await db.commit()
    r = await c.client.post(HUMAN + "/sessions", json={"agent_id": str(c.agent.id), "message_number": c.task.number,
        "server_id": str(c.lab.id), "operation": "x"}, headers=c.owner_h)
    assert r.status_code == 403 and code(r) == "TASK_FINISHED"


@pytest.mark.asyncio
async def test_direct_command_route_is_unchanged_by_a_session(ctx):
    """A collaborative session cannot keep an agent on the direct access list."""
    c = ctx
    session = await open_session(c)
    await authorize(c, session)
    async with AsyncSessionLocal() as db:
        await db.execute(update(Agent).where(Agent.id == c.agent.id).values(direct_access_allowed=False))
        await db.commit()
    r = await c.client.post(DIRECT_RUN, json={"server_ids": [str(c.lab.id)], "command": "uname -a",
                                              "reason": "Check the kernel", "message_number": c.task.number},
                            headers=c.agent_h)
    assert r.status_code == 403 and code(r) == "AGENT_NOT_LISTED"
    assert c.calls == []


# --- machine runnability, launch failure, removed bindings, effective status ----

async def listed_session(c, session, headers=None):
    r = await c.client.get(HUMAN + "/sessions", headers=headers or c.owner_h)
    assert r.status_code == 200, r.text
    return next(s for s in r.json() if s["id"] == session["id"])


@pytest.mark.asyncio
async def test_machine_launch_would_skip_is_refused_and_command_kept(ctx):
    c = ctx
    session = await open_session(c)
    entry = await authorize(c, session)
    for values in ({"access_enabled": False}, {"os_family": "windows"}, {"ip_address": ""}):
        async with AsyncSessionLocal() as db:
            await db.execute(update(Server).where(Server.id == c.lab.id).values(**values))
            await db.commit()
        r = await run(c, session, entry)
        assert r.status_code == 409 and code(r) == "MACHINE_NOT_RUNNABLE", (values, r.text)
        assert (await command_row(entry)).status == "authorized"
        async with AsyncSessionLocal() as db:
            await db.execute(update(Server).where(Server.id == c.lab.id).values(
                access_enabled=True, os_family="linux", ip_address="192.0.2.61"))
            await db.commit()
    assert c.calls == []
    async with AsyncSessionLocal() as db:
        assert not (await db.scalars(select(HostExecution).where(HostExecution.agent_id == c.agent.id))).all()
    # Restored, the same authorization still runs.
    r = await run(c, session, entry)
    assert r.status_code == 201, r.text
    await finished(r.json()["id"])


@pytest.mark.asyncio
async def test_opening_and_authorizing_check_the_machine_can_run_it(ctx):
    c = ctx
    # Shell vs OS at authorization (sh machine, PowerShell command).
    session = await open_session(c)
    r = await c.client.post(f"{HUMAN}/sessions/{session['id']}/commands",
                            json={"command": "Get-Date", "shell": "powershell"}, headers=c.owner_h)
    assert r.status_code == 422 and code(r) == "MACHINE_NOT_RUNNABLE"
    # Access turned off: neither authorizing nor opening.
    async with AsyncSessionLocal() as db:
        await db.execute(update(Server).where(Server.id.in_([c.lab.id, c.lab2.id])).values(access_enabled=False))
        await db.commit()
    r = await c.client.post(f"{HUMAN}/sessions/{session['id']}/commands", json={"command": "id"}, headers=c.owner_h)
    assert r.status_code == 422 and code(r) == "MACHINE_NOT_RUNNABLE"
    r = await c.client.post(HUMAN + "/sessions", json={"agent_id": str(c.other.id),
        "message_number": c.other_task.number, "server_id": str(c.lab2.id), "operation": "x"}, headers=c.owner_h)
    assert r.status_code == 422 and code(r) == "MACHINE_NOT_RUNNABLE"
    async with AsyncSessionLocal() as db:
        assert not (await db.scalars(select(RemoteCollaborationCommand).where(
            RemoteCollaborationCommand.session_id == uuid.UUID(session["id"])))).all()


@pytest.mark.asyncio
async def test_launch_failure_before_commit_leaves_the_command_unconsumed(ctx, monkeypatch):
    from fastapi import HTTPException
    c = ctx
    session = await open_session(c)
    entry = await authorize(c, session)
    original = host.launch_execution

    async def failing(db, **kwargs):
        consume = kwargs["before_commit"]

        async def boom(execution):
            await consume(execution)  # the authorization is marked used, then the launch fails
            raise HTTPException(503, {"code": "SIMULATED", "message": "launch failed before commit"})
        kwargs["before_commit"] = boom
        return await original(db, **kwargs)

    monkeypatch.setattr(host, "launch_execution", failing)
    r = await run(c, session, entry)
    assert r.status_code == 503, r.text
    used = await command_row(entry)
    assert used.status == "authorized" and used.execution_id is None and used.used_at is None
    async with AsyncSessionLocal() as db:
        assert not (await db.scalars(select(HostExecution).where(HostExecution.agent_id == c.agent.id))).all()
        assert not (await db.scalars(select(AuditEvent).where(
            AuditEvent.event_type == "remote_collaboration_command_run",
            AuditEvent.entity_id == uuid.UUID(session["id"])))).all()
    assert c.calls == []
    monkeypatch.setattr(host, "launch_execution", original)
    r = await run(c, session, entry)
    assert r.status_code == 201, r.text
    await finished(r.json()["id"])


@pytest.mark.asyncio
async def test_purged_owner_session_keeps_the_record_and_fails_closed(ctx):
    c = ctx
    session = await open_session(c)
    entry = await authorize(c, session)
    # purge_old_sessions deletes the browser session row: the record survives with NULL.
    async with AsyncSessionLocal() as db:
        await db.execute(delete(UserSession).where(UserSession.id == c.owner_session.id))
        await db.commit()
    row = await session_row(session)
    assert row is not None and row.user_session_id is None and row.status == "active"
    assert (await command_row(entry)).status == "authorized"
    r = await run(c, session, entry)
    assert r.status_code == 403 and code(r) == "COLLABORATION_SESSION_NOT_ACTIVE"
    # The owner, back in a new browser session, sees it inactive and can't authorize on it.
    sid, fresh = _session_row(c.owner)
    async with AsyncSessionLocal() as db:
        db.add(fresh)
        await db.commit()
    headers = _token(c.owner, sid)
    shown = await listed_session(c, session, headers)
    assert shown["status"] == "active" and shown["effective_status"] == "inactive"
    assert shown["dead_reason"] == "owner_session_removed"
    r = await c.client.post(f"{HUMAN}/sessions/{session['id']}/commands", json={"command": "id"}, headers=headers)
    assert r.status_code == 403 and code(r) == "COLLABORATION_SESSION_NOT_ACTIVE"
    r = await c.client.post(f"{HUMAN}/sessions/{session['id']}:end", json={}, headers=headers)
    assert r.status_code == 200, r.text
    assert c.calls == []


@pytest.mark.asyncio
async def test_deleted_machine_keeps_the_record_and_fails_closed(ctx):
    c = ctx
    session = await open_session(c, server=c.lab2)
    entry = await authorize(c, session)
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Server).where(Server.id == c.lab2.id))
        await db.commit()
    row = await session_row(session)
    assert row is not None and row.server_id is None
    assert (await command_row(entry)).status == "authorized"
    r = await run(c, session, entry, server_ids=[str(c.lab2.id)])
    assert r.status_code == 403 and code(r) == "COLLABORATION_SESSION_NOT_ACTIVE"
    shown = await listed_session(c, session)
    assert shown["effective_status"] == "inactive" and shown["dead_reason"] == "machine_removed"
    assert shown["server_id"] is None
    r = await c.client.post(f"{HUMAN}/sessions/{session['id']}/commands", json={"command": "id"}, headers=c.owner_h)
    assert r.status_code == 403 and code(r) == "COLLABORATION_SESSION_NOT_ACTIVE"
    # A new opening for the agent ends it (no longer usable) instead of refusing.
    reopened = await open_session(c)
    assert reopened["effective_status"] == "active"
    old = await session_row(session)
    assert old.status == "ended" and old.end_reason == "machine_removed"
    assert c.calls == []


@pytest.mark.asyncio
async def test_listing_shows_the_effective_status(ctx):
    c = ctx
    session = await open_session(c)
    shown = await listed_session(c, session)
    assert shown["effective_status"] == "active" and shown["dead_reason"] is None
    async with AsyncSessionLocal() as db:
        await db.execute(update(AgentDemand).where(AgentDemand.id == c.task.id).values(dispatch_status="completed"))
        await db.commit()
    shown = await listed_session(c, session)
    assert shown["status"] == "active" and shown["effective_status"] == "inactive"
    assert shown["dead_reason"] == "run_ended"
    async with AsyncSessionLocal() as db:
        await db.execute(update(RemoteCollaborationSession).where(
            RemoteCollaborationSession.id == uuid.UUID(session["id"])).values(
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
        await db.commit()
    assert (await listed_session(c, session))["dead_reason"] == "expired"
    r = await c.client.post(f"{HUMAN}/sessions/{session['id']}:end", json={}, headers=c.owner_h)
    assert r.json()["effective_status"] == "ended" and r.json()["dead_reason"] is None


@pytest.mark.asyncio
async def test_locked_pass_blocks_machine_edits_and_other_launches_until_commit(ctx):
    """Review #42352: between the locked check and launch_execution's commit, the
    machine row can't change (login, address, key ref), and run_direct_command or
    another collaborative call (both take `with_for_update(key_share=True)`, i.e.
    FOR NO KEY UPDATE) can't race past busy_server_ids."""
    from sqlalchemy import text

    from app.core.deps import ActorPrincipal
    from app.core.remote_collaboration import require_collaboration

    c = ctx
    session = await open_session(c)
    entry = await authorize(c, session)
    principal = ActorPrincipal(principal_type="agent", principal_id=c.agent.id, display_name=c.agent.name,
                               credential_id=c.credential_id, credential_label=f"dispatch:{c.run_id}")
    async with AsyncSessionLocal() as holder:
        found = await require_collaboration(
            holder, principal=principal, session_id=uuid.UUID(session["id"]), command_id=uuid.UUID(entry["id"]),
            command=entry["command"], shell=entry["shell"], message_number=c.task.number,
            server_ids=[session["server_id"]], lock=True)
        assert found.server.id == c.lab.id
        for statement in (
            update(Server).where(Server.id == c.lab.id).values(remote_user="someone-else"),
            update(AgentServiceCredential).where(AgentServiceCredential.id == c.credential_id).values(
                revoked_at=datetime.now(timezone.utc)),
            update(AgentServiceCredential).where(AgentServiceCredential.id == c.credential_id).values(
                expires_at=datetime.now(timezone.utc)),
            select(Server.id).where(Server.id == c.lab.id).with_for_update(key_share=True),
            update(Agent).where(Agent.id == c.agent.id).values(direct_access_allowed=False),
            update(Agent).where(Agent.id == c.agent.id).values(runtime_type="hermes"),
            update(AuthorityDelegation).where(AuthorityDelegation.id == c.grant.id).values(status="revoked"),
            update(AuthorityDelegation).where(AuthorityDelegation.id == c.grant.id).values(servers=[]),
            update(AuthorityDelegation).where(AuthorityDelegation.id == c.grant.id).values(allow_elevation=False),
        ):
            async with AsyncSessionLocal() as other:
                await other.execute(text("SET LOCAL lock_timeout = '300ms'"))
                with pytest.raises(Exception, match="lock timeout"):
                    await other.execute(statement)
                await other.rollback()
        await holder.rollback()
    async with AsyncSessionLocal() as db:
        assert (await db.get(Server, c.lab.id)).remote_user != "someone-else"


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["open", "authorize", "run", "locked_run"])
@pytest.mark.parametrize("change", ["missing", "revoked", "expired", "future", "machine", "action", "unlisted", "elevation"])
async def test_direct_grant_is_required_at_every_stage(ctx, monkeypatch, stage, change):
    c = ctx
    elevated = change == "elevation"
    session = entry = None
    if stage != "open":
        session = await open_session(c, allow_elevation=elevated)
    if stage in ("run", "locked_run"):
        entry = await authorize(c, session, "sudo id" if elevated else "uname -a", allow_elevation=elevated)

    async def restrict():
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as db:
            if change == "missing":
                await db.execute(delete(AuthorityDelegation).where(AuthorityDelegation.id == c.grant.id))
            elif change == "unlisted":
                await db.execute(update(Agent).where(Agent.id == c.agent.id).values(direct_access_allowed=False))
            else:
                values = {
                    "revoked": {"revoked_at": now},
                    "expired": {"expires_at": now - timedelta(seconds=1)},
                    "future": {"valid_from": now + timedelta(hours=1)},
                    "machine": {"servers": [str(c.lab2.id)]},
                    "action": {"allowed_actions": ["remote_access.execute"]},
                    "elevation": {"allow_elevation": False},
                }[change]
                await db.execute(update(AuthorityDelegation).where(AuthorityDelegation.id == c.grant.id).values(**values))
            await db.commit()

    if stage == "locked_run":
        async def readiness(db):
            await restrict()
            return {c.lab.id: (True, "complete")}
        monkeypatch.setattr(host, "_agent_readiness", readiness)
    else:
        await restrict()
    if stage == "open":
        response = await c.client.post(HUMAN + "/sessions", headers=c.owner_h, json={
            "agent_id": str(c.agent.id), "message_number": c.task.number, "server_id": str(c.lab.id),
            "operation": "test", "allow_elevation": elevated})
    elif stage == "authorize":
        response = await c.client.post(f"{HUMAN}/sessions/{session['id']}/commands", headers=c.owner_h,
                                      json={"command": "sudo id" if elevated else "id", "allow_elevation": elevated})
    else:
        response = await run(c, session, entry)
    assert response.status_code == 403, response.text
    assert code(response) == ("ELEVATION_NOT_ALLOWED" if elevated else "NO_DIRECT_ACCESS")
    assert c.calls == []
    if entry:
        assert (await command_row(entry)).status == "authorized"
    async with AsyncSessionLocal() as db:
        assert not (await db.scalars(select(HostExecution).where(HostExecution.agent_id == c.agent.id))).all()


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime", ["hermes", None, "claude", "codex", "agy"])
@pytest.mark.parametrize("stage", ["open", "authorize", "run", "locked_run"])
async def test_only_coding_runtimes_can_collaborate(ctx, monkeypatch, runtime, stage):
    c = ctx
    session = entry = None
    if stage != "open":
        session = await open_session(c)
    if stage in ("run", "locked_run"):
        entry = await authorize(c, session)

    async def change_runtime():
        async with AsyncSessionLocal() as db:
            await db.execute(update(Agent).where(Agent.id == c.agent.id).values(runtime_type=runtime))
            await db.commit()

    if stage == "locked_run":
        async def readiness(db):
            await change_runtime()
            return {c.lab.id: (True, "complete")}
        monkeypatch.setattr(host, "_agent_readiness", readiness)
    else:
        await change_runtime()
    if stage == "open":
        response = await c.client.post(HUMAN + "/sessions", headers=c.owner_h, json={
            "agent_id": str(c.agent.id), "message_number": c.task.number, "server_id": str(c.lab.id), "operation": "test"})
    elif stage == "authorize":
        response = await c.client.post(f"{HUMAN}/sessions/{session['id']}/commands", headers=c.owner_h,
                                      json={"command": "id"})
    else:
        response = await run(c, session, entry)
    if runtime in ("claude", "codex", "agy"):
        assert response.status_code == 201, response.text
        if entry:
            await finished(response.json()["id"])
    else:
        assert response.status_code == 403 and code(response) == "COLLABORATION_AGENT_INELIGIBLE", response.text
        assert c.calls == []
        if entry:
            assert (await command_row(entry)).status == "authorized"


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["revoked", "expired", "deleted", "agent", "run"])
async def test_credential_changed_during_readiness_is_refused(ctx, monkeypatch, change):
    c = ctx
    session = await open_session(c)
    entry = await authorize(c, session)

    async def readiness(db):
        async with AsyncSessionLocal() as writer:
            if change == "deleted":
                await writer.execute(delete(AgentServiceCredential).where(AgentServiceCredential.id == c.credential_id))
            else:
                values = {
                    "revoked": {"revoked_at": datetime.now(timezone.utc)},
                    "expired": {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)},
                    "agent": {"agent_id": c.other.id},
                    "run": {"label": "dispatch:different-run"},
                }[change]
                await writer.execute(update(AgentServiceCredential).where(
                    AgentServiceCredential.id == c.credential_id).values(**values))
            await writer.commit()
        return {c.lab.id: (True, "complete")}

    monkeypatch.setattr(host, "_agent_readiness", readiness)
    response = await run(c, session, entry)
    assert response.status_code == 403 and code(response) == "TASK_CREDENTIAL_MISMATCH", response.text
    assert c.calls == [] and (await command_row(entry)).status == "authorized"
    async with AsyncSessionLocal() as db:
        assert not (await db.scalars(select(HostExecution).where(HostExecution.agent_id == c.agent.id))).all()


@pytest.mark.asyncio
@pytest.mark.parametrize("restriction", ["machine", "scripts"])
@pytest.mark.parametrize("stage", ["open", "authorize", "run", "locked_run"])
async def test_collaboration_honors_maintenance_request_scope(ctx, monkeypatch, restriction, stage):
    c = ctx
    session = entry = None
    if stage != "open":
        session = await open_session(c)
    if stage in ("run", "locked_run"):
        entry = await authorize(c, session)

    async def restrict():
        async with AsyncSessionLocal() as db:
            db.add(AuditEvent(entity_type=host.REQUEST_EVENT, entity_id=c.task.id, event_type=host.REQUEST_EVENT,
                              actor=c.owner.username, payload={
                                  "server_ids": [str(c.lab2.id if restriction == "machine" else c.lab.id)],
                                  "script_ids": [str(uuid.uuid4())] if restriction == "scripts" else [],
                              }))
            await db.commit()

    if stage == "locked_run":
        async def readiness(db):
            await restrict()
            return {c.lab.id: (True, "complete")}
        monkeypatch.setattr(host, "_agent_readiness", readiness)
    else:
        await restrict()
    if stage == "open":
        response = await c.client.post(HUMAN + "/sessions", headers=c.owner_h, json={
            "agent_id": str(c.agent.id), "message_number": c.task.number, "server_id": str(c.lab.id), "operation": "test"})
    elif stage == "authorize":
        response = await c.client.post(f"{HUMAN}/sessions/{session['id']}/commands", headers=c.owner_h,
                                      json={"command": "id"})
    else:
        response = await run(c, session, entry)
    assert response.status_code == 403, response.text
    assert ("Not in task" if restriction == "machine" else "allows only the scripts") in code(response)
    assert c.calls == []
    if entry:
        assert (await command_row(entry)).status == "authorized"


@pytest.mark.asyncio
async def test_collaborative_execution_records_selected_direct_grant(ctx):
    c = ctx
    session = await open_session(c)
    entry = await authorize(c, session)
    response = await run(c, session, entry)
    assert response.status_code == 201, response.text
    execution_id = uuid.UUID(response.json()["id"])
    await finished(str(execution_id))
    async with AsyncSessionLocal() as db:
        result = await db.scalar(select(HostExecutionResult).where(HostExecutionResult.execution_id == execution_id))
        assert result.delegation_id == c.grant.id
        audit = await db.scalar(select(AuditEvent).where(
            AuditEvent.entity_id == execution_id, AuditEvent.event_type == "started"))
        assert audit.payload["direct_access"] == {str(c.lab.id): str(c.grant.id)}
        # The grant remains exactly the pre-existing machine authorization.
        grant = await db.get(AuthorityDelegation, c.grant.id)
        assert grant.servers == c.grant.servers and grant.expires_at == c.grant.expires_at


@pytest.mark.asyncio
async def test_opening_cannot_deadlock_completion_creating_a_reply(ctx):
    import asyncio
    from sqlalchemy import event
    from fastapi import HTTPException
    from app.api.routes.demand import _finalize_dispatch
    from app.api.routes.remote_collaboration import open_collaboration_session
    from app.api.schemas.remote_collaboration import CollaborationSessionCreate
    from app.core.deps import ActorPrincipal
    from app.db.base import engine

    c = ctx
    async with AsyncSessionLocal() as db:
        await db.execute(update(AgentDemand).where(AgentDemand.id == c.task.id).values(
            requires_response=True, from_agent_id=c.other.id))
        await db.commit()
    waiting_for_task = asyncio.Event()
    opener = None

    def observe(conn, cursor, statement, parameters, context, executemany):
        if asyncio.current_task() is opener and "agent_demands" in statement and "FOR SHARE" in statement:
            waiting_for_task.set()

    async def opening():
        async with AsyncSessionLocal() as db:
            try:
                await open_collaboration_session(
                    CollaborationSessionCreate(agent_id=c.agent.id, message_number=c.task.number,
                                               server_id=c.lab.id, operation="test"),
                    owner=(ActorPrincipal("user", c.owner.id, c.owner.username, is_admin=True), c.owner_session), db=db)
            except HTTPException as exc:
                assert exc.status_code == 403 and exc.detail["code"] == "TASK_FINISHED"
            else:
                pytest.fail("Opening must see the task finalized before it acquired the task lock")

    event.listen(engine.sync_engine, "before_cursor_execute", observe)
    try:
        async with AsyncSessionLocal() as finalizer:
            await finalizer.scalar(select(AgentDemand).where(AgentDemand.id == c.task.id).with_for_update())
            opener = asyncio.create_task(opening())
            await asyncio.wait_for(waiting_for_task.wait(), timeout=5)
            reply = await asyncio.wait_for(_finalize_dispatch(finalizer, c.task.id, {
                "status": "completed", "output": "done\nSTATUS: DONE"}), timeout=5)
            assert reply is not None and reply.from_agent_id == c.agent.id
            await finalizer.commit()
        await asyncio.wait_for(opener, timeout=5)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", observe)
        if opener is not None and not opener.done():
            opener.cancel()
            await asyncio.gather(opener, return_exceptions=True)

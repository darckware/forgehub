"""Direct remote access: real FastAPI/Postgres; the bridge is simulated except
in the linux-target.test cycle, which runs for real."""
import asyncio
import hashlib
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, or_, select

from app.api.routes import host_execution as host
from app.core import host_exec_runner
from app.core.remote_authority import CONTROL_ID, agent_access_control, hermes_direct_problem, is_sensitive_machine
from app.core.secret_masking import mask_secrets
from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent, AgentServiceCredential
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent, AuthorityDelegation
from app.db.models.host_execution import HostExecution, HostExecutionResult
from app.db.models.host_script import HostSchedule, HostScript, HostScriptCategory
from app.db.models.notification import Notification
from app.db.models.server import HostGroup, HostGroupMember, Server
from app.db.models.user import User
from app.main import app

ORIGINAL_BRIDGE_EXEC = host_exec_runner.call_bridge_exec
ADMIN = "/api/v1/remote-access/direct"
RUN = "/api/v1/host-executions/agent/commands"
FAKE_KEY = "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAA\n-----END OPENSSH PRIVATE KEY-----"


@pytest_asyncio.fixture
async def ctx(monkeypatch):
    tag = uuid.uuid4().hex
    tokens = {"agent": "agt_direct_" + tag, "other": "agt_direct_other_" + tag, "hermes": "agt_direct_hermes_" + tag}
    async with AsyncSessionLocal() as db:
        admin = User(username="direct-admin-" + tag, hashed_password="unused", is_admin=True)
        plain = User(username="direct-user-" + tag, hashed_password="unused", is_admin=False)
        agent = Agent(name="direct-agent-" + tag, agent_type="executor", runtime_type="claude", direct_access_allowed=True)
        other = Agent(name="direct-other-" + tag, agent_type="executor", runtime_type="codex", direct_access_allowed=True)
        hermes = Agent(name="direct-hermes-" + tag, agent_type="executor", runtime_type="hermes", profile_slug="d" + tag[:8])
        lab = Server(name="direct-lab-" + tag, ip_address="192.0.2.51", remote_user="test", os_family="linux", environment="lab")
        lab2 = Server(name="direct-lab2-" + tag, ip_address="192.0.2.52", remote_user="test", os_family="linux", environment="test")
        prod = Server(name="direct-prod-" + tag, ip_address="192.0.2.53", remote_user="test", os_family="linux", environment="client")
        group = HostGroup(name="direct-group-" + tag)
        db.add_all([admin, plain, agent, other, hermes, lab, lab2, prod, group])
        await db.flush()
        db.add(HostGroupMember(group_id=group.id, server_id=lab2.id))
        task = AgentDemand(from_agent="t", from_agent_id=agent.id, target_agent_id=agent.id, subject="t", body="t", origin_type="task")
        foreign = AgentDemand(from_agent="t", from_agent_id=other.id, target_agent_id=other.id, subject="o", body="t", origin_type="task")
        db.add_all([task, foreign])
        for row, token in ((agent, tokens["agent"]), (other, tokens["other"]), (hermes, tokens["hermes"])):
            db.add(AgentServiceCredential(agent_id=row.id, label="test", token_hash=hashlib.sha256(token.encode()).hexdigest()))
        await db.commit()
    machines = [lab, lab2, prod]

    async def readiness(db):
        return {m.id: (True, "complete") for m in machines}

    monkeypatch.setattr(host, "_agent_readiness", readiness)

    async def remote(*args):
        return dict(exit_code=0, stdout="ok token=never-show-this\n" + FAKE_KEY, stderr=FAKE_KEY[:60], duration_ms=1, failure=None)

    monkeypatch.setattr(host_exec_runner, "call_bridge_exec", remote)
    agents = [agent.id, other.id, hermes.id]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield SimpleNamespace(
            client=client, admin=admin, agent=agent, other=other, hermes=hermes, lab=lab, lab2=lab2, prod=prod, group=group,
            task=task, foreign=foreign,
            admin_h={"Authorization": "Bearer " + create_access_token(admin.username)},
            user_h={"Authorization": "Bearer " + create_access_token(plain.username)},
            agent_h={"Authorization": "Bearer " + tokens["agent"]}, other_h={"Authorization": "Bearer " + tokens["other"]},
        )
    for pending in list(host_exec_runner._running.values()):
        await pending
    async with AsyncSessionLocal() as db:
        ids = [m.id for m in machines]
        access_ids = select(AuthorityDelegation.id).where(AuthorityDelegation.grantee_id.in_(agents))
        keys = [Notification.event_key.like(f"direct-access:{verb}:{i}") for verb in ("opened", "closed")
                for i in (await db.scalars(access_ids)).all()]
        if keys:
            await db.execute(delete(Notification).where(or_(*keys)))
        run_ids = select(HostExecution.id).where(HostExecution.agent_id.in_(agents))
        await db.execute(delete(AuditEvent).where(or_(AuditEvent.entity_id.in_(run_ids), AuditEvent.entity_id.in_(access_ids),
                                                      AuditEvent.entity_id.in_(ids), AuditEvent.entity_id.in_(agents))))
        await db.execute(delete(HostExecution).where(HostExecution.agent_id.in_(agents)))
        await db.execute(delete(AuthorityDelegation).where(AuthorityDelegation.grantee_id.in_(agents)))
        await db.execute(delete(AgentServiceCredential).where(AgentServiceCredential.agent_id.in_(agents)))
        await db.execute(delete(AgentDemand).where(AgentDemand.target_agent_id.in_(agents)))
        await db.execute(delete(HostGroup).where(HostGroup.id == group.id))
        await db.execute(delete(Server).where(Server.id.in_(ids)))
        await db.execute(delete(Agent).where(Agent.id.in_(agents)))
        await db.execute(delete(User).where(User.id.in_([admin.id, plain.id])))
        await db.commit()


def opening(c, **extra):
    return {"agent_id": str(c.agent.id), "server_ids": [str(c.lab.id)], "reason": "Fix the deploy", "purpose": "support",
            "duration_hours": 1, **extra}


async def opened(c, **extra):
    r = await c.client.post(ADMIN, json=opening(c, **extra), headers=c.admin_h)
    assert r.status_code == 201, r.text
    return r.json()


def command(c, **extra):
    return {"server_ids": [str(c.lab.id)], "command": "uname -a", "reason": "Check the kernel",
            "message_number": c.task.number, **extra}


async def finished(c, execution_id):
    pending = host_exec_runner._running.get(uuid.UUID(execution_id))
    if pending:
        await pending


async def code_of(response):
    return response.json()["detail"]["code"]


@pytest.mark.asyncio
async def test_linux_target_open_use_close(ctx, monkeypatch):
    c = ctx
    state = subprocess.run(["docker", "inspect", "-f", "{{.State.Status}}", "forgehub_test_linux_target"],
                           capture_output=True, text=True, check=True)
    assert state.stdout.strip() == "running"
    async with AsyncSessionLocal() as db:
        s = await db.get(Server, c.lab.id)
        s.ip_address, s.remote_user, s.ssh_key_path = "linux-target.test", "darckware", "/test-linux-target/id_ed25519"
        await db.commit()
    monkeypatch.setattr(host_exec_runner, "call_bridge_exec", ORIGINAL_BRIDGE_EXEC)
    access = await opened(c)
    machines = await c.client.get("/api/v1/host-executions/agent/machines", headers=c.agent_h)
    row = next(m for m in machines.json() if m["id"] == str(c.lab.id))
    assert row["direct_access"] is True and row["direct_access_until"] and row["direct_allow_elevation"] is False

    r = await c.client.post(RUN, json=command(c, command="id -un; printf 'pass''word=fictitious-548\\n'"), headers=c.agent_h)
    assert r.status_code == 201, r.text
    eid = r.json()["id"]
    await finished(c, eid)
    got = await c.client.get("/api/v1/host-executions/agent/" + eid, headers=c.agent_h)
    data = got.json()
    assert data["counts"]["succeeded"] == 1, data
    assert data["results"][0]["delegation_id"] == access["id"]
    assert data["results"][0]["stdout"] == "darckware\npassword=********\n"

    history = (await c.client.get(f"/api/v1/servers/{c.lab.id}/maintenance", headers=c.admin_h)).json()
    runs = [h for h in history if h["execution_id"] == eid]
    assert len(runs) == 1
    assert (runs[0]["direct_access_id"], runs[0]["direct_access_purpose"], runs[0]["message_number"]) == (access["id"], "support", c.task.number)
    assert runs[0]["reason"] == "Check the kernel" and runs[0]["agent_name"] == c.agent.name
    assert any("Acesso direto aberto" in h["title"] for h in history)

    closed = await c.client.post(f"{ADMIN}/{access['id']}:close", headers=c.admin_h)
    assert closed.status_code == 200, closed.text
    assert closed.json()["running_commands"] == 0 and "not interrupted" in closed.json()["notice"]
    refused = await c.client.post(RUN, json=command(c), headers=c.agent_h)
    assert refused.status_code == 403 and await code_of(refused) == "NO_DIRECT_ACCESS"
    assert access["id"] not in [a["id"] for a in (await c.client.get(ADMIN, headers=c.admin_h)).json()]
    async with AsyncSessionLocal() as db:
        run = await db.get(HostExecution, uuid.UUID(eid))
        assert (run.trigger, run.agent_id, run.agent_demand_id) == ("agent", c.agent.id, c.task.id)
        started = (await db.scalars(select(AuditEvent).where(AuditEvent.entity_id == run.id))).one()
        assert started.payload["direct_access"] == {str(c.lab.id): access["id"]}
        events = (await db.scalars(select(AuditEvent).where(AuditEvent.entity_id == uuid.UUID(access["id"])))).all()
        assert {e.event_type for e in events} == {"direct_access_opened", "direct_access_closed"}
        assert all(e.actor == c.admin.username for e in events)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["none", "other_machine", "expired", "revoked", "foreign_task", "archived_task", "request_task"])
async def test_command_refusals(ctx, case):
    c = ctx
    body = command(c)
    expected = 403
    if case != "none":
        access = await opened(c, server_ids=[str(c.lab2.id)] if case == "other_machine" else [str(c.lab.id)])
    if case in ("expired", "revoked"):
        async with AsyncSessionLocal() as db:
            row = await db.get(AuthorityDelegation, uuid.UUID(access["id"]))
            if case == "expired":
                row.valid_from, row.expires_at = (datetime.now(timezone.utc) - timedelta(hours=2),
                                                  datetime.now(timezone.utc) - timedelta(seconds=1))
            else:
                row.status, row.revoked_at = "revoked", datetime.now(timezone.utc)
            await db.commit()
    if case == "foreign_task":
        body["message_number"] = c.foreign.number
    if case == "archived_task":
        expected = 409
        async with AsyncSessionLocal() as db:
            (await db.get(AgentDemand, c.task.id)).status = "archived"
            await db.commit()
    if case == "request_task":
        # "Pedir ao agente" limits the task to scripts: no free command inside it.
        async with AsyncSessionLocal() as db:
            db.add(AuditEvent(entity_type=host.REQUEST_EVENT, entity_id=c.task.id, event_type="created", actor="t",
                              payload={"server_ids": [str(c.lab.id)], "script_ids": [str(uuid.uuid4())]}))
            await db.commit()
    r = await c.client.post(RUN, json=body, headers=c.agent_h)
    assert r.status_code == expected, r.text
    async with AsyncSessionLocal() as db:
        assert (await db.scalars(select(HostExecution).where(HostExecution.agent_id == c.agent.id))).first() is None
        if case == "request_task":
            await db.execute(delete(AuditEvent).where(AuditEvent.entity_id == c.task.id))
            await db.commit()


@pytest.mark.asyncio
async def test_access_must_cover_every_machine_and_empty_covers_nothing(ctx):
    c = ctx
    await opened(c)
    r = await c.client.post(RUN, json=command(c, server_ids=[str(c.lab.id), str(c.lab2.id)]), headers=c.agent_h)
    assert r.status_code == 403
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        db.add(AuthorityDelegation(grantor_user_id=c.admin.id, grantee_type="agent", grantee_id=c.other.id,
                                   allowed_actions=["remote_access.direct"], purpose="support", servers=[], host_groups=[],
                                   valid_from=now, expires_at=now + timedelta(hours=1)))
        await db.commit()
    r = await c.client.post(RUN, json=command(c, message_number=c.foreign.number), headers=c.other_h)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_only_a_human_admin_opens_and_closes(ctx):
    c = ctx
    assert (await c.client.post(ADMIN, json=opening(c), headers=c.agent_h)).status_code in (401, 403)
    assert (await c.client.post(ADMIN, json=opening(c), headers=c.user_h)).status_code == 403
    access = await opened(c)
    assert (await c.client.post(f"{ADMIN}/{access['id']}:close", headers=c.agent_h)).status_code in (401, 403)
    assert (await c.client.post(f"{ADMIN}/{access['id']}:close", headers=c.user_h)).status_code == 403
    assert (await c.client.post(f"/api/v1/governed/authority-delegations/{access['id']}:revoke", headers=c.agent_h)).status_code in (401, 403)
    assert (await c.client.post(f"{ADMIN}/{access['id']}:close", headers=c.admin_h)).status_code == 200
    assert (await c.client.post(f"{ADMIN}/{access['id']}:close", headers=c.admin_h)).status_code == 409


@pytest.mark.asyncio
async def test_the_generic_delegation_route_cannot_open_direct_access(ctx):
    c = ctx
    r = await c.client.post("/api/v1/governed/authority-delegations", headers=c.admin_h, json={
        "grantee_agent_id": str(c.agent.id), "allowed_actions": ["remote_access.direct"], "servers": [str(c.lab.id)],
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(), "reason": "bypass"})
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    {"duration_hours": 2}, {"duration_hours": 48}, {"duration_hours": 0}, {"reason": "    "}, {"reason": ""},
    {"purpose": "fun"}, {"expires_at": "2099-01-01T00:00:00Z"}, {"server_ids": []},
])
async def test_opening_validation(ctx, change):
    c = ctx
    assert (await c.client.post(ADMIN, json=opening(c, **change), headers=c.admin_h)).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("hours", [1, 4, 24])
async def test_the_three_durations(ctx, hours):
    c = ctx
    a = await opened(c, duration_hours=hours)
    gap = datetime.fromisoformat(a["expires_at"]) - datetime.fromisoformat(a["opened_at"])
    assert gap == timedelta(hours=hours)


@pytest.mark.asyncio
async def test_hermes_agent_is_not_eligible(ctx):
    c = ctx
    r = await c.client.post(ADMIN, json=opening(c, agent_id=str(c.hermes.id)), headers=c.admin_h)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_sensitive_machine_needs_confirmation_and_audit_says_who(ctx):
    c = ctx
    body = opening(c, server_ids=[str(c.prod.id), str(c.lab.id)])
    r = await c.client.post(ADMIN, json=body, headers=c.admin_h)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "SENSITIVE_CONFIRMATION_REQUIRED"
    assert r.json()["detail"]["machines"] == [c.prod.name]
    a = await opened(c, server_ids=[str(c.prod.id), str(c.lab.id)], confirm_sensitive=True)
    assert {m["name"]: m["sensitive"] for m in a["machines"]} == {c.prod.name: True, c.lab.name: False}
    async with AsyncSessionLocal() as db:
        event = (await db.scalars(select(AuditEvent).where(AuditEvent.entity_id == uuid.UUID(a["id"])))).one()
        assert event.payload["sensitive_machines"] == [c.prod.name]
        assert event.payload["sensitive_confirmed_by"] == c.admin.username
    plain = await opened(c)
    async with AsyncSessionLocal() as db:
        event = (await db.scalars(select(AuditEvent).where(AuditEvent.entity_id == uuid.UUID(plain["id"])))).one()
        assert event.payload["sensitive_confirmed_by"] is None


@pytest.mark.parametrize("environment,sensitive", [
    ("test", False), ("dev", False), ("lab", False), (" LAB ", False),
    ("semed", True), ("client", True), ("vps", True), ("teste", True), ("", True), (None, True),
])
def test_sensitive_rule(environment, sensitive):
    assert is_sensitive_machine(SimpleNamespace(environment=environment)) is sensitive


@pytest.mark.asyncio
async def test_group_is_a_snapshot_of_its_members(ctx):
    c = ctx
    a = await opened(c, server_ids=[], group_ids=[str(c.group.id)])
    assert [m["id"] for m in a["machines"]] == [str(c.lab2.id)]
    assert (await c.client.post(RUN, json=command(c, server_ids=[str(c.lab2.id)]), headers=c.agent_h)).status_code == 201
    async with AsyncSessionLocal() as db:
        db.add(HostGroupMember(group_id=c.group.id, server_id=c.prod.id))
        await db.commit()
    r = await c.client.post(RUN, json=command(c, server_ids=[str(c.prod.id)]), headers=c.agent_h)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_a_group_with_no_machines_opens_nothing(ctx):
    c = ctx
    async with AsyncSessionLocal() as db:
        await db.execute(delete(HostGroupMember).where(HostGroupMember.group_id == c.group.id))
        await db.commit()
    assert (await c.client.post(ADMIN, json=opening(c, server_ids=[], group_ids=[str(c.group.id)]), headers=c.admin_h)).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["sudo systemctl restart nginx", "docker ps", "su - root -c id"])
async def test_elevation_needs_the_option(ctx, text):
    c = ctx
    await opened(c)
    r = await c.client.post(RUN, json=command(c, command=text), headers=c.agent_h)
    assert r.status_code == 403 and await code_of(r) == "ELEVATION_NOT_ALLOWED"
    assert "sudo" in r.json()["detail"]["message"] and c.lab.name in r.json()["detail"]["message"]


@pytest.mark.asyncio
async def test_elevation_passes_with_the_option(ctx):
    c = ctx
    a = await opened(c, allow_elevation=True)
    r = await c.client.post(RUN, json=command(c, command="sudo -n true"), headers=c.agent_h)
    assert r.status_code == 201, r.text
    assert r.json()["results"][0]["delegation_id"] == a["id"]
    rows = (await c.client.get("/api/v1/host-executions/agent/machines", headers=c.agent_h)).json()
    assert next(m for m in rows if m["id"] == str(c.lab.id))["direct_allow_elevation"] is True


@pytest.mark.asyncio
async def test_elevation_comes_from_the_access_that_allows_it(ctx):
    c = ctx
    await opened(c, duration_hours=24)
    allowed = await opened(c, allow_elevation=True)
    r = await c.client.post(RUN, json=command(c, command="sudo -n true"), headers=c.agent_h)
    assert r.status_code == 201 and r.json()["results"][0]["delegation_id"] == allowed["id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("field,text", [
    ("command", "curl -H 'Authorization: Bearer abc.def.ghi' x"), ("command", "export password=hunter22"),
    ("command", FAKE_KEY), ("command", "tailscale up --authkey tskey-auth-abcdef123456"),
    ("reason", "login with password=hunter22"),
])
async def test_literal_secret_is_refused_and_not_stored(ctx, field, text):
    c = ctx
    await opened(c)
    r = await c.client.post(RUN, json=command(c, **{field: text}), headers=c.agent_h)
    assert r.status_code == 422 and await code_of(r) == "LITERAL_SECRET"
    assert "hunter22" not in r.text
    async with AsyncSessionLocal() as db:
        assert (await db.scalars(select(HostExecution).where(HostExecution.agent_id == c.agent.id))).first() is None


@pytest.mark.asyncio
async def test_timeout_default_and_limits(ctx):
    c = ctx
    await opened(c)
    r = await c.client.post(RUN, json=command(c), headers=c.agent_h)
    assert r.status_code == 201 and r.json()["timeout_seconds"] == 120
    await finished(c, r.json()["id"])
    assert (await c.client.post(RUN, json=command(c, timeout_seconds=1801), headers=c.agent_h)).status_code == 422


@pytest.mark.asyncio
async def test_busy_machine_comes_back_busy_with_nothing_queued(ctx, monkeypatch):
    c = ctx
    await opened(c)
    release = asyncio.Event()

    async def slow(*args):
        await release.wait()
        return dict(exit_code=0, stdout="done", stderr="", duration_ms=1, failure=None)

    monkeypatch.setattr(host_exec_runner, "call_bridge_exec", slow)
    results = await asyncio.gather(*[c.client.post(RUN, json=command(c), headers=c.agent_h) for _ in range(3)])
    assert sorted(r.status_code for r in results) == [201, 409, 409]
    refused = next(r for r in results if r.status_code == 409)
    assert await code_of(refused) == "MACHINE_BUSY" and refused.json()["detail"]["machines"] == [c.lab.name]
    async with AsyncSessionLocal() as db:
        assert len((await db.scalars(select(HostExecution).where(HostExecution.agent_id == c.agent.id))).all()) == 1
    release.set()


@pytest.mark.asyncio
async def test_closing_reports_the_running_command_and_it_finishes(ctx, monkeypatch):
    c = ctx
    access = await opened(c)
    release = asyncio.Event()

    async def slow(*args):
        await release.wait()
        return dict(exit_code=0, stdout="done", stderr="", duration_ms=1, failure=None)

    monkeypatch.setattr(host_exec_runner, "call_bridge_exec", slow)
    run = await c.client.post(RUN, json=command(c), headers=c.agent_h)
    closed = await c.client.post(f"{ADMIN}/{access['id']}:close", headers=c.admin_h)
    assert closed.json()["running_commands"] == 1
    release.set()
    await finished(c, run.json()["id"])
    async with AsyncSessionLocal() as db:
        result = (await db.scalars(select(HostExecutionResult).where(
            HostExecutionResult.execution_id == uuid.UUID(run.json()["id"])))).one()
        assert result.status == "succeeded"


@pytest.mark.asyncio
async def test_login_must_work_on_every_machine(ctx, monkeypatch):
    c = ctx
    await opened(c)

    async def not_ready(db):
        return {c.lab.id: (False, "not_prepared")}

    monkeypatch.setattr(host, "_agent_readiness", not_ready)
    r = await c.client.post(RUN, json=command(c), headers=c.agent_h)
    assert r.status_code == 409 and await code_of(r) == "LOGIN_NOT_READY"


@pytest.mark.asyncio
async def test_direct_and_execute_do_not_imply_each_other(ctx):
    c = ctx
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        db.add(AuthorityDelegation(grantor_user_id=c.admin.id, grantee_type="agent", grantee_id=c.agent.id,
                                   allowed_actions=["remote_access.execute"], servers=[str(c.lab.id)], max_risk="high",
                                   valid_from=now, expires_at=now + timedelta(hours=1)))
        category = await db.scalar(select(HostScriptCategory).limit(1))
        script = HostScript(name="direct-script-" + uuid.uuid4().hex, category_id=category.id, platform="linux",
                            content="echo ok", risk="read", created_by="t", updated_by="t", timeout_seconds=30)
        db.add(script)
        await db.commit()
    try:
        assert (await c.client.post(RUN, json=command(c), headers=c.agent_h)).status_code == 403
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AuthorityDelegation).where(AuthorityDelegation.grantee_id == c.agent.id))
            await db.commit()
        await opened(c)
        r = await c.client.post("/api/v1/host-executions/agent", headers=c.agent_h, json={
            "script_id": str(script.id), "server_ids": [str(c.lab.id)], "reason": "Library run", "message_number": c.task.number})
        assert r.status_code == 403, r.text
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(HostScript).where(HostScript.id == script.id))
            await db.commit()


@pytest.mark.asyncio
async def test_no_ssh_key_in_results_history_audit_or_agent_routes(ctx):
    c = ctx
    async with AsyncSessionLocal() as db:
        s = await db.get(Server, c.lab.id)
        s.ssh_key_ref, s.private_key_encrypted = "vault-ref-direct-test", "encrypted-direct-test"
        await db.commit()
    access = await opened(c)
    r = await c.client.post(RUN, json=command(c), headers=c.agent_h)
    eid = r.json()["id"]
    await finished(c, eid)
    texts = [r.text, (await c.client.get("/api/v1/host-executions/agent/" + eid, headers=c.agent_h)).text,
             (await c.client.get("/api/v1/host-executions/agent/machines", headers=c.agent_h)).text,
             (await c.client.get(ADMIN, headers=c.admin_h)).text,
             (await c.client.get(f"/api/v1/servers/{c.lab.id}/maintenance", headers=c.admin_h)).text]
    async with AsyncSessionLocal() as db:
        run = await db.get(HostExecution, uuid.UUID(eid))
        result = (await db.scalars(select(HostExecutionResult).where(HostExecutionResult.execution_id == run.id))).one()
        assert "********" in result.stdout and "********" in result.stderr
        texts += [run.command, result.stdout, result.stderr]
        for event in (await db.scalars(select(AuditEvent).where(AuditEvent.entity_id.in_(
                [run.id, uuid.UUID(access["id"]), c.lab.id])))).all():
            texts.append(str(event.payload))
    for text in texts:
        for leaked in ("PRIVATE KEY", "b3BlbnNzaC1rZXkt", "vault-ref-direct-test", "encrypted-direct-test",
                       "never-show-this", "ssh_key", "private_key"):
            assert leaked not in text
    for path in (f"/api/v1/servers/{c.lab.id}", "/api/v1/servers", f"/api/v1/servers/{c.lab.id}/maintenance"):
        assert (await c.client.get(path, headers=c.agent_h)).status_code in (401, 403)
    for method, path in (("POST", f"/api/v1/servers/{c.lab.id}/key:restore"), ("POST", f"/api/v1/servers/{c.lab.id}/key:backup")):
        assert (await c.client.request(method, path, headers=c.agent_h)).status_code in (401, 403)


def test_a_truncated_private_key_is_masked_to_the_end():
    assert mask_secrets("x\n-----BEGIN RSA PRIVATE KEY-----\nMIIEow") == "x\n********"


# --- the list of agents ---------------------------------------------------------

AGENTS = ADMIN + "/agents"
CONTROL = ADMIN + "/control"
PAUSED = "AGENT_REMOTE_ACCESS_PAUSED"


def hermes_profile(tmp_path, tools=""):
    (tmp_path / "config.yaml").write_text(
        "mcp_servers:\n  forgehub:\n    command: uv\n    args: [run, /srv/backend/app/mcp/factory_server.py]\n" + tools)
    return str(tmp_path)


async def set_home(agent, home):
    async with AsyncSessionLocal() as db:
        (await db.get(Agent, agent.id)).home_path = home
        await db.commit()


async def audit_events(entity_id, event_type):
    async with AsyncSessionLocal() as db:
        return (await db.scalars(select(AuditEvent).where(
            AuditEvent.entity_id == entity_id, AuditEvent.event_type == event_type))).all()


@pytest.mark.asyncio
async def test_adding_and_removing_is_audited_with_the_admin(ctx):
    c = ctx
    assert (await c.client.delete(f"{AGENTS}/{c.other.id}", headers=c.admin_h)).status_code == 200
    assert (await c.client.delete(f"{AGENTS}/{c.other.id}", headers=c.admin_h)).status_code == 404
    listed = {a["id"]: a for a in (await c.client.get(AGENTS, headers=c.admin_h)).json()}
    assert listed[str(c.other.id)]["allowed"] is False and listed[str(c.agent.id)]["allowed"] is True
    assert (await c.client.post(f"{AGENTS}/{c.other.id}", headers=c.admin_h)).status_code == 201
    assert (await c.client.post(f"{AGENTS}/{c.other.id}", headers=c.admin_h)).status_code == 409
    for event in ("direct_access_agent_removed", "direct_access_agent_added"):
        [row] = await audit_events(c.other.id, event)
        assert row.actor == c.admin.username


@pytest.mark.asyncio
async def test_an_agent_off_the_list_cannot_get_an_access(ctx):
    c = ctx
    await c.client.delete(f"{AGENTS}/{c.agent.id}", headers=c.admin_h)
    r = await c.client.post(ADMIN, json=opening(c), headers=c.admin_h)
    assert r.status_code == 422 and await code_of(r) == "AGENT_NOT_LISTED"


@pytest.mark.asyncio
async def test_removing_closes_the_open_accesses_and_refuses_the_next_command(ctx):
    c = ctx
    await opened(c)
    await opened(c, server_ids=[str(c.lab2.id)])
    assert (await c.client.post(RUN, json=command(c), headers=c.agent_h)).status_code == 201
    r = await c.client.delete(f"{AGENTS}/{c.agent.id}", headers=c.admin_h)
    assert r.status_code == 200
    assert r.json()["closed_accesses"] == 2 and "not interrupted" in r.json()["notice"]
    assert (await c.client.get(ADMIN, headers=c.admin_h)).json() == []
    r = await c.client.post(RUN, json=command(c), headers=c.agent_h)
    assert r.status_code == 403 and await code_of(r) == "AGENT_NOT_LISTED"
    async with AsyncSessionLocal() as db:
        rows = (await db.scalars(select(AuthorityDelegation).where(AuthorityDelegation.grantee_id == c.agent.id))).all()
        assert {r.status for r in rows} == {"revoked"}
        events = (await db.scalars(select(AuditEvent).where(
            AuditEvent.entity_id.in_([r.id for r in rows]), AuditEvent.event_type == "direct_access_closed"))).all()
        assert len(events) == 2 and {e.actor for e in events} == {c.admin.username}
        assert {e.payload["cause"] for e in events} == {"agent_removed_from_list"}


@pytest.mark.asyncio
async def test_removing_says_how_many_commands_are_still_running(ctx, monkeypatch):
    c = ctx
    release = asyncio.Event()

    async def slow(*args):
        await release.wait()
        return dict(exit_code=0, stdout="done", stderr="", duration_ms=1, failure=None)

    monkeypatch.setattr(host_exec_runner, "call_bridge_exec", slow)
    await opened(c)
    run = await c.client.post(RUN, json=command(c), headers=c.agent_h)
    assert (await c.client.delete(f"{AGENTS}/{c.agent.id}", headers=c.admin_h)).json()["running_commands"] == 1
    release.set()
    await finished(c, run.json()["id"])


@pytest.mark.asyncio
async def test_a_hermes_agent_joins_only_if_its_profile_reaches_the_tool(ctx, tmp_path):
    c = ctx
    await set_home(c.hermes, str(tmp_path / "missing"))
    r = await c.client.post(f"{AGENTS}/{c.hermes.id}", headers=c.admin_h)
    assert r.status_code == 422 and await code_of(r) == "PROFILE_NOT_READABLE"
    await set_home(c.hermes, hermes_profile(tmp_path, "    tools:\n      include: [send_agent_message]\n"))
    listed = {a["id"]: a for a in (await c.client.get(AGENTS, headers=c.admin_h)).json()}
    assert listed[str(c.hermes.id)]["unsupported_reason"] == "PROFILE_MCP_WITHOUT_MAINTENANCE_TOOLS"
    assert (await c.client.post(f"{AGENTS}/{c.hermes.id}", headers=c.admin_h)).status_code == 422
    await set_home(c.hermes, hermes_profile(tmp_path))
    assert (await c.client.post(f"{AGENTS}/{c.hermes.id}", headers=c.admin_h)).status_code == 201
    assert (await opened(c, agent_id=str(c.hermes.id)))["agent_id"] == str(c.hermes.id)


@pytest.mark.parametrize("config,problem", [
    ({}, "PROFILE_WITHOUT_FORGEHUB_MCP"),
    ({"mcp_servers": {"forgehub": {"enabled": False, "args": ["factory_server.py"]}}}, "PROFILE_WITHOUT_FORGEHUB_MCP"),
    ({"mcp_servers": {"forgehub": {"args": ["/profiles/maia/mcp/forgehub.py"]}}}, "PROFILE_MCP_WITHOUT_MAINTENANCE_TOOLS"),
    ({"mcp_servers": {"forgehub": {"args": ["x/factory_server.py"], "tools": {"exclude": ["run_remote_command"]}}}},
     "PROFILE_MCP_WITHOUT_MAINTENANCE_TOOLS"),
    ({"mcp_servers": {"forgehub": {"args": ["x/factory_server.py"], "tools": {"include": ["run_remote_command"]}}}}, None),
    ({"mcp_servers": {"forgehub": {"args": ["x/forgehub_messages_mcp.py"]}}}, None),
])
def test_hermes_profile_rule(config, problem):
    assert hermes_direct_problem(config) == problem


@pytest.mark.asyncio
async def test_agents_never_change_the_list_or_the_pause_even_with_delegation(ctx):
    c = ctx
    await opened(c)
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        db.add(AuthorityDelegation(grantor_user_id=c.admin.id, grantee_type="agent", grantee_id=c.agent.id,
                                   allowed_actions=["remote_access.execute"], servers=[str(c.lab.id)], max_risk="high",
                                   valid_from=now, expires_at=now + timedelta(hours=1)))
        await db.commit()
    # The agent's credential stops at the middleware (401); a person's session at the route.
    for headers, refused in ((c.agent_h, 401), (c.user_h, 403)):
        calls = [c.client.get(AGENTS, headers=headers), c.client.post(f"{AGENTS}/{c.other.id}", headers=headers),
                 c.client.delete(f"{AGENTS}/{c.agent.id}", headers=headers), c.client.get(CONTROL, headers=headers),
                 c.client.post(CONTROL + ":pause", json={}, headers=headers),
                 c.client.post(CONTROL + ":resume", headers=headers)]
        for call in calls:
            assert (await call).status_code == refused
    async with AsyncSessionLocal() as db:
        assert (await agent_access_control(db)).paused is False


# --- the pause ------------------------------------------------------------------

@pytest_asyncio.fixture
async def pausable(ctx):
    """Always leaves the switch active: the database is shared by the whole suite."""
    yield ctx
    async with AsyncSessionLocal() as db:
        control = await agent_access_control(db)
        control.paused, control.paused_at, control.paused_by, control.reason = False, None, None, None
        await db.execute(delete(AuditEvent).where(AuditEvent.entity_id == CONTROL_ID))
        await db.execute(delete(Notification).where(Notification.event_key.like("agent-remote-access:%")))
        await db.commit()


async def pause(c, reason=None):
    r = await c.client.post(CONTROL + ":pause", json={"reason": reason}, headers=c.admin_h)
    assert r.status_code == 200, r.text
    return r.json()


async def resume(c):
    r = await c.client.post(CONTROL + ":resume", headers=c.admin_h)
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_pause_refuses_command_and_opening_and_shows_in_the_listing(pausable):
    c = pausable
    await opened(c)
    state = await pause(c, "Incidente")
    assert state["paused"] is True and state["paused_by"] == c.admin.username and state["reason"] == "Incidente"
    assert (await c.client.get(CONTROL, headers=c.admin_h)).json()["paused"] is True
    r = await c.client.post(RUN, json=command(c), headers=c.agent_h)
    assert r.status_code == 403 and await code_of(r) == PAUSED
    r = await c.client.post(ADMIN, json=opening(c, server_ids=[str(c.lab2.id)]), headers=c.admin_h)
    assert r.status_code == 403 and await code_of(r) == PAUSED
    [machine] = (await c.client.get("/api/v1/host-executions/agent/machines", headers=c.agent_h)).json()
    assert machine["agent_access_paused"] is True and machine["runnable"] is False and machine["direct_access"] is True
    events = await audit_events(CONTROL_ID, "agent_remote_access_paused")
    [event] = [e for e in events if e.actor == c.admin.username]
    assert event.payload == {"reason": "Incidente"}


@pytest.mark.asyncio
async def test_pause_closes_nothing_and_a_valid_access_counts_again(pausable):
    c = pausable
    access = await opened(c)
    await pause(c)
    assert [a["id"] for a in (await c.client.get(ADMIN, headers=c.admin_h)).json()] == [access["id"]]
    await resume(c)
    r = await c.client.post(RUN, json=command(c), headers=c.agent_h)
    assert r.status_code == 201, r.text
    await finished(c, r.json()["id"])
    [machine] = (await c.client.get("/api/v1/host-executions/agent/machines", headers=c.agent_h)).json()
    assert machine["agent_access_paused"] is False and machine["runnable"] is True
    assert await audit_events(CONTROL_ID, "agent_remote_access_resumed")


@pytest.mark.asyncio
async def test_an_access_that_expires_during_the_pause_does_not_come_back(pausable):
    c = pausable
    access = await opened(c)
    await pause(c)
    async with AsyncSessionLocal() as db:
        row = await db.get(AuthorityDelegation, uuid.UUID(access["id"]))
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()
    await resume(c)
    r = await c.client.post(RUN, json=command(c), headers=c.agent_h)
    assert r.status_code == 403 and await code_of(r) == "NO_DIRECT_ACCESS"


@pytest.mark.asyncio
async def test_pausing_twice_and_resuming_twice_are_conflicts(pausable):
    c = pausable
    assert (await c.client.post(CONTROL + ":resume", headers=c.admin_h)).status_code == 409
    await pause(c)
    assert (await c.client.post(CONTROL + ":pause", json={}, headers=c.admin_h)).status_code == 409


@pytest.mark.asyncio
async def test_a_literal_secret_in_the_pause_reason_is_refused(pausable):
    r = await pausable.client.post(CONTROL + ":pause", json={"reason": "password=hunter2hunter2"}, headers=pausable.admin_h)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_a_pause_landing_after_the_first_check_still_stops_the_command(pausable, monkeypatch):
    """The first check passes, then the pause commits: only the check under the lock catches it."""
    c = pausable
    await opened(c)

    async def pause_midway(db):
        await pause(c)
        return {c.lab.id: (True, "complete")}

    monkeypatch.setattr(host, "_agent_readiness", pause_midway)
    r = await c.client.post(RUN, json=command(c), headers=c.agent_h)
    assert r.status_code == 403 and await code_of(r) == PAUSED
    async with AsyncSessionLocal() as db:
        assert await db.scalar(select(func.count()).select_from(HostExecution).where(HostExecution.agent_id == c.agent.id)) == 0


@pytest.mark.asyncio
async def test_a_pause_waits_for_a_command_being_recorded(pausable):
    c = pausable
    async with AsyncSessionLocal() as db:
        await agent_access_control(db, lock=True)
        pending = asyncio.create_task(c.client.post(CONTROL + ":pause", json={}, headers=c.admin_h))
        await asyncio.sleep(0.3)
        assert not pending.done()
        await db.commit()
    assert (await pending).status_code == 200


@pytest.mark.asyncio
async def test_a_running_command_finishes_during_the_pause(pausable, monkeypatch):
    c = pausable
    release = asyncio.Event()

    async def slow(*args):
        await release.wait()
        return dict(exit_code=0, stdout="done", stderr="", duration_ms=1, failure=None)

    monkeypatch.setattr(host_exec_runner, "call_bridge_exec", slow)
    await opened(c)
    run = await c.client.post(RUN, json=command(c), headers=c.agent_h)
    await pause(c)
    release.set()
    await finished(c, run.json()["id"])
    async with AsyncSessionLocal() as db:
        result = await db.scalar(select(HostExecutionResult).where(HostExecutionResult.execution_id == uuid.UUID(run.json()["id"])))
        assert result.status == "succeeded"


@pytest.mark.asyncio
async def test_agent_schedules_wait_and_people_are_not_affected(pausable):
    from app.api.routes.host_script import run_due_schedules

    c = pausable
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    async with AsyncSessionLocal() as db:
        category = await db.scalar(select(HostScriptCategory).limit(1))
        script = HostScript(name="pause-script-" + uuid.uuid4().hex, category_id=category.id, platform="linux",
                            content="echo ok", risk="read", created_by="t", updated_by="t", timeout_seconds=30)
        db.add(script)
        await db.flush()
        shape = dict(script_id=script.id, server_ids=[str(c.lab.id)], group_ids=[], kind="once", run_at=past,
                     next_run_at=past, created_by="t", parameter_values={})
        by_agent = HostSchedule(name="pause-agent", agent_id=c.agent.id, **shape)
        by_person = HostSchedule(name="pause-person", **shape)
        db.add_all([by_agent, by_person])
        await db.commit()
    try:
        await pause(c)
        assert await run_due_schedules() == 1
        r = await c.client.post(f"/api/v1/host-schedules/{by_agent.id}:run-now", headers=c.admin_h)
        assert r.status_code == 403 and await code_of(r) == PAUSED
        async with AsyncSessionLocal() as db:
            assert (await db.get(HostSchedule, by_agent.id)).enabled is True
            assert (await db.get(HostSchedule, by_person.id)).last_execution_id is not None
        await resume(c)
        assert await run_due_schedules() == 1
    finally:
        for pending in list(host_exec_runner._running.values()):
            await pending
        async with AsyncSessionLocal() as db:
            runs = select(HostExecution.id).where(HostExecution.schedule_id.in_([by_agent.id, by_person.id]))
            await db.execute(delete(AuditEvent).where(AuditEvent.entity_id.in_(runs)))
            await db.execute(delete(HostExecution).where(HostExecution.schedule_id.in_([by_agent.id, by_person.id])))
            await db.execute(delete(HostScript).where(HostScript.id == script.id))
            await db.commit()

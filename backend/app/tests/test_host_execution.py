"""Remote Access phase 4 — command executions. The host-bridge call is mocked;
everything else (rows, skip rules, background run, follow-up, cancel, busy)
runs for real. Only rows created here are touched and deleted."""
import asyncio
import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.api.routes import host_execution as routes
from app.api.routes import server as server_routes
from app.core import host_exec_runner
from app.core.secret_masking import MASK, mask_secrets
from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.governance import AuditEvent
from app.db.models.host_execution import HostExecution
from app.db.models.server import Server


@pytest_asyncio.fixture
async def client(admin_headers):
    app = FastAPI()
    app.include_router(routes.router)
    app.include_router(server_routes.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=admin_headers) as ac:
        yield ac


@pytest_asyncio.fixture
async def machines():
    tag = uuid.uuid4().hex[:8]
    rows = {
        "linux": Server(name=f"lin-{tag}", ip_address="100.127.9.1", remote_user="darckware", os_family="linux", kind="workstation"),
        "linux2": Server(name=f"lin2-{tag}", ip_address="100.127.9.2", remote_user="darckware", os_family="linux", kind="workstation"),
        "windows": Server(name=f"win-{tag}", ip_address="100.127.9.3", remote_user="darckware", os_family="windows", kind="workstation"),
        "parked": Server(name=f"off-{tag}", ip_address="100.127.9.4", remote_user="darckware", os_family="linux", access_enabled=False),
        "nologin": Server(name=f"new-{tag}", ip_address="100.127.9.5", remote_user="", os_family="linux"),
    }
    async with AsyncSessionLocal() as db:
        db.add_all(rows.values())
        await db.commit()
    created: list[uuid.UUID] = []
    yield rows, created
    for task in list(host_exec_runner._running.values()):
        await asyncio.wait_for(task, timeout=10)
    async with AsyncSessionLocal() as db:
        if created:
            await db.execute(delete(AuditEvent).where(AuditEvent.entity_id.in_(created)))
            await db.execute(delete(HostExecution).where(HostExecution.id.in_(created)))
        await db.execute(delete(Server).where(Server.id.in_([r.id for r in rows.values()])))
        await db.commit()


async def _wait(execution_id: str) -> None:
    task = host_exec_runner._running.get(uuid.UUID(execution_id))
    if task:
        await asyncio.wait_for(task, timeout=10)


def test_mask_secrets_patterns_and_known_values():
    text = (
        "net user darckware S3nh@Forte! /add\n"
        "$p = ConvertTo-SecureString 'Abc123!x' -AsPlainText -Force\n"
        "PASSWORD=hunter22 curl -H 'Authorization: Bearer abcdefghijkl'\n"
        "-----BEGIN OPENSSH PRIVATE KEY-----\nAAAA\n-----END OPENSSH PRIVATE KEY-----\n"
        "generated: Zq9-unique-pass"
    )
    masked = mask_secrets(text, ["Zq9-unique-pass"])
    for secret in ("S3nh@Forte!", "Abc123!x", "hunter22", "abcdefghijkl", "AAAA", "Zq9-unique-pass"):
        assert secret not in masked
    assert "net user darckware " + MASK + " /add" in masked
    assert mask_secrets("net user darckware /delete") == "net user darckware /delete"


@pytest.mark.asyncio
async def test_run_skips_with_reasons_and_masks_output(client, machines):
    rows, created = machines

    async def fake_bridge(server, shell, script, timeout):
        return {"exit_code": 0, "stdout": f"ok {server.name} token=xyz12345", "stderr": "", "duration_ms": 12, "failure": None}

    with patch.object(host_exec_runner, "call_bridge_exec", fake_bridge):
        resp = await client.post("/api/v1/host-executions", json={
            "command": "uptime # password=s3cret99", "shell": "sh", "confirmation": "CONFIRMAR",
            "server_ids": [str(r.id) for r in rows.values()],
        })
        assert resp.status_code == 201, resp.text
        execution_id = resp.json()["id"]
        created.append(uuid.UUID(execution_id))
        await _wait(execution_id)

    detail = (await client.get(f"/api/v1/host-executions/{execution_id}")).json()
    by_name = {r["server_name"]: r for r in detail["results"]}
    assert by_name[rows["linux"].name]["status"] == "succeeded", by_name[rows["linux"].name]
    assert "xyz12345" not in by_name[rows["linux"].name]["stdout"]
    assert by_name[rows["windows"].name]["skip_reason"] == "sh does not run on Windows machines"
    assert by_name[rows["parked"].name]["status"] == "skipped"
    assert by_name[rows["nologin"].name]["skip_reason"] == "No login set for this machine yet"
    assert detail["counts"]["succeeded"] == 2 and detail["counts"]["skipped"] == 3
    assert detail["verdict"] == "succeeded" and detail["status"] == "completed"
    assert "s3cret99" not in detail["command"]

    async with AsyncSessionLocal() as db:
        audit = (await db.execute(select(AuditEvent).where(AuditEvent.entity_id == uuid.UUID(execution_id)))).scalar_one()
        assert audit.entity_type == "host_execution" and "s3cret99" not in str(audit.payload)


@pytest.mark.asyncio
async def test_typed_login_runs_where_forgehub_has_no_access(client, machines):
    """ForgeHub's own key first; the login typed for this run only where that
    key is refused or there is none -- password never stored."""
    rows, created = machines
    own, typed = [], []
    async with AsyncSessionLocal() as db:
        for name in ("linux", "linux2"):
            (await db.get(Server, rows[name].id)).ssh_key_path = "/root/.ssh/forgehub_test_key"
        await db.commit()

    async def fake_own(server, shell, script, timeout):
        own.append(server.name)
        if server.id == rows["linux2"].id:
            return {"failure": "auth", "stderr": "Permission denied"}
        return {"exit_code": 0, "stdout": "own", "stderr": "", "duration_ms": 1, "failure": None}

    async def fake_as(**kw):
        typed.append((kw["host"], kw["user"], kw["password"], kw["key_path"]))
        return {"exit_code": 0, "stdout": "typed Pw-9x!typed", "stderr": "", "duration_ms": 1, "failure": None}

    try:
        assert (await client.post("/api/v1/host-executions", json={
            "command": "uptime", "shell": "sh", "confirmation": "CONFIRMAR", "server_ids": [str(rows["linux"].id)], "login_user": "suporte",
        })).status_code == 422  # login without password
        with (
            patch.object(host_exec_runner, "call_bridge_exec", fake_own),
            patch.object(host_exec_runner, "call_bridge_exec_as", fake_as),
        ):
            resp = await client.post("/api/v1/host-executions", json={
                "command": "uptime", "shell": "sh", "confirmation": "CONFIRMAR",
                "server_ids": [str(rows["linux"].id), str(rows["linux2"].id), str(rows["nologin"].id)],
                "login_user": "suporte", "login_password": "Pw-9x!typed",
            })
            assert resp.status_code == 201, resp.text
            execution_id = resp.json()["id"]
            created.append(uuid.UUID(execution_id))
            await _wait(execution_id)
    finally:
        server_routes._ssh_probe_cache.update({"at": None, "statuses": {}})

    assert sorted(own) == sorted([rows["linux"].name, rows["linux2"].name])
    assert sorted(t[0] for t in typed) == ["100.127.9.2", "100.127.9.5"]  # incl. the machine with no login
    assert all(t[1:] == ("suporte", "Pw-9x!typed", None) for t in typed)
    detail = (await client.get(f"/api/v1/host-executions/{execution_id}")).json()
    assert detail["counts"]["succeeded"] == 3
    assert all("Pw-9x!typed" not in (r["stdout"] or "") for r in detail["results"])
    async with AsyncSessionLocal() as db:
        events = (await db.execute(select(AuditEvent).where(AuditEvent.entity_id == uuid.UUID(execution_id)))).scalars().all()
    assert {e.event_type for e in events} == {"started", "typed_login_used"}
    assert all("Pw-9x!typed" not in str(e.payload) for e in events)


@pytest.mark.asyncio
async def test_failure_then_follow_up_only_on_failed(client, machines):
    rows, created = machines
    ok_id, bad_id = rows["linux"].id, rows["linux2"].id

    async def fake_bridge(server, shell, script, timeout):
        if server.id == bad_id and "fix" not in script:
            return {"exit_code": 2, "stdout": "", "stderr": "disk full", "duration_ms": 5, "failure": "command"}
        return {"exit_code": 0, "stdout": "fine", "stderr": "", "duration_ms": 5, "failure": None}

    with patch.object(host_exec_runner, "call_bridge_exec", fake_bridge):
        first = (await client.post("/api/v1/host-executions", json={
            "command": "apt-get update", "shell": "sh", "confirmation": "CONFIRMAR", "server_ids": [str(ok_id), str(bad_id)],
        })).json()
        created.append(uuid.UUID(first["id"]))
        await _wait(first["id"])
        detail = (await client.get(f"/api/v1/host-executions/{first['id']}")).json()
        assert detail["verdict"] == "failed"
        failed = next(r for r in detail["results"] if r["status"] == "failed")
        assert failed["exit_code"] == 2 and failed["failure"] == "command" and failed["stderr"] == "disk full"

        follow = await client.post(f"/api/v1/host-executions/{first['id']}:follow-up",
                                   json={"command": "fix-disk && apt-get update", "shell": "sh"})
        assert follow.status_code == 201, follow.text
        created.append(uuid.UUID(follow.json()["id"]))
        await _wait(follow.json()["id"])

    second = (await client.get(f"/api/v1/host-executions/{follow.json()['id']}")).json()
    assert [r["server_id"] for r in second["results"]] == [str(bad_id)]
    assert second["parent_execution_id"] == first["id"] and second["verdict"] == "succeeded"
    parent = (await client.get(f"/api/v1/host-executions/{first['id']}")).json()
    assert parent["follow_up_ids"] == [follow.json()["id"]]

    # Nothing failed in the follow-up: a second follow-up has no target.
    again = await client.post(f"/api/v1/host-executions/{second['id']}:follow-up", json={"command": "x", "shell": "sh"})
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_busy_machine_is_skipped_and_reads_busy_until_done(client, machines):
    rows, created = machines
    release = asyncio.Event()

    async def slow_bridge(server, shell, script, timeout):
        await release.wait()
        return {"exit_code": 0, "stdout": "", "stderr": "", "duration_ms": 1, "failure": None}

    with patch.object(host_exec_runner, "call_bridge_exec", slow_bridge):
        first = (await client.post("/api/v1/host-executions", json={
            "command": "sleep", "shell": "sh", "confirmation": "CONFIRMAR", "server_ids": [str(rows["linux"].id)],
        })).json()
        created.append(uuid.UUID(first["id"]))
        await asyncio.sleep(0.2)

        second = (await client.post("/api/v1/host-executions", json={
            "command": "uptime", "shell": "sh", "confirmation": "CONFIRMAR", "server_ids": [str(rows["linux"].id)],
        })).json()
        created.append(uuid.UUID(second["id"]))
        assert second["results"][0]["skip_reason"] == "Already running another command"

        async with AsyncSessionLocal() as db:
            assert rows["linux"].id in await routes.busy_server_ids(db)

        release.set()
        await _wait(first["id"])
        await _wait(second["id"])
    async with AsyncSessionLocal() as db:
        assert rows["linux"].id not in await routes.busy_server_ids(db)


@pytest.mark.asyncio
async def test_cancel_skips_machines_not_started(client, machines):
    rows, created = machines
    release = asyncio.Event()

    async def slow_bridge(server, shell, script, timeout):
        await release.wait()
        return {"exit_code": 0, "stdout": "", "stderr": "", "duration_ms": 1, "failure": None}

    with (
        patch.object(host_exec_runner, "call_bridge_exec", slow_bridge),
        patch.object(host_exec_runner, "MAX_PARALLEL", 1),
    ):
        resp = (await client.post("/api/v1/host-executions", json={
            "command": "uptime", "shell": "sh", "confirmation": "CONFIRMAR", "server_ids": [str(rows["linux"].id), str(rows["linux2"].id)],
        })).json()
        created.append(uuid.UUID(resp["id"]))
        await asyncio.sleep(0.2)
        cancelled = await client.post(f"/api/v1/host-executions/{resp['id']}:cancel")
        assert cancelled.status_code == 200
        release.set()
        await _wait(resp["id"])

    detail = (await client.get(f"/api/v1/host-executions/{resp['id']}")).json()
    assert detail["status"] == "cancelled"
    statuses = sorted(r["status"] for r in detail["results"])
    assert statuses == ["skipped", "succeeded"]
    assert (await client.post(f"/api/v1/host-executions/{resp['id']}:cancel")).status_code == 409


@pytest.mark.asyncio
async def test_rejects_empty_and_unknown_targets(client, machines):
    assert (await client.post("/api/v1/host-executions", json={"command": "x", "shell": "sh"})).status_code == 422
    unknown = await client.post("/api/v1/host-executions", json={
        "command": "x", "shell": "sh", "confirmation": "CONFIRMAR", "server_ids": [str(uuid.uuid4())],
    })
    assert unknown.status_code == 422


@pytest.mark.asyncio
async def test_recovery_closes_only_stale_executions(machines):
    from datetime import datetime, timedelta, timezone

    from app.db.models.host_execution import HostExecutionResult

    rows, created = machines
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        stale = HostExecution(shell="sh", command="x", timeout_seconds=60, status="running", requested_by="test",
                              started_at=now - timedelta(minutes=10), heartbeat_at=now - timedelta(minutes=5))
        live = HostExecution(shell="sh", command="x", timeout_seconds=60, status="running", requested_by="test",
                             started_at=now - timedelta(minutes=10), heartbeat_at=now)
        db.add_all([stale, live])
        await db.flush()
        created += [stale.id, live.id]
        for execution in (stale, live):
            db.add(HostExecutionResult(execution_id=execution.id, server_id=rows["linux"].id,
                                       server_name="x", status="running"))
        await db.commit()

    await host_exec_runner.recover_interrupted_executions()

    async with AsyncSessionLocal() as db:
        assert (await db.get(HostExecution, stale.id)).status == "completed"
        assert (await db.get(HostExecution, live.id)).status == "running"
        stale_result = (await db.execute(select(HostExecutionResult).where(HostExecutionResult.execution_id == stale.id))).scalar_one()
        assert stale_result.status == "failed" and stale_result.failure == "interrupted"
        # Close the live one so it doesn't leave the machine "busy".
        (await db.get(HostExecution, live.id)).status = "completed"
        await db.commit()


@pytest.mark.asyncio
async def test_agent_maintenance_needs_delegation_reason_and_a_prepared_machine(machines):
    """Agents run library scripts with their own agt_ credential: deny by
    default, risk capped by the delegation, only on machines ForgeHub already
    has its login on, and the run is recorded as theirs with its reason --
    then shows in the machine's maintenance history."""
    import hashlib
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace

    from app.core.security import hash_password
    from app.db.models.agent import Agent, AgentServiceCredential
    from app.db.models.demand import AgentDemand
    from app.db.models.governance import AuthorityDelegation
    from app.db.models.host_script import HostScript, HostScriptCategory
    from app.db.models.user import User
    from app.main import app

    rows, created = machines
    tag = uuid.uuid4().hex[:8]
    token = f"agt_test_{tag}"
    async with AsyncSessionLocal() as db:
        grantor = User(username=f"grantor-{tag}", hashed_password=hash_password("x"), is_admin=True)
        agent = Agent(name=f"maint-agent-{tag}", agent_type="executor")
        category = (await db.execute(select(HostScriptCategory).limit(1))).scalar_one()
        script = HostScript(name=f"diag-{tag}", category_id=category.id, platform="linux", risk="read",
                            timeout_seconds=30, parameters=[], content="uptime", current_version=1,
                            created_by="t", updated_by="t")
        risky = HostScript(name=f"wipe-{tag}", category_id=category.id, platform="linux", risk="destructive",
                           timeout_seconds=30, parameters=[], content="true", current_version=1,
                           created_by="t", updated_by="t")
        db.add_all([grantor, agent, script, risky])
        await db.flush()
        db.add(AgentServiceCredential(agent_id=agent.id, label="test", token_hash=hashlib.sha256(token.encode()).hexdigest()))
        # A task addressed to the agent, never scheduled (nothing dispatches it).
        task = AgentDemand(from_agent="t", subject=f"maint {tag}", body="x", origin_type="task",
                           target_agent_id=agent.id, from_agent_id=agent.id)
        other = AgentDemand(from_agent="t", subject=f"other {tag}", body="x", origin_type="task")
        db.add_all([task, other])
        await db.flush()
        # "Pedir ao agente" recorded what this task allows.
        db.add(AuditEvent(entity_type="agent_maintenance_request", entity_id=task.id, event_type="created", actor="t",
                          payload={"server_ids": [str(rows["linux"].id)], "script_ids": [str(script.id)]}))
        await db.commit()
        ids = SimpleNamespace(grantor=grantor.id, agent=agent.id, script=script.id, risky=risky.id,
                              task=task.id, number=task.number, other=other.number)

    ready = {rows["linux"].id: "ready"}

    async def fake_readiness(**_kw):
        return SimpleNamespace(entries=[
            SimpleNamespace(server_id=r.id, readiness=ready.get(r.id, "not_prepared"), status="complete")
            for r in rows.values()
        ])

    async def fake_bridge(server, shell, script, timeout):
        return {"exit_code": 0, "stdout": "up 3 days", "stderr": "", "duration_ms": 5, "failure": None}

    body = {"script_id": str(ids.script), "server_ids": [str(rows["linux"].id)], "reason": "Cliente relatou lentidão",
            "message_number": ids.number}
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers) as ac:
            with (
                patch.object(server_routes, "get_readiness", fake_readiness),
                patch.object(host_exec_runner, "call_bridge_exec", fake_bridge),
            ):
                assert (await ac.post("/api/v1/host-executions/agent", json=body)).status_code == 403  # no delegation
                async with AsyncSessionLocal() as db:
                    now = datetime.now(timezone.utc)
                    db.add(AuthorityDelegation(
                        grantor_user_id=ids.grantor, grantee_type="agent", grantee_id=ids.agent,
                        allowed_actions=["remote_access.execute"], max_risk="medium",
                        valid_from=now - timedelta(minutes=1), expires_at=now + timedelta(hours=1),
                    ))
                    await db.commit()
                machines_list = (await ac.get("/api/v1/host-executions/agent/machines")).json()
                assert {m["name"]: m["runnable"] for m in machines_list}[rows["linux"].name] is True
                scripts = (await ac.get("/api/v1/host-executions/agent/scripts")).json()
                assert any(s["id"] == str(ids.script) for s in scripts)
                assert (await ac.post("/api/v1/host-executions/agent", json={**body, "script_id": str(ids.risky)})).status_code == 403
                assert (await ac.post("/api/v1/host-executions/agent", json={**body, "reason": ""})).status_code == 422
                no_task = {k: v for k, v in body.items() if k != "message_number"}
                assert (await ac.post("/api/v1/host-executions/agent", json=no_task)).status_code == 422
                assert (await ac.post("/api/v1/host-executions/agent", json={**body, "message_number": ids.other})).status_code == 403
                ready[rows["linux2"].id] = "ready"  # ready, but not in the task
                outside = await ac.post("/api/v1/host-executions/agent", json={**body, "server_ids": [str(rows["linux2"].id)]})
                assert outside.status_code == 403 and "Not in task" in outside.json()["detail"]
                del ready[rows["linux2"].id]
                not_ready = await ac.post("/api/v1/host-executions/agent", json={**body, "server_ids": [str(rows["linux2"].id)]})
                assert not_ready.status_code == 409 and rows["linux2"].name in not_ready.json()["detail"]

                resp = await ac.post("/api/v1/host-executions/agent", json={**body, "darckware_item_kind": "ticket", "darckware_item_id": "T-42"})
                assert resp.status_code == 201, resp.text
                execution_id = resp.json()["id"]
                created.append(uuid.UUID(execution_id))
                await _wait(execution_id)
                got = (await ac.get(f"/api/v1/host-executions/agent/{execution_id}")).json()
                assert got["trigger"] == "agent" and got["agent_name"] == f"maint-agent-{tag}"
                assert got["reason"] == "Cliente relatou lentidão" and got["darckware_item_id"] == "T-42"
                assert got["counts"]["succeeded"] == 1 and got["agent_demand_id"] == str(ids.task)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                               headers={"Authorization": f"Bearer {create_access_token(f'grantor-{tag}')}"}) as ac:
            history = (await ac.get(f"/api/v1/servers/{rows['linux'].id}/maintenance")).json()
        entry = next(h for h in history if h["execution_id"] == execution_id)
        assert entry["actor"] == f"maint-agent-{tag}" and entry["reason"] == "Cliente relatou lentidão"
        assert entry["kind"] == "execution" and entry["darckware_item_kind"] == "ticket"
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AuditEvent).where(AuditEvent.entity_id.in_(created)))
            await db.execute(delete(HostExecution).where(HostExecution.id.in_(created)))
            created.clear()
            await db.execute(delete(AuthorityDelegation).where(AuthorityDelegation.grantee_id == ids.agent))
            await db.execute(delete(AgentServiceCredential).where(AgentServiceCredential.agent_id == ids.agent))
            await db.execute(delete(AuditEvent).where(AuditEvent.entity_id == ids.task))
            await db.execute(delete(AgentDemand).where(AgentDemand.number.in_([ids.number, ids.other])))
            await db.execute(delete(HostScript).where(HostScript.id.in_([ids.script, ids.risky])))
            await db.execute(delete(Agent).where(Agent.id == ids.agent))
            await db.execute(delete(User).where(User.id == ids.grantor))
            await db.commit()


@pytest.mark.asyncio
async def test_agent_request_creates_one_task_per_authorized_agent(client, machines):
    """"Pedir ao agente": refused for an agent without the delegation or below
    the scripts' risk, for an unprepared machine, and for secret values;
    otherwise one self-addressed Task per agent, logged on each machine."""
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace

    from app.api.routes import demand as demand_routes
    from app.core.security import hash_password
    from app.db.models.agent import Agent
    from app.db.models.demand import AgentDemand
    from app.db.models.governance import AuthorityDelegation
    from app.db.models.host_script import HostScript, HostScriptCategory
    from app.db.models.user import User

    rows, _ = machines
    tag = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        grantor = User(username=f"grantor2-{tag}", hashed_password=hash_password("x"), is_admin=True)
        low = Agent(name=f"low-{tag}", agent_type="executor")
        mid = Agent(name=f"mid-{tag}", agent_type="executor")
        none = Agent(name=f"none-{tag}", agent_type="executor")
        category = (await db.execute(select(HostScriptCategory).limit(1))).scalar_one()
        change = HostScript(name=f"fix-{tag}", category_id=category.id, platform="linux", risk="change", timeout_seconds=30,
                            parameters=[{"name": "SERVICE", "label": "S", "required": True, "default": None, "secret": False},
                                        {"name": "PASS", "label": "P", "required": False, "default": None, "secret": True}],
                            content="true", current_version=1, created_by="t", updated_by="t")
        db.add_all([grantor, low, mid, none, change])
        await db.flush()
        now = datetime.now(timezone.utc)
        for agent, risk in ((low, "low"), (mid, "medium")):
            db.add(AuthorityDelegation(grantor_user_id=grantor.id, grantee_type="agent", grantee_id=agent.id,
                                       allowed_actions=["remote_access.execute"], max_risk=risk,
                                       valid_from=now - timedelta(minutes=1), expires_at=now + timedelta(days=1)))
        await db.commit()
        ids = SimpleNamespace(grantor=grantor.id, low=low.id, mid=mid.id, none=none.id, change=change.id)

    async def fake_readiness(**_kw):
        return SimpleNamespace(entries=[SimpleNamespace(server_id=r.id, readiness="ready" if r is rows["linux"] else "not_prepared",
                                                        status="complete") for r in rows.values()])

    sent = []

    async def fake_create(db, payload, commit=True):
        # A real row, never scheduled: nothing dispatches it.
        sent.append(payload)
        demand = AgentDemand(from_agent=payload.from_agent, subject=payload.subject, body=payload.body,
                             origin_type="task", target_agent_id=payload.target_agent_id, from_agent_id=payload.from_agent_id)
        db.add(demand)
        return demand

    base = {"server_ids": [str(rows["linux"].id)], "instruction": "Reiniciar o spooler travado",
            "scripts": [{"script_id": str(ids.change), "parameter_values": {"SERVICE": "spooler"}}],
            "darckware_item_kind": "ticket", "darckware_item_id": "T-9"}
    try:
        with patch.object(server_routes, "get_readiness", fake_readiness), patch.object(demand_routes, "create_demand_and_notify", fake_create):
            r = await client.post("/api/v1/host-executions/agent-requests", json={**base, "agent_ids": [str(ids.none)]})
            assert r.status_code == 422 and f"none-{tag}" in r.json()["detail"]
            r = await client.post("/api/v1/host-executions/agent-requests", json={**base, "agent_ids": [str(ids.low)]})
            assert r.status_code == 422  # a "change" script is above a low ceiling
            r = await client.post("/api/v1/host-executions/agent-requests",
                                  json={**base, "agent_ids": [str(ids.mid)], "server_ids": [str(rows["linux2"].id)]})
            assert r.status_code == 409
            secret = {**base, "scripts": [{"script_id": str(ids.change), "parameter_values": {"SERVICE": "x", "PASS": "s3cr3t"}}]}
            assert (await client.post("/api/v1/host-executions/agent-requests", json={**secret, "agent_ids": [str(ids.mid)]})).status_code == 422
            assert sent == []

            r = await client.post("/api/v1/host-executions/agent-requests", json={**base, "agent_ids": [str(ids.mid)]})
            assert r.status_code == 201, r.text
            assert r.json()[0]["agent_name"] == f"mid-{tag}"
            # Free text only: no script restriction, any authorized ceiling.
            r = await client.post("/api/v1/host-executions/agent-requests",
                                  json={**base, "scripts": [], "agent_ids": [str(ids.low), str(ids.mid)]})
            assert r.status_code == 201 and len(r.json()) == 2
        task = sent[0]
        assert task.origin_type == "task" and task.target_agent_id == task.from_agent_id == ids.mid
        async with AsyncSessionLocal() as db:
            stored = (await db.execute(select(AgentDemand).where(AgentDemand.subject == task.subject[:255],
                                                                 AgentDemand.target_agent_id == ids.mid))).scalars().first()
            assert f"Esta é a tarefa #{stored.number}" in stored.body  # the agent knows its message_number
            spec = (await db.execute(select(AuditEvent).where(AuditEvent.entity_type == "agent_maintenance_request",
                                                              AuditEvent.entity_id == stored.id))).scalar_one()
            assert spec.payload["server_ids"] == [str(rows["linux"].id)] and spec.payload["script_ids"] == [str(ids.change)]
        assert str(rows["linux"].id) in task.body and str(ids.change) in task.body and "SERVICE=spooler" in task.body
        assert 'darckware_ticket_id="T-9"' in task.body
        assert "list_maintenance_scripts" in sent[1].body and len(sent) == 3
        history = (await client.get(f"/api/v1/servers/{rows['linux'].id}/maintenance")).json()
        assert any(h["title"].startswith(f"Tarefa pedida ao agente mid-{tag}") for h in history)
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AuditEvent).where(AuditEvent.event_type == "agent_task_requested",
                                                      AuditEvent.entity_id.in_([r.id for r in rows.values()])))
            demand_ids = list((await db.execute(select(AgentDemand.id).where(
                AgentDemand.target_agent_id.in_([ids.low, ids.mid])))).scalars())
            await db.execute(delete(AuditEvent).where(AuditEvent.entity_id.in_(demand_ids)))
            await db.execute(delete(AgentDemand).where(AgentDemand.id.in_(demand_ids)))
            await db.execute(delete(AuthorityDelegation).where(AuthorityDelegation.grantor_user_id == ids.grantor))
            await db.execute(delete(HostScript).where(HostScript.id == ids.change))
            await db.execute(delete(Agent).where(Agent.id.in_([ids.low, ids.mid, ids.none])))
            await db.execute(delete(User).where(User.id == ids.grantor))
            await db.commit()


@pytest.mark.asyncio
async def test_delegation_expiry_warns_once_in_the_last_week():
    from datetime import datetime, timedelta, timezone

    from app.core.security import hash_password
    from app.db.models.agent import Agent
    from app.db.models.governance import AuthorityDelegation
    from app.db.models.notification import Notification
    from app.db.models.user import User

    tag = uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        grantor = User(username=f"exp-{tag}", hashed_password=hash_password("x"), is_admin=True)
        agent = Agent(name=f"exp-agent-{tag}", agent_type="executor")
        db.add_all([grantor, agent])
        await db.flush()
        soon = AuthorityDelegation(grantor_user_id=grantor.id, grantee_type="agent", grantee_id=agent.id,
                                   allowed_actions=["remote_access.execute"], max_risk="low",
                                   valid_from=now, expires_at=now + timedelta(days=3))
        later = AuthorityDelegation(grantor_user_id=grantor.id, grantee_type="agent", grantee_id=agent.id,
                                    allowed_actions=["remote_access.execute"], max_risk="low",
                                    valid_from=now, expires_at=now + timedelta(days=30))
        db.add_all([soon, later])
        await db.commit()
    keys = [f"delegation-expiring:{soon.id}", f"delegation-expiring:{later.id}"]
    try:
        await routes.run_delegation_expiry_pass()
        await routes.run_delegation_expiry_pass()  # deduplicated
        async with AsyncSessionLocal() as db:
            found = (await db.execute(select(Notification).where(Notification.event_key.in_(keys)))).scalars().all()
        assert [n.event_key for n in found] == [keys[0]] and f"exp-agent-{tag}" in found[0].title
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Notification).where(Notification.event_key.in_(keys)))
            await db.execute(delete(AuthorityDelegation).where(AuthorityDelegation.grantee_id == agent.id))
            await db.execute(delete(Agent).where(Agent.id == agent.id))
            await db.execute(delete(User).where(User.id == grantor.id))
            await db.commit()


@pytest.mark.asyncio
async def test_canary_stops_after_a_failing_first_machine_and_confirmation_is_required(client, machines):
    rows, created = machines
    ran = []

    async def failing_bridge(server, shell, script, timeout):
        ran.append(server.name)
        return {"exit_code": 1, "stdout": "", "stderr": "boom", "duration_ms": 1, "failure": "command"}

    ids = [str(rows["linux"].id), str(rows["linux2"].id)]
    body = {"command": "true", "shell": "sh", "server_ids": ids, "canary": True}
    assert (await client.post("/api/v1/host-executions", json=body)).status_code == 422  # word missing
    with patch.object(host_exec_runner, "call_bridge_exec", failing_bridge):
        resp = await client.post("/api/v1/host-executions", json={**body, "confirmation": "confirmar"})
        assert resp.status_code == 201, resp.text
        execution_id = resp.json()["id"]
        created.append(uuid.UUID(execution_id))
        await _wait(execution_id)
    assert len(ran) == 1  # only the canary ran
    detail = (await client.get(f"/api/v1/host-executions/{execution_id}")).json()
    skipped = [r for r in detail["results"] if r["status"] == "skipped"]
    assert len(skipped) == 1 and skipped[0]["skip_reason"] == host_exec_runner.CANARY_SKIP_REASON


@pytest.mark.asyncio
async def test_stop_all_cancels_every_running_execution(client, machines):
    rows, created = machines
    gate = asyncio.Event()

    async def slow_bridge(server, shell, script, timeout):
        await gate.wait()
        return {"exit_code": 0, "stdout": "", "stderr": "", "duration_ms": 1, "failure": None}

    with patch.object(host_exec_runner, "call_bridge_exec", slow_bridge), patch.object(host_exec_runner, "MAX_PARALLEL", 1):
        resp = await client.post("/api/v1/host-executions", json={
            "command": "true", "shell": "sh", "confirmation": "CONFIRMAR",
            "server_ids": [str(rows["linux"].id), str(rows["linux2"].id)]})
        execution_id = resp.json()["id"]
        created.append(uuid.UUID(execution_id))
        await asyncio.sleep(0.2)
        async with AsyncSessionLocal() as db:
            others = (await db.execute(select(HostExecution.id).where(
                HostExecution.status == "running", HostExecution.id != uuid.UUID(execution_id)))).scalars().all()
        if others:  # the database is shared with production: never stop a real run
            gate.set()
            await _wait(execution_id)
            pytest.skip("another execution is running; stop-all would cancel it")
        stopped = (await client.post("/api/v1/host-executions/running:cancel")).json()
        assert stopped["cancelled"] >= 1 and stopped["machines_skipped"] >= 1
        gate.set()
        await _wait(execution_id)
    detail = (await client.get(f"/api/v1/host-executions/{execution_id}")).json()
    assert detail["status"] == "cancelled" and detail["counts"]["skipped"] == 1

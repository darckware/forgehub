"""Script library, parameters, schedules and per-agent execution logs
(Remote Access plan step 1). The bridge is mocked; only rows created here are
touched and deleted."""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.api.routes import host_execution as exec_routes
from app.api.routes import host_script as script_routes
from app.core import host_exec_runner
from app.core.host_scripts import ScriptError, compatible, next_run, render_script, resolve_values, validate_parameters
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.governance import AuditEvent
from app.db.models.host_execution import HostExecution
from app.db.models.host_script import HostSchedule, HostScript, HostScriptCategory
from app.db.models.server import Server

SP = "America/Sao_Paulo"


# --- pure helpers -------------------------------------------------------------

def test_parameters_are_quoted_never_spliced():
    params = validate_parameters([{"name": "SERVICE", "required": True}, {"name": "NOTE", "default": "x"}])
    values, _ = resolve_values(params, {"SERVICE": "wuauserv'; Remove-Item C:\\ -Recurse #"})
    ps = render_script("windows", "Restart-Service $SERVICE", values)
    assert ps.startswith("$SERVICE = 'wuauserv''; Remove-Item C:\\ -Recurse #'\n$NOTE = 'x'\n")
    sh = render_script("linux", 'systemctl restart "$SERVICE"', {"SERVICE": "a'; rm -rf / #"})
    assert sh.startswith("SERVICE='a'\"'\"'; rm -rf / #'\n")


def test_parameter_validation():
    with pytest.raises(ScriptError):
        validate_parameters([{"name": "bad-name"}])
    with pytest.raises(ScriptError):
        validate_parameters([{"name": "A"}, {"name": "A"}])
    params = validate_parameters([{"name": "PW", "required": True, "secret": True}])
    with pytest.raises(ScriptError):
        resolve_values(params, {})
    with pytest.raises(ScriptError):
        resolve_values(params, {"OTHER": "x"})
    assert resolve_values(params, {"PW": "s3cret"}) == ({"PW": "s3cret"}, ["s3cret"])


def test_platform_compatibility():
    assert compatible("windows", "windows") and not compatible("windows", "linux")
    assert compatible("linux", None) and compatible("linux", "linux") and not compatible("linux", "macos")
    assert compatible("macos", "macos") and not compatible("macos", None)


def test_next_run_weekly_in_client_timezone():
    # Thursday 2026-10-15 23:00 UTC = 20:00 in São Paulo (UTC-3).
    after = datetime(2026, 10, 15, 23, 0, tzinfo=timezone.utc)
    nxt = next_run("weekly", None, [1, 4], "22:00", SP, after)  # Mon/Thu 22:00 local
    assert nxt == datetime(2026, 10, 16, 1, 0, tzinfo=timezone.utc)  # Thu 22:00 local
    again = next_run("weekly", None, [1, 4], "22:00", SP, nxt)
    assert again == datetime(2026, 10, 20, 1, 0, tzinfo=timezone.utc)  # following Mon 22:00 local
    assert next_run("once", after - timedelta(hours=1), None, None, SP, after) is None


# --- API ----------------------------------------------------------------------

@pytest_asyncio.fixture
async def client(admin_headers):
    app = FastAPI()
    for r in (exec_routes.router, script_routes.router, script_routes.schedules_router):
        app.include_router(r)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=admin_headers) as ac:
        yield ac


@pytest_asyncio.fixture
async def world():
    tag = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        cat = (await db.execute(select(HostScriptCategory).where(HostScriptCategory.slug == "diagnostico"))).scalar_one()
        win = Server(name=f"w-{tag}", ip_address="100.127.6.1", remote_user="darckware", os_family="windows", kind="workstation")
        lin = Server(name=f"l-{tag}", ip_address="100.127.6.2", remote_user="darckware", os_family="linux", kind="workstation")
        agent = Agent(name=f"Agente {tag}")
        db.add_all([win, lin, agent])
        await db.commit()
    created: dict[str, list] = {"scripts": [], "executions": [], "schedules": [], "categories": []}
    yield {"tag": tag, "cat": cat, "win": win, "lin": lin, "agent": agent, "created": created}
    for task in list(host_exec_runner._running.values()):
        await asyncio.wait_for(task, timeout=10)
    async with AsyncSessionLocal() as db:
        ids = created["executions"] + created["scripts"] + created["schedules"] + created["categories"]
        if ids:
            await db.execute(delete(AuditEvent).where(AuditEvent.entity_id.in_(ids)))
        if created["schedules"]:
            await db.execute(delete(HostSchedule).where(HostSchedule.id.in_(created["schedules"])))
        exec_ids = list((await db.execute(select(HostExecution.id).where(
            HostExecution.script_id.in_(created["scripts"] or [uuid.uuid4()])))).scalars()) + created["executions"]
        if exec_ids:
            await db.execute(delete(AuditEvent).where(AuditEvent.entity_id.in_(exec_ids)))
            await db.execute(delete(HostExecution).where(HostExecution.id.in_(exec_ids)))
        if created["scripts"]:
            await db.execute(delete(HostScript).where(HostScript.id.in_(created["scripts"])))
        if created["categories"]:
            await db.execute(delete(HostScriptCategory).where(HostScriptCategory.id.in_(created["categories"])))
        await db.execute(delete(Server).where(Server.id.in_([win.id, lin.id])))
        await db.execute(delete(Agent).where(Agent.id == agent.id))
        await db.commit()


async def _wait(execution_id):
    task = host_exec_runner._running.get(uuid.UUID(str(execution_id)))
    if task:
        await asyncio.wait_for(task, timeout=10)


@pytest.mark.asyncio
async def test_library_versions_and_run_with_parameters(client, world):
    w = world
    created = await client.post("/api/v1/host-scripts", json={
        "name": f"Reiniciar serviço {w['tag']}", "category_id": str(w["cat"].id), "description": "Reinicia um serviço",
        "platform": "windows", "risk": "change", "timeout_seconds": 60,
        "parameters": [{"name": "SERVICE", "label": "Serviço", "required": True},
                       {"name": "TOKEN", "secret": True, "default": "tok-abc-123"}],
        "content": "Restart-Service $SERVICE; \"ok $TOKEN\"",
    })
    assert created.status_code == 201, created.text
    script = created.json()
    w["created"]["scripts"].append(uuid.UUID(script["id"]))

    edited = await client.put(f"/api/v1/host-scripts/{script['id']}", json={"content": "Restart-Service $SERVICE -Force; \"ok $TOKEN\"", "note": "força"})
    assert edited.json()["current_version"] == 2
    renamed = await client.put(f"/api/v1/host-scripts/{script['id']}", json={"description": "só descrição"})
    assert renamed.json()["current_version"] == 2  # metadata only: no new version
    detail = (await client.get(f"/api/v1/host-scripts/{script['id']}")).json()
    assert [v["version"] for v in detail["versions"]] == [2, 1]

    seen = {}

    async def fake_bridge(server, shell, body, timeout):
        seen[server.name] = (shell, body, timeout)
        return {"exit_code": 0, "stdout": "ok tok-abc-123", "stderr": "", "duration_ms": 3, "failure": None}

    with patch.object(host_exec_runner, "call_bridge_exec", fake_bridge):
        missing = await client.post("/api/v1/host-executions", json={
            "script_id": script["id"], "server_ids": [str(w["win"].id)]})
        assert missing.status_code == 422  # SERVICE is required
        run = await client.post("/api/v1/host-executions", json={
            "script_id": script["id"], "parameter_values": {"SERVICE": "spooler"},
            "server_ids": [str(w["win"].id), str(w["lin"].id)]})
        assert run.status_code == 201, run.text
        await _wait(run.json()["id"])

    detail = (await client.get(f"/api/v1/host-executions/{run.json()['id']}")).json()
    assert detail["script_name"].startswith("Reiniciar") and detail["script_version"] == 2
    shell, body, timeout = seen[w["win"].name]
    assert shell == "powershell" and body.startswith("$SERVICE = 'spooler'") and timeout == 60
    by_name = {r["server_name"]: r for r in detail["results"]}
    assert by_name[w["lin"].name]["skip_reason"] == "This script is for Windows machines"
    assert "tok-abc-123" not in (by_name[w["win"].name]["stdout"] or "")  # secret parameter masked

    # Library filter by platform.
    windows = (await client.get("/api/v1/host-scripts?platform=windows")).json()
    assert any(s["id"] == script["id"] for s in windows)
    assert not any(s["id"] == script["id"] for s in (await client.get("/api/v1/host-scripts?platform=linux")).json())

    archived = await client.post(f"/api/v1/host-scripts/{script['id']}:archive")
    assert archived.json()["archived"] is True
    blocked = await client.post("/api/v1/host-executions", json={
        "script_id": script["id"], "parameter_values": {"SERVICE": "x"}, "server_ids": [str(w["win"].id)]})
    assert blocked.status_code == 409


@pytest.mark.asyncio
async def test_category_create_and_system_script_protection(client, world):
    w = world
    cat = await client.post("/api/v1/host-scripts/categories", json={"label": f"Backup {w['tag']}"})
    assert cat.status_code == 201
    w["created"]["categories"].append(uuid.UUID(cat.json()["id"]))
    assert (await client.post("/api/v1/host-scripts/categories", json={"label": f"Backup {w['tag']}"})).status_code == 409

    async with AsyncSessionLocal() as db:
        system = HostScript(name=f"Sistema {w['tag']}", category_id=w["cat"].id, platform="windows", content="x",
                            parameters=[], is_system=True, created_by="forgehub", updated_by="forgehub")
        db.add(system)
        await db.commit()
    w["created"]["scripts"].append(system.id)
    assert (await client.put(f"/api/v1/host-scripts/{system.id}", json={"content": "y"})).status_code == 409
    assert (await client.post(f"/api/v1/host-scripts/{system.id}:archive")).status_code == 409


@pytest.mark.asyncio
async def test_schedule_fires_once_with_agent_origin_and_logs_filter(client, world):
    w = world
    async with AsyncSessionLocal() as db:
        script = HostScript(name=f"Uptime {w['tag']}", category_id=w["cat"].id, platform="linux", content="uptime",
                            parameters=[], created_by="t", updated_by="t", timeout_seconds=30)
        db.add(script)
        await db.commit()
    w["created"]["scripts"].append(script.id)

    past = await client.post("/api/v1/host-schedules", json={
        "name": "passado", "script_id": str(script.id), "server_ids": [str(w["lin"].id)], "kind": "once",
        "run_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()})
    assert past.status_code == 422

    sched = await client.post("/api/v1/host-schedules", json={
        "name": f"Toda segunda {w['tag']}", "script_id": str(script.id), "server_ids": [str(w["lin"].id)],
        "kind": "weekly", "weekdays": [1], "time_of_day": "22:00", "timezone": SP, "window_minutes": 30})
    assert sched.status_code == 201, sched.text
    body = sched.json()
    w["created"]["schedules"].append(uuid.UUID(body["id"]))
    assert body["next_run_at"] is not None

    # Make it due now and owned by an agent, then run the scheduler pass.
    async with AsyncSessionLocal() as db:
        row = await db.get(HostSchedule, uuid.UUID(body["id"]))
        row.next_run_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        row.agent_id = w["agent"].id
        await db.commit()

    async def fake_bridge(server, shell, body_, timeout):
        return {"exit_code": 0, "stdout": "up", "stderr": "", "duration_ms": 2, "failure": None}

    with patch.object(host_exec_runner, "call_bridge_exec", fake_bridge):
        fired = await script_routes.run_due_schedules()
        assert fired >= 1
        async with AsyncSessionLocal() as db:
            row = await db.get(HostSchedule, uuid.UUID(body["id"]))
            execution_id = row.last_execution_id
            assert row.next_run_at > datetime.now(timezone.utc)  # moved to next Monday
        await _wait(execution_id)
        # A second pass right away fires nothing for this schedule.
        async with AsyncSessionLocal() as db:
            before = row.last_execution_id
        await script_routes.run_due_schedules()
        async with AsyncSessionLocal() as db:
            assert (await db.get(HostSchedule, uuid.UUID(body["id"]))).last_execution_id == before

    logs = (await client.get(f"/api/v1/host-executions?agent_id={w['agent'].id}")).json()
    assert [e["id"] for e in logs] == [str(execution_id)]
    assert logs[0]["trigger"] == "schedule" and logs[0]["agent_name"] == w["agent"].name
    assert logs[0]["retry_until"] is not None and logs[0]["verdict"] == "succeeded"


@pytest.mark.asyncio
async def test_scheduled_run_retries_unreachable_then_not_run(world, monkeypatch):
    w = world
    monkeypatch.setattr(host_exec_runner, "RETRY_INTERVAL_SECONDS", 0.05)
    calls = []

    async def offline(server, shell, body, timeout):
        calls.append(1)
        return {"failure": "connection", "stderr": "No route to host"}

    async with AsyncSessionLocal() as db:
        servers = [await db.get(Server, w["lin"].id)]
        with patch.object(host_exec_runner, "call_bridge_exec", offline):
            execution = await exec_routes.launch_execution(
                db, servers=servers, command="uptime", shell="sh", timeout_seconds=10, actor="t",
                target_summary="t", trigger="schedule",
                retry_until=datetime.now(timezone.utc) + timedelta(seconds=0.3))
            w["created"]["executions"].append(execution.id)
            await _wait(execution.id)
    async with AsyncSessionLocal() as db:
        detail = await exec_routes._detail(db, await db.get(HostExecution, execution.id))
    assert len(calls) > 1
    result = detail.results[0]
    assert result.status == "skipped" and result.skip_reason == "Unreachable until the scheduled window closed"

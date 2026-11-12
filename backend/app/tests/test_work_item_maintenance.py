"""Remote maintenance <-> Darckware ticket (remote-access support plan, Fase 3).

Darckware is an in-memory `httpx.MockTransport` (same pattern as
test_client_ops.py); ForgeHub's rows (servers, tasks, executions, audit) are
real and removed by the ids this test created.
"""
import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from app.api.routes import host_execution as host_routes
from app.core import darckware_client, host_exec_runner
from app.core import work_item_maintenance as wim
from app.core.config import settings
from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent
from app.db.models.host_execution import HostExecution, HostExecutionResult
from app.db.models.maintenance_proposal import MaintenanceProposal
from app.db.models.server import Server
from app.main import app

AGENT_PATH = "/api/internal/agent"


class FakeDarckware:
    def __init__(self, ticket_id: str, client_id: str) -> None:
        self.calls: list[tuple[str, str, dict | None]] = []
        self.fail_patch = False
        self.refuse_entry = False
        self.ticket = {
            "id": ticket_id, "client_account_id": client_id, "company_name": "ACME", "title": "PC lento",
            "type": "manutencao", "status": "em_andamento", "comments": [], "time_entries": [],
        }

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        path = request.url.path
        self.calls.append((request.method, path, body))
        tid = self.ticket["id"]
        if path == f"{AGENT_PATH}/tickets/{tid}" and request.method == "GET":
            return httpx.Response(200, json=self.ticket)
        if path == f"{AGENT_PATH}/tickets/{tid}" and request.method == "PATCH":
            if self.fail_patch:
                return httpx.Response(500, text="boom")
            self.ticket = {**self.ticket, "status": body["status"]}
            return httpx.Response(200, json=self.ticket)
        if path == f"{AGENT_PATH}/tickets/{tid}/time-entries" and request.method == "POST":
            if self.refuse_entry:
                return httpx.Response(422, json={"detail": "Contrato suspenso"})
            return httpx.Response(201, json=self.ticket)
        return httpx.Response(404, json={"detail": f"unmocked {request.method} {path}"})

    def writes(self) -> list[tuple[str, str, dict | None]]:
        return [c for c in self.calls if c[0] in ("POST", "PATCH", "PUT", "DELETE")]


@pytest_asyncio.fixture
async def world():
    """A client machine, an agent, a finished "Pedir ao agente" task for a
    ticket with two runs (10 + 25 min), a still-running task and a person's run."""
    tag = uuid.uuid4().hex[:8]
    ticket_id, client_id = str(uuid.uuid4()), str(uuid.uuid4())
    now = datetime.now(timezone.utc).replace(microsecond=0)
    async with AsyncSessionLocal() as db:
        server = Server(name=f"pc-{tag}", ip_address="192.0.2.77", remote_user="darckware", os_family="linux",
                        kind="workstation", darckware_client_id=uuid.UUID(client_id), darckware_client_name="ACME")
        agent = Agent(name=f"wim-agent-{tag}", agent_type="executor")
        db.add_all([server, agent])
        await db.flush()
        done = AgentDemand(from_agent="t", subject=f"wim done {tag}", body="x", origin_type="task",
                           target_agent_id=agent.id, from_agent_id=agent.id, dispatch_status="completed")
        running = AgentDemand(from_agent="t", subject=f"wim run {tag}", body="x", origin_type="task",
                              target_agent_id=agent.id, from_agent_id=agent.id, dispatch_status="running")
        plain = AgentDemand(from_agent="t", subject=f"wim plain {tag}", body="x", origin_type="task",
                            target_agent_id=agent.id, from_agent_id=agent.id, dispatch_status="running")
        db.add_all([done, running, plain])
        await db.flush()
        for task in (done, running):
            db.add(AuditEvent(entity_type=wim.REQUEST_EVENT, entity_id=task.id, event_type="created", actor="t",
                              payload={"server_ids": [str(server.id)], "script_ids": [],
                                       "darckware_item_kind": "ticket", "darckware_item_id": ticket_id}))
        executions = []
        for minutes, demand, trig in ((10, done, "agent"), (25, done, "agent"), (5, None, "manual")):
            start = now - timedelta(hours=2) + timedelta(minutes=len(executions) * 40)
            e = HostExecution(shell="sh", command="systemctl restart cups\nsecond line", timeout_seconds=60,
                              status="completed", requested_by=agent.name if demand else "marcelo",
                              started_at=start, finished_at=start + timedelta(minutes=minutes), trigger=trig,
                              agent_id=agent.id if demand else None, agent_demand_id=demand.id if demand else None,
                              script_name="Reiniciar spooler" if len(executions) == 0 else None,
                              darckware_item_kind="ticket", darckware_item_id=ticket_id, reason="lento")
            db.add(e)
            await db.flush()
            db.add(HostExecutionResult(execution_id=e.id, server_id=server.id, server_name=server.name,
                                       status="succeeded" if len(executions) != 1 else "failed",
                                       started_at=start, finished_at=start + timedelta(minutes=minutes)))
            executions.append(e.id)
        skipped = HostExecution(shell="sh", command="true", timeout_seconds=60, status="completed",
                                requested_by=agent.name, started_at=now - timedelta(minutes=30),
                                finished_at=now - timedelta(minutes=30), trigger="agent", agent_id=agent.id,
                                agent_demand_id=done.id, darckware_item_kind="ticket", darckware_item_id=ticket_id)
        db.add(skipped)
        await db.flush()
        db.add(HostExecutionResult(execution_id=skipped.id, server_id=server.id, server_name=server.name,
                                   status="skipped", skip_reason="Already running another command"))
        executions.append(skipped.id)
        await db.commit()
        ids = SimpleNamespace(tag=tag, ticket=ticket_id, client=client_id, server=server.id, agent=agent.id,
                              done=done.id, done_number=done.number, running=running.id, plain=plain.id,
                              executions=executions, extra_executions=[], extra_demands=[], proposals=[])
    yield ids
    async with AsyncSessionLocal() as db:
        all_exec = ids.executions + ids.extra_executions
        await db.execute(delete(AuditEvent).where(AuditEvent.entity_id.in_(
            [uuid.UUID(ids.ticket), ids.done, ids.running, ids.plain, *all_exec, *ids.extra_demands, *ids.proposals])))
        await db.execute(delete(MaintenanceProposal).where(MaintenanceProposal.id.in_(ids.proposals)))
        await db.execute(delete(HostExecution).where(HostExecution.id.in_(all_exec)))
        await db.execute(delete(AgentDemand).where(AgentDemand.id.in_([ids.done, ids.running, ids.plain, *ids.extra_demands])))
        await db.execute(delete(Agent).where(Agent.id == ids.agent))
        await db.execute(delete(Server).where(Server.id == ids.server))
        await db.commit()


@pytest.fixture
def darckware(monkeypatch, world):
    fake = FakeDarckware(world.ticket, world.client)
    monkeypatch.setattr(darckware_client, "transport", httpx.MockTransport(fake.handler))
    monkeypatch.setattr(settings, "DARCKWARE_API_URL", "http://darckware.test")
    monkeypatch.setattr(settings, "DARCKWARE_AGENT_TOKEN", "agent-token")
    monkeypatch.setattr(settings, "DARCKWARE_APPROVER_TOKEN", "approver-token")
    return fake


@pytest_asyncio.fixture
async def client(admin_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=admin_headers) as ac:
        yield ac


def _base(world) -> str:
    return f"/api/v1/client-ops/work-items/ticket/{world.ticket}/maintenance"


async def _item_audits(world, event_type: str | None = None) -> list[AuditEvent]:
    async with AsyncSessionLocal() as db:
        q = select(AuditEvent).where(AuditEvent.entity_id == uuid.UUID(world.ticket))
        if event_type:
            q = q.where(AuditEvent.event_type == event_type)
        return list((await db.scalars(q)).all())


@pytest.mark.asyncio
async def test_proposal_lists_runs_and_writes_nothing(client, darckware, world):
    r = await client.get(_base(world))
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["executions"]) == 4
    manual = next(e for e in data["executions"] if e["trigger"] == "manual")
    assert manual["agent_demand_id"] is None and manual["requested_by"] == "marcelo"
    by_id = {t["demand_id"]: t for t in data["tasks"]}
    assert set(by_id) == {str(world.done), str(world.running)}  # the manual run is no task
    done = by_id[str(world.done)]
    # The skipped-only run isn't counted.
    assert done["finished"] is True and done["recorded"] is None and len(done["execution_ids"]) == 2
    # 10 + 25 = 35 min (no overlap) -> rounded up to 60.
    assert done["proposal"]["minutes"] == 60 and done["proposal"]["execution_count"] == 2
    assert done["client_ids"] == [world.client] and done["uncertain"] is None
    note = done["proposal"]["note"]
    # Client-facing: machines, plain description, outcome -- nothing internal.
    assert f"pc-{world.tag}" in note and 'Rotina de manutenção "Reiniciar spooler"' in note and "Comando de suporte" in note
    assert "concluída com sucesso" in note and "não concluída" in note
    for internal in (str(world.done_number), f"wim-agent-{world.tag}", "systemctl", "tarefa", str(world.done), world.ticket):
        assert internal not in note
    assert by_id[str(world.running)]["proposal"] is None  # not finished
    # Proposing wrote nothing: no Darckware call at all, no audit on the item.
    assert darckware.calls == []
    assert await _item_audits(world) == []


def test_overlapping_runs_count_once():
    t0 = datetime(2026, 11, 12, 10, tzinfo=timezone.utc)
    m = lambda n: t0 + timedelta(minutes=n)  # noqa: E731
    assert wim.union_seconds([(m(0), m(20)), (m(10), m(30)), (m(40), m(50))]) == 40 * 60
    assert wim.union_seconds([(m(0), m(60)), (m(5), m(10))]) == 60 * 60
    assert wim.union_seconds([]) == 0


def test_minutes_round_up_to_half_hours_with_a_minimum():
    assert wim.proposed_minutes(0) == 30
    assert wim.proposed_minutes(60) == 30
    assert wim.proposed_minutes(30 * 60 + 1) == 60
    assert wim.proposed_minutes(10 ** 9) == 24 * 60


@pytest.mark.asyncio
async def test_log_time_records_once_per_task(client, darckware, world):
    url = f"{_base(world)}/{world.done}:record"
    body = {"mode": "log_time", "note": "Spooler reiniciado nas máquinas", "minutes": 45}
    r = await client.post(url, json=body)
    assert r.status_code == 200, r.text
    entries = [c for c in darckware.writes() if c[1].endswith("/time-entries")]
    assert len(entries) == 1
    sent = entries[0][2]
    assert sent["minutes"] == 45 and sent["description"] == body["note"]
    assert sent["recorded_by"].startswith("forgehub:test-admin-") and sent["end_time"]
    assert not any(c[0] == "PATCH" for c in darckware.calls)  # log_time never changes the status

    again = await client.post(url, json=body)
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "MAINTENANCE_ALREADY_RECORDED"
    assert len([c for c in darckware.writes() if c[1].endswith("/time-entries")]) == 1

    marks = await _item_audits(world, wim.RECORDED_EVENT)
    assert len(marks) == 1 and marks[0].payload["agent_demand_id"] == str(world.done)
    assert marks[0].payload["minutes"] == 45 and marks[0].payload["proposed_minutes"] == 60
    view = (await client.get(_base(world))).json()
    done = next(t for t in view["tasks"] if t["demand_id"] == str(world.done))
    assert done["recorded"]["minutes"] == 45 and done["proposal"] is None


@pytest.mark.asyncio
async def test_resolve_logs_the_time_once_and_then_refuses(client, darckware, world):
    url = f"{_base(world)}/{world.done}:record"
    body = {"mode": "resolve", "note": "Spooler reiniciado", "minutes": 60}
    r = await client.post(url, json=body)
    assert r.status_code == 200, r.text
    writes = [(m, p) for m, p, _ in darckware.writes()]
    assert writes == [
        ("POST", f"{AGENT_PATH}/tickets/{world.ticket}/time-entries"),
        ("PATCH", f"{AGENT_PATH}/tickets/{world.ticket}"),
    ]  # exactly one time entry: resolve logs it, nothing else does
    assert darckware.ticket["status"] == "resolvido"
    assert len(await _item_audits(world, "resolve")) == 1
    assert len(await _item_audits(world, wim.RECORDED_EVENT)) == 1
    again = await client.post(url, json={**body, "mode": "log_time"})
    assert again.status_code == 409 and again.json()["detail"]["code"] == "MAINTENANCE_ALREADY_RECORDED"
    assert len(darckware.writes()) == 2


@pytest.mark.asyncio
async def test_record_refuses_unfinished_unrelated_and_failed_darckware(client, darckware, world):
    body = {"mode": "log_time", "note": "x", "minutes": 30}
    r = await client.post(f"{_base(world)}/{world.running}:record", json=body)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "MAINTENANCE_TASK_NOT_FINISHED"
    r = await client.post(f"{_base(world)}/{world.plain}:record", json=body)
    assert r.status_code == 404 and r.json()["detail"]["code"] == "MAINTENANCE_TASK_NOT_FOUND"
    assert darckware.writes() == []
    # Darckware refusing the entry leaves no mark: the operator can try again.
    darckware.ticket["id"] = str(uuid.uuid4())  # every write now 404s
    r = await client.post(f"{_base(world)}/{world.done}:record", json=body)
    assert r.status_code >= 400
    assert await _item_audits(world, wim.RECORDED_EVENT) == []


@pytest.mark.asyncio
async def test_non_admin_is_refused(darckware, world):
    headers = {"Authorization": f"Bearer {create_access_token(f'not-an-admin-{uuid.uuid4().hex}')}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers) as ac:
        assert (await ac.get(_base(world))).status_code in (401, 403)
        r = await ac.post(f"{_base(world)}/{world.done}:record", json={"note": "x", "minutes": 30})
        assert r.status_code in (401, 403)
    assert darckware.calls == []


@pytest.mark.asyncio
async def test_agent_runs_inherit_the_task_item_and_refuse_another(world):
    """launch_execution is the one place every agent path records a run."""
    started = []
    with patch.object(host_exec_runner, "start_execution", lambda *a, **k: started.append(a)):
        async with AsyncSessionLocal() as db:
            server = await db.get(Server, world.server)
            common = dict(servers=[server], command="true", shell="sh", timeout_seconds=5, actor="agent",
                          target_summary="x", trigger="agent", agent_id=world.agent)
            inherited = await host_routes.launch_execution(db, **common, agent_demand_id=world.running)
            world.extra_executions.append(inherited.id)
            assert (inherited.darckware_item_kind, inherited.darckware_item_id) == ("ticket", world.ticket)
            same = await host_routes.launch_execution(db, **common, agent_demand_id=world.running,
                                                      darckware_item=("ticket", world.ticket.upper()))
            world.extra_executions.append(same.id)
            assert same.darckware_item_id == world.ticket
            # A task with no item ("Pedir ao agente" without one, or written by hand) limits nothing.
            free = await host_routes.launch_execution(db, **common, agent_demand_id=world.plain,
                                                      darckware_item=("demand", "D-1"))
            world.extra_executions.append(free.id)
            assert free.darckware_item_id == "D-1"
            before = await db.scalar(select(func.count()).select_from(HostExecution))
            for other in (("ticket", str(uuid.uuid4())), ("demand", world.ticket)):
                with pytest.raises(HTTPException) as exc:
                    await host_routes.launch_execution(db, **common, agent_demand_id=world.running, darckware_item=other)
                assert exc.value.status_code == 422 and exc.value.detail["code"] == "DARCKWARE_ITEM_MISMATCH"
                await db.rollback()
            assert await db.scalar(select(func.count()).select_from(HostExecution)) == before
    assert len(started) == 3


@pytest.mark.asyncio
async def test_approved_proposal_run_task_serves_the_origin_item(world):
    """An approved proposal runs under a new task (open_run_task); its runs
    still belong to the origin task's ticket."""
    async with AsyncSessionLocal() as db:
        run_task = AgentDemand(from_agent="t", subject=f"wim proposal {world.tag}", body="x", origin_type="task",
                               target_agent_id=world.agent, from_agent_id=world.agent, dispatch_status="running")
        db.add(run_task)
        await db.flush()
        world.extra_demands.append(run_task.id)
        proposal = MaintenanceProposal(agent_id=world.agent, agent_demand_id=run_task.id, server_ids=[str(world.server)],
                                       shell="sh", content="true", risk="low", timeout_seconds=30,
                                       requires_elevation=False, parameters=[], reason="r", expected_effect="e",
                                       rollback="b", content_hash="0" * 64, status="approved")
        db.add(proposal)
        await db.flush()
        world.proposals.append(proposal.id)
        db.add(AuditEvent(entity_type="maintenance_proposal", entity_id=proposal.id, event_type="approved",
                          actor="user:x", payload={"origin_demand_id": str(world.running)}))
        await db.commit()
        assert await wim.task_item(db, run_task.id) == ("ticket", world.ticket)
        assert await wim.resolve_task_item(db, run_task.id, None) == ("ticket", world.ticket)


def _entries(darckware) -> list:
    return [c for c in darckware.writes() if c[1].endswith("/time-entries")]


@pytest.mark.asyncio
async def test_failure_after_the_time_entry_is_uncertain_and_never_posts_twice(client, darckware, world):
    """Resolve: the time entry is accepted, then the status change fails. The
    retry must not post a second entry; an admin settles the attempt."""
    url = f"{_base(world)}/{world.done}:record"
    body = {"mode": "resolve", "note": "Feito", "minutes": 60}
    darckware.fail_patch = True
    r = await client.post(url, json=body)
    assert r.status_code == 502
    assert len(_entries(darckware)) == 1
    darckware.fail_patch = False
    for mode in ("resolve", "log_time"):
        again = await client.post(url, json={**body, "mode": mode})
        assert again.status_code == 409 and again.json()["detail"]["code"] == "MAINTENANCE_RECORD_UNCERTAIN"
    assert len(_entries(darckware)) == 1  # no second entry, ever
    view = (await client.get(_base(world))).json()
    task = next(t for t in view["tasks"] if t["demand_id"] == str(world.done))
    assert task["uncertain"]["note"] == "Feito" and task["proposal"] is None and task["recorded"] is None

    # Settling needs a reason; "recorded" closes the task for good.
    assert (await client.post(f"{_base(world)}/{world.done}:settle", json={"outcome": "recorded", "reason": "x"})).status_code == 422
    s = await client.post(f"{_base(world)}/{world.done}:settle",
                          json={"outcome": "recorded", "reason": "Conferi: a entrada de 1 h está no chamado"})
    assert s.status_code == 200, s.text
    task = next(t for t in s.json()["tasks"] if t["demand_id"] == str(world.done))
    assert task["recorded"]["confirmed_by_operator"] is True and task["uncertain"] is None
    final = await client.post(url, json=body)
    assert final.status_code == 409 and final.json()["detail"]["code"] == "MAINTENANCE_ALREADY_RECORDED"
    assert len(_entries(darckware)) == 1
    nothing = await client.post(f"{_base(world)}/{world.done}:settle", json={"outcome": "discard", "reason": "de novo"})
    assert nothing.status_code == 409 and nothing.json()["detail"]["code"] == "MAINTENANCE_NOTHING_UNCERTAIN"


@pytest.mark.asyncio
async def test_discarding_an_uncertain_attempt_allows_a_new_record(client, darckware, world):
    url = f"{_base(world)}/{world.done}:record"
    darckware.fail_patch = True
    assert (await client.post(url, json={"mode": "resolve", "note": "Feito", "minutes": 30})).status_code == 502
    darckware.fail_patch = False
    s = await client.post(f"{_base(world)}/{world.done}:settle",
                          json={"outcome": "discard", "reason": "Entrada não aparece no chamado"})
    assert s.status_code == 200, s.text
    r = await client.post(url, json={"mode": "log_time", "note": "Feito", "minutes": 30})
    assert r.status_code == 200, r.text
    assert len(_entries(darckware)) == 2  # the operator chose to post again
    assert len(await _item_audits(world, wim.DISCARDED_EVENT)) == 1


@pytest.mark.asyncio
async def test_explicit_refusal_before_any_write_leaves_no_attempt_open(client, darckware, world):
    url = f"{_base(world)}/{world.done}:record"
    darckware.refuse_entry = True
    r = await client.post(url, json={"mode": "log_time", "note": "Feito", "minutes": 30})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "darckware_rejected"
    darckware.refuse_entry = False
    discarded = await _item_audits(world, wim.DISCARDED_EVENT)
    assert len(discarded) == 1 and discarded[0].payload["automatic"] is True
    ok = await client.post(url, json={"mode": "log_time", "note": "Feito", "minutes": 30})
    assert ok.status_code == 200, ok.text


@pytest.mark.asyncio
async def test_record_needs_every_run_on_the_item_client_and_every_run_over(client, darckware, world):
    url = f"{_base(world)}/{world.done}:record"
    body = {"mode": "log_time", "note": "x", "minutes": 30}
    async with AsyncSessionLocal() as db:
        server = await db.get(Server, world.server)
        server.darckware_client_id = uuid.uuid4()
        await db.commit()
    r = await client.post(url, json=body)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "MAINTENANCE_CLIENT_MISMATCH"
    async with AsyncSessionLocal() as db:
        server = await db.get(Server, world.server)
        server.darckware_client_id = uuid.UUID(world.client)
        running = HostExecution(shell="sh", command="true", timeout_seconds=60, status="running", requested_by="a",
                                started_at=datetime.now(timezone.utc), trigger="agent", agent_id=world.agent,
                                agent_demand_id=world.done, darckware_item_kind="ticket", darckware_item_id=world.ticket)
        db.add(running)
        await db.flush()
        db.add(HostExecutionResult(execution_id=running.id, server_id=world.server, server_name="pc", status="running"))
        world.extra_executions.append(running.id)
        await db.commit()
    view = (await client.get(_base(world))).json()
    task = next(t for t in view["tasks"] if t["demand_id"] == str(world.done))
    assert task["runs_in_progress"] is True and task["proposal"] is None
    r = await client.post(url, json=body)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "MAINTENANCE_TASK_NOT_FINISHED"
    assert darckware.writes() == []


@pytest.mark.asyncio
async def test_retrying_failed_machines_keeps_the_item(client, world):
    """A person's follow-up on a run's failed machines serves the same ticket."""
    with patch.object(host_exec_runner, "start_execution", lambda *a, **k: None):
        r = await client.post(f"/api/v1/host-executions/{world.executions[1]}:follow-up",
                              json={"command": "true", "shell": "sh"})
    assert r.status_code == 201, r.text
    world.extra_executions.append(uuid.UUID(r.json()["id"]))
    assert (r.json()["darckware_item_kind"], r.json()["darckware_item_id"]) == ("ticket", world.ticket)

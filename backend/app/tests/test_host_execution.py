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
            "command": "uptime # password=s3cret99", "shell": "sh",
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
async def test_failure_then_follow_up_only_on_failed(client, machines):
    rows, created = machines
    ok_id, bad_id = rows["linux"].id, rows["linux2"].id

    async def fake_bridge(server, shell, script, timeout):
        if server.id == bad_id and "fix" not in script:
            return {"exit_code": 2, "stdout": "", "stderr": "disk full", "duration_ms": 5, "failure": "command"}
        return {"exit_code": 0, "stdout": "fine", "stderr": "", "duration_ms": 5, "failure": None}

    with patch.object(host_exec_runner, "call_bridge_exec", fake_bridge):
        first = (await client.post("/api/v1/host-executions", json={
            "command": "apt-get update", "shell": "sh", "server_ids": [str(ok_id), str(bad_id)],
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
            "command": "sleep", "shell": "sh", "server_ids": [str(rows["linux"].id)],
        })).json()
        created.append(uuid.UUID(first["id"]))
        await asyncio.sleep(0.2)

        second = (await client.post("/api/v1/host-executions", json={
            "command": "uptime", "shell": "sh", "server_ids": [str(rows["linux"].id)],
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
            "command": "uptime", "shell": "sh", "server_ids": [str(rows["linux"].id), str(rows["linux2"].id)],
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
        "command": "x", "shell": "sh", "server_ids": [str(uuid.uuid4())],
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

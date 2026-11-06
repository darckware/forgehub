"""T.4a: real SSH execution through the isolated test stub."""
import subprocess
import uuid
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.api.routes import server as server_routes
from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.governance import AuditEvent
from app.db.models.host_execution import HostExecution
from app.db.models.server import Server
from app.tests.test_host_execution import _wait
from app.scripts.seed_test_database import seed, seed_id

@pytest.mark.asyncio
async def test_t4a_agent_linux_execution():
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

    from app.core.config import settings

    try:
        inspected = subprocess.run(
            ["docker", "inspect", "-f", "{{.Config.Hostname}}", "forgehub_test_linux_target"],
            capture_output=True, text=True, timeout=10, check=True,
        )
    except (OSError, subprocess.SubprocessError):
        pytest.skip("Docker or the test Linux target is unavailable")
    hostname = inspected.stdout.strip()
    assert hostname
    async with AsyncSessionLocal() as db:
        target = await db.get(Server, seed_id("servers", "linux-target"))
        outside = await db.get(Server, seed_id("servers", "srv-teste-01"))
    if target is None or outside is None:
        await seed(settings)
        async with AsyncSessionLocal() as db:
            target = await db.get(Server, seed_id("servers", "linux-target"))
            outside = await db.get(Server, seed_id("servers", "srv-teste-01"))
    assert target is not None and outside is not None
    rows = {"linux": target, "linux2": outside}
    original_ip = outside.ip_address
    created = []
    tag = uuid.uuid4().hex[:8]
    token = f"agt_test_{tag}"
    async with AsyncSessionLocal() as db:
        grantor = User(username=f"grantor-{tag}", hashed_password=hash_password("x"), is_admin=True)
        agent = Agent(name=f"maint-agent-{tag}", agent_type="executor")
        category = (await db.execute(select(HostScriptCategory).limit(1))).scalar_one()
        script = HostScript(name=f"diag-{tag}", category_id=category.id, platform="linux", risk="read",
                            timeout_seconds=30, parameters=[], content="hostname; id -un; uname -s; echo token=example_secret_12345", current_version=1,
                            created_by="t", updated_by="t")
        risky = HostScript(name=f"wipe-{tag}", category_id=category.id, platform="linux", risk="change",
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

    body = {"script_id": str(ids.script), "server_ids": [str(rows["linux"].id)], "reason": "Cliente relatou lentidão",
            "message_number": ids.number}
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers) as ac:
            with (
                patch.object(server_routes, "get_readiness", fake_readiness),
            ):
                assert (await ac.post("/api/v1/host-executions/agent", json=body)).status_code == 403  # no delegation
                async with AsyncSessionLocal() as db:
                    now = datetime.now(timezone.utc)
                    db.add(AuthorityDelegation(
                        grantor_user_id=ids.grantor, grantee_type="agent", grantee_id=ids.agent,
                        allowed_actions=["remote_access.execute"], servers=[str(rows["linux"].id), str(rows["linux2"].id)], max_risk="low",
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
                assert not_ready.status_code == 403  # outside the task, regardless of readiness

                resp = await ac.post("/api/v1/host-executions/agent", json={**body, "darckware_item_kind": "ticket", "darckware_item_id": "T-42"})
                assert resp.status_code == 201, resp.text
                execution_id = resp.json()["id"]
                created.append(uuid.UUID(execution_id))
                await _wait(execution_id)
                got = (await ac.get(f"/api/v1/host-executions/agent/{execution_id}")).json()
                assert got["trigger"] == "agent" and got["agent_name"] == f"maint-agent-{tag}"
                assert got["reason"] == "Cliente relatou lentidão" and got["darckware_item_id"] == "T-42"
                assert got["counts"]["succeeded"] == 1 and got["agent_demand_id"] == str(ids.task)
                output_lines = got["results"][0]["stdout"].splitlines()
                assert hostname in output_lines and "darckware" in output_lines and "Linux" in output_lines
                assert "example_secret_12345" not in got["command"]
                assert "example_secret_12345" not in str(got["results"])
                # A separate requested machine is deliberately real-looking; the
                # bridge must refuse it and the persisted result must fail.
                async with AsyncSessionLocal() as db:
                    real = await db.get(Server, rows["linux2"].id)
                    real.ip_address = "10.0.0.5"
                    event = (await db.execute(select(AuditEvent).where(
                        AuditEvent.entity_type == "agent_maintenance_request", AuditEvent.entity_id == ids.task
                    ))).scalar_one()
                    event.payload = {"server_ids": [str(rows["linux"].id), str(real.id)],
                                     "script_ids": [str(ids.script)]}
                    await db.commit()
                ready[rows["linux2"].id] = "ready"
                refused = await ac.post("/api/v1/host-executions/agent", json={
                    **body, "server_ids": [str(rows["linux2"].id)]})
                assert refused.status_code == 201, refused.text
                failed_id = refused.json()["id"]
                created.append(uuid.UUID(failed_id))
                await _wait(failed_id)
                failed = (await ac.get(f"/api/v1/host-executions/agent/{failed_id}")).json()
                assert failed["counts"]["failed"] == 1
                assert "not a fictitious" in str(failed)
                async with AsyncClient(base_url=settings.CHAT_BRIDGE_URL) as stub:
                    log = (await stub.get("/_stub/calls", params={"integration": "host-bridge"})).json()["calls"]
                assert any(c["outcome"] == "executed" and c["destination"] == "linux-target.test" for c in log)
                assert any(c["outcome"] == "refused" and c["destination"] == "10.0.0.5" for c in log)
                assert all(c["destination"] == "linux-target.test" for c in log if c["outcome"] == "executed")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                               headers={"Authorization": f"Bearer {create_access_token(f'grantor-{tag}')}"}) as ac:
            history = (await ac.get(f"/api/v1/servers/{rows['linux'].id}/maintenance")).json()
        entry = next(h for h in history if h["execution_id"] == execution_id)
        assert entry["actor"] == f"maint-agent-{tag}" and entry["reason"] == "Cliente relatou lentidão"
        assert entry["kind"] == "execution" and entry["darckware_item_kind"] == "ticket"
    finally:
        async with AsyncSessionLocal() as db:
            outside_row = await db.get(Server, rows["linux2"].id)
            outside_row.ip_address = original_ip
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

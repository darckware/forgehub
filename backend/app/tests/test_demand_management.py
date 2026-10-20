"""Operator workflows exercise real routes, persistence and per-item conflicts."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.main import app
from app.api.schemas.demand import DemandUpdateIn
from app.api.routes.demand import update_demand
from app.db.models.governance import AuditEvent
from app.db.models.demand import DemandGroup
from sqlalchemy import delete
pytest_plugins = ["app.tests.test_demand_consolidation"]


@pytest.fixture
async def client(admin_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=admin_headers) as client:
        yield client


async def test_restore_clears_expired_schedule_and_requires_new_approval(consolidation_db):
    db, failed, _ = consolidation_db
    failed.status = "archived"
    failed.dispatch_status = None
    failed.agent_run_id = None
    failed.scheduled_at = datetime.now(timezone.utc) - timedelta(days=1)
    await db.commit()
    restored = await update_demand(failed.id, DemandUpdateIn(status="new"), db=db)
    assert restored.scheduled_at is None
    assert restored.requires_approval
    assert restored.approval_status == "pending"


async def test_agent_work_paginates_and_counts_using_the_same_filters(client, consolidation_db):
    db, failed, incubated = consolidation_db
    label = f"unique-work-{uuid.uuid4().hex}"
    failed.subject = label + " failure"
    incubated.subject = label + " incubation"
    await db.commit()
    response = await client.get("/api/v1/demands/agent-work", params={"search": label, "view": "attention", "page_size": 1})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["total"] == 2
    assert len(result["items"]) == 1
    assert result["counts"]["attention"] == 2
    assert result["counts"]["failed"] == 1
    second = (await client.get("/api/v1/demands/agent-work", params={"search": label, "page": 2, "page_size": 1})).json()
    assert second["items"][0]["id"] != result["items"][0]["id"]
    narrowed = (await client.get("/api/v1/demands/agent-work", params={"search": label, "view": "failed"})).json()
    assert narrowed["total"] == 1
    assert narrowed["counts"]["attention"] == 2


async def test_agent_work_exposes_uncertainty_and_blocks_retry_and_delete(client, consolidation_db):
    db, failed, _ = consolidation_db
    await db.commit()
    result = (await client.get("/api/v1/demands/agent-work", params={"search": str(failed.number)})).json()
    item = next(row for row in result["items"] if row["id"] == str(failed.id))
    assert item["work_state"] == "uncertain"
    assert "reconcile" in item["allowed_actions"]
    assert "retry" not in item["allowed_actions"]
    assert "delete" not in item["allowed_actions"]
    assert item["blocked_actions"]["retry"]


async def test_agent_and_date_filters_apply_before_counts(client, consolidation_db):
    db, failed, _ = consolidation_db
    await db.commit()
    response = await client.get("/api/v1/demands/agent-work", params={"agent_id": str(uuid.uuid4())})
    assert response.json()["total"] == 0
    assert not any(response.json()["counts"].values())
    response = await client.get("/api/v1/demands/agent-work", params={"created_from": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()})
    assert response.json()["total"] == 0


async def test_bulk_reports_success_active_and_stale_items_individually(client, consolidation_db):
    db, failed, incubated = consolidation_db
    failed.agent_run_id = None
    failed.dispatch_error = "Known failure"
    incubated.dispatch_status = "running"
    await db.commit()
    await db.refresh(failed)
    await db.refresh(incubated)
    response = await client.post("/api/v1/demands/agent-work/bulk", json={
        "action": "archive", "items": [
            {"id": str(failed.id), "updated_at": failed.updated_at.isoformat()},
            {"id": str(incubated.id), "updated_at": incubated.updated_at.isoformat()},
            {"id": str(uuid.uuid4()), "updated_at": failed.updated_at.isoformat()},
        ],
    })
    assert response.status_code == 200, response.text
    assert [item["status"] for item in response.json()["results"]] == ["success", "blocked", "missing"]
    await db.refresh(failed)
    await db.refresh(incubated)
    assert failed.status == "archived"
    assert incubated.status != "archived"
    response = await client.post("/api/v1/demands/agent-work/bulk", json={"action": "restore", "items": [{"id": str(failed.id), "updated_at": (failed.updated_at - timedelta(days=1)).isoformat()}]})
    assert response.json()["results"][0]["status"] == "stale"


async def test_retry_authorization_requires_evidence_and_does_not_schedule(client, consolidation_db):
    db, failed, _ = consolidation_db
    failed.agent_run_id = None
    failed.dispatch_error = "Known terminal failure"
    failed.working_path = "/tmp"
    await db.commit()
    url = f"/api/v1/demands/{failed.id}/decision"
    response = await client.post(url, json={"action": "authorize_retry", "reason": "Corrected configuration"})
    assert response.status_code == 422
    response = await client.post(url, json={"action": "authorize_retry", "reason": "Corrected configuration", "evidence_ref": "docs/recovery-check.md"})
    assert response.status_code == 200, response.text
    assert response.json()["dispatch_attempts"] == 3
    assert response.json()["retry_limit"] == 6
    assert response.json()["scheduled_at"] is None
    history = (await client.get(f"/api/v1/demands/{failed.id}/history")).json()
    assert any(event["payload"].get("evidence_ref") == "docs/recovery-check.md" for event in history)


async def test_drop_incubation_requires_reason_and_preserves_history(client, consolidation_db):
    db, _, incubated = consolidation_db
    await db.commit()
    url = f"/api/v1/demands/{incubated.id}/decision"
    assert (await client.post(url, json={"action": "drop"})).status_code == 422
    response = await client.post(url, json={"action": "drop", "reason": "Superseded by current work"})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "archived"
    assert response.json()["incubation_state"] == "dropped"
    assert response.json()["drop_reason"] == "Superseded by current work"
    assert await db.scalar(select(AuditEvent.id).where(AuditEvent.entity_id == incubated.id, AuditEvent.event_type == "demand_drop"))


async def test_attempt_history_preserves_the_run_when_retrying(client, consolidation_db):
    from app.api.routes.demand import _fail_dispatch
    db, failed, _ = consolidation_db
    run_id = failed.agent_run_id
    await _fail_dispatch(db, failed, "Dispatch outcome is uncertain; reconcile the known run before retrying.", title="Test failure")
    await db.commit()
    history = (await client.get(f"/api/v1/demands/{failed.id}/history")).json()
    assert any(event["payload"].get("run_id") == run_id and event["payload"].get("lifetime_attempts") == 3 for event in history)


async def test_consolidated_source_content_is_read_only(consolidation_db):
    from fastapi import HTTPException
    db, failed, incubated = consolidation_db
    failed.consolidated_into_id = incubated.id
    failed.status = "archived"
    await db.flush()
    with pytest.raises(HTTPException) as error:
        await update_demand(failed.id, DemandUpdateIn(body="Overwritten evidence"), db=db)
    assert error.value.status_code == 409
    assert failed.body == "Original evidence"


async def test_filing_into_archive_folder_cannot_hide_active_execution(consolidation_db):
    from fastapi import HTTPException
    db, failed, _ = consolidation_db
    failed.dispatch_status = "running"
    group = DemandGroup(name=f"Archive test {uuid.uuid4()}")
    db.add(group)
    await db.flush()
    group_id = group.id
    try:
        with pytest.raises(HTTPException) as error:
            await update_demand(failed.id, DemandUpdateIn(group_id=group_id), db=db)
        assert error.value.status_code == 409
    finally:
        await db.rollback()
        await db.execute(delete(DemandGroup).where(DemandGroup.id == group_id))
        await db.commit()


async def test_restoring_discarded_incubation_starts_a_new_decision_cycle(client, consolidation_db):
    db, _, incubated = consolidation_db
    await db.commit()
    url = f"/api/v1/demands/{incubated.id}/decision"
    assert (await client.post(url, json={"action": "drop", "reason": "Superseded"})).status_code == 200
    response = await client.post(url, json={"action": "restore"})
    assert response.status_code == 200, response.text
    assert response.json()["incubation_state"] == "incubating"
    assert datetime.fromisoformat(response.json()["matures_at"]) > datetime.now(timezone.utc)
    assert response.json()["scheduled_at"] is None


@pytest.mark.parametrize("operation", ["reprocess", "delete"])
async def test_noncanonical_uncertainty_is_blocked_by_direct_api(client, consolidation_db, operation):
    db, failed, _ = consolidation_db
    failed.dispatch_attempts = 1
    failed.dispatch_error = "A previous execution remains uncertain; investigation is pending"
    await db.commit()
    url = f"/api/v1/demands/{failed.id}"
    response = await (client.delete(url) if operation == "delete" else client.post(url + ":reprocess"))
    assert response.status_code == 409


async def test_retry_preserves_previous_run_evidence_in_audit(client, consolidation_db):
    db, failed, _ = consolidation_db
    failed.dispatch_attempts = 1
    failed.dispatch_error = "The agent run ended as 'failed'."
    run_id, error = failed.agent_run_id, failed.dispatch_error
    await db.commit()
    response = await client.post(f"/api/v1/demands/{failed.id}:reprocess")
    assert response.status_code == 200, response.text
    events = (await client.get(f"/api/v1/demands/{failed.id}/history")).json()
    assert any(event["action"] == "demand_reprocess" and event["payload"]["run_id"] == run_id and event["payload"]["error"] == error for event in events)


async def test_archive_check_is_serialized_with_dispatch_reservation(consolidation_db, test_suite_agent, monkeypatch):
    import asyncio
    from app.api.routes import demand as routes
    from app.core.demand_dispatch_guard import reserve_dispatch
    from app.db.base import AsyncSessionLocal
    from fastapi import HTTPException
    db, failed, _ = consolidation_db
    failed.agent_run_id = None
    failed.dispatch_status = None
    failed.dispatch_error = None
    failed.dispatch_attempts = 0
    failed.working_path = "/tmp"
    await db.commit()
    demand_id = failed.id
    fetched, release = asyncio.Event(), asyncio.Event()
    original = routes._get_demand_or_404

    async def paused_lookup(session, item_id, **kwargs):
        row = await original(session, item_id, **kwargs)
        if session is db:
            fetched.set()
            await release.wait()
        return row

    monkeypatch.setattr(routes, "_get_demand_or_404", paused_lookup)
    async def reserve():
        async with AsyncSessionLocal() as other:
            row = await other.get(type(failed), demand_id)
            return await reserve_dispatch(other, row, test_suite_agent, None)
    archive = asyncio.create_task(routes.update_demand(demand_id, DemandUpdateIn(status="archived"), db=db))
    await asyncio.wait_for(fetched.wait(), 5)
    reservation = asyncio.create_task(reserve())
    try:
        await asyncio.sleep(0.05)
        release.set()
        await archive
        with pytest.raises(HTTPException):
            await asyncio.wait_for(reservation, 5)
    finally:
        release.set()
        await asyncio.gather(archive, reservation, return_exceptions=True)


async def test_investigation_preserves_uncertainty_until_explicit_inactive_confirmation(client, consolidation_db):
    db, failed, _ = consolidation_db
    await db.commit()
    run_id = failed.agent_run_id
    url = f"/api/v1/demands/{failed.id}/decision"
    evidence = {"reason": "Inspected runner and process inventory", "evidence_ref": "docs/inactive-run-evidence.md"}
    recorded = await client.post(url, json={"action": "record_investigation", **evidence})
    assert recorded.status_code == 200, recorded.text
    assert recorded.json()["agent_run_id"] == run_id
    assert "uncertain" in recorded.json()["dispatch_error"].lower()
    denied = await client.post(url, json={"action": "confirm_inactive", "confirmation": "wrong-run", **evidence})
    assert denied.status_code == 409
    confirmed = await client.post(url, json={"action": "confirm_inactive", "confirmation": run_id, **evidence})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["agent_run_id"] == run_id
    assert confirmed.json()["scheduled_at"] is None
    assert confirmed.json()["dispatch_status"] == "failed"
    assert confirmed.json()["requires_approval"] is True
    history = (await client.get(f"/api/v1/demands/{failed.id}/history")).json()
    assert any(row["action"] == "demand_confirm_inactive" and row["payload"]["previous_run_id"] == run_id for row in history)

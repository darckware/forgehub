"""Tests for the Governance domain (approvals, audit_events, policies).

Covers: create + get + list for the primary entity (Approval), plus a
business-rule violation case (deciding an already-decided approval is
rejected with 409). Also smoke-tests Policy and AuditEvent create/list.

DB strategy: this domain's tables (approvals, audit_events, policies) are
created and owned by the project's Alembic migration -- this module no
longer creates or drops them itself. (It previously did both via
`Base.metadata.create_all`/`drop_all` against this module's own table
subset, written before the unified migration existed; `drop_all` on a
table subset turned out to also attempt `DROP TYPE` for unrelated
Postgres enum types shared via the same `Base.metadata` -- e.g. the
Artifact domain's `artifact_type_enum` -- which fails with
`DependentObjectsStillExistError` since `company.artifacts` still uses
that type, and worse, it was dropping real migration-managed tables out
from under the running app between test sessions.) Each test now cleans
up only the specific rows it creates via the real DELETE endpoints.
"""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db.models.governance import Approval, AuditEvent, Policy  # noqa: F401

# All async tests/fixtures in this module share one event loop so that the
# module-scoped DB engine (created at import time in app.db.base) is used
# consistently — asyncpg connections are bound to the loop that created
# them and cannot hop loops.


_governance_router_mounted = False


@pytest_asyncio.fixture
async def client(auth_headers):
    global _governance_router_mounted

    from app.main import app

    from app.api.routes import governance

    # main.py's central wiring step adds this router in normal operation;
    # until that step runs, mount it directly on the shared app instance
    # here so this domain's tests are runnable standalone. Guarded by a
    # module-level flag so re-importing app.main across tests in this
    # session doesn't double-mount the router.
    if not _governance_router_mounted:
        app.include_router(governance.router)
        _governance_router_mounted = True

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=auth_headers) as ac:
        yield ac


async def test_create_policy(client: AsyncClient):
    name = f"policy-{uuid.uuid4().hex[:8]}"
    resp = await client.post(
        "/api/v1/governance/policies",
        json={
            "name": name,
            "description": "Critical skills require approval",
            "policy_type": "approval_required",
            "rules": {"applies_to": "skill", "min_risk_level": "critical"},
            "is_active": True,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == name
    assert body["is_active"] is True
    assert "id" in body

    # cleanup
    del_resp = await client.delete(f"/api/v1/governance/policies/{body['id']}")
    assert del_resp.status_code == 204


async def test_create_duplicate_policy_name_rejected(client: AsyncClient):
    name = f"policy-{uuid.uuid4().hex[:8]}"
    payload = {
        "name": name,
        "policy_type": "approval_required",
    }
    first = await client.post("/api/v1/governance/policies", json=payload)
    assert first.status_code == 201, first.text

    second = await client.post("/api/v1/governance/policies", json=payload)
    assert second.status_code == 400

    await client.delete(f"/api/v1/governance/policies/{first.json()['id']}")


async def test_create_get_list_approval(client: AsyncClient):
    target_id = uuid.uuid4()
    create_resp = await client.post(
        "/api/v1/governance/approvals",
        json={
            "entity_type": "pipeline_stage_gate",
            "entity_id": str(target_id),
            "approval_type": "gate_approval",
            "requested_by": "marcelo",
            "comments": "Please review the gate before release.",
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    assert created["status"] == "pending"
    assert created["entity_type"] == "pipeline_stage_gate"
    approval_id = created["id"]

    get_resp = await client.get(f"/api/v1/governance/approvals/{approval_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == approval_id

    list_resp = await client.get(
        "/api/v1/governance/approvals", params={"entity_id": str(target_id)}
    )
    assert list_resp.status_code == 200
    listed = list_resp.json()
    assert any(a["id"] == approval_id for a in listed)

    # Audit event should have been recorded for the request.
    audit_resp = await client.get(
        "/api/v1/governance/audit-events",
        params={"entity_type": "approval", "entity_id": approval_id},
    )
    assert audit_resp.status_code == 200
    audit_events = audit_resp.json()
    assert any(e["event_type"] == "approval_requested" for e in audit_events)


async def test_approval_cannot_be_decided_twice(client: AsyncClient):
    """Business rule: a decided approval is final; redeciding is a 4xx."""
    create_resp = await client.post(
        "/api/v1/governance/approvals",
        json={
            "entity_type": "release",
            "entity_id": str(uuid.uuid4()),
            "approval_type": "release_approval",
            "requested_by": "marcelo",
        },
    )
    assert create_resp.status_code == 201
    approval_id = create_resp.json()["id"]

    first_decision = await client.post(
        f"/api/v1/governance/approvals/{approval_id}/approve",
        json={"decided_by": "lead", "comments": "Looks good"},
    )
    assert first_decision.status_code == 200, first_decision.text
    assert first_decision.json()["status"] == "approved"

    second_decision = await client.post(
        f"/api/v1/governance/approvals/{approval_id}/approve",
        json={"decided_by": "lead", "comments": "Trying again"},
    )
    assert second_decision.status_code == 409

    second_reject = await client.post(
        f"/api/v1/governance/approvals/{approval_id}/reject",
        json={"decided_by": "lead"},
    )
    assert second_reject.status_code == 409


async def test_approval_unknown_policy_id_rejected(client: AsyncClient):
    resp = await client.post(
        "/api/v1/governance/approvals",
        json={
            "entity_type": "skill",
            "entity_id": str(uuid.uuid4()),
            "approval_type": "skill_approval",
            "requested_by": "marcelo",
            "policy_id": str(uuid.uuid4()),
        },
    )
    assert resp.status_code == 400


async def test_create_and_list_audit_event(client: AsyncClient):
    entity_id = uuid.uuid4()
    create_resp = await client.post(
        "/api/v1/governance/audit-events",
        json={
            "entity_type": "project_task",
            "entity_id": str(entity_id),
            "event_type": "task_completed",
            "actor": "agent-7",
            "payload": {"outcome": "success"},
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    body = create_resp.json()
    assert body["event_type"] == "task_completed"

    get_resp = await client.get(f"/api/v1/governance/audit-events/{body['id']}")
    assert get_resp.status_code == 200

    list_resp = await client.get(
        "/api/v1/governance/audit-events", params={"entity_id": str(entity_id)}
    )
    assert list_resp.status_code == 200
    assert any(e["id"] == body["id"] for e in list_resp.json())

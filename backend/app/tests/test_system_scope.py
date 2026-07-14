"""Integration coverage for the Planning conception-to-scope gate."""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.db.base import AsyncSessionLocal
from app.db.models.governance import AuditEvent
from app.db.models.governance import ApprovalDecisionRecord, ApprovalRequest, PolicyEvaluation
from app.db.models.notification import Notification
from app.db.models.product import Product
from app.db.models.user import User
from app.core.security import create_access_token, hash_password
from app.main import app


@pytest_asyncio.fixture
async def governed_users():
    suffix = uuid.uuid4().hex
    async with AsyncSessionLocal() as db:
        requester = User(username=f"planning-requester-{suffix}", hashed_password=hash_password("test"), is_admin=True)
        approver = User(username=f"planning-approver-{suffix}", hashed_password=hash_password("test"), is_admin=True)
        db.add_all([requester, approver])
        await db.commit()
        await db.refresh(requester); await db.refresh(approver)
        data = {
            "requester_id": requester.id, "approver_id": approver.id,
            "requester_headers": {"Authorization": f"Bearer {create_access_token(requester.username)}"},
            "approver_headers": {"Authorization": f"Bearer {create_access_token(approver.username)}"},
        }
    yield data
    async with AsyncSessionLocal() as db:
        await db.execute(delete(User).where(User.id.in_([data["requester_id"], data["approver_id"]])))
        await db.commit()


@pytest_asyncio.fixture
async def client(governed_users):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=governed_users["requester_headers"]
    ) as value:
        yield value


async def _cleanup(product_id: uuid.UUID, concept_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as db:
        request_ids = list((await db.execute(select(ApprovalRequest.id).where(
            ApprovalRequest.target_id == concept_id
        ))).scalars())
        evaluation_ids = list((await db.execute(select(ApprovalRequest.policy_evaluation_id).where(
            ApprovalRequest.target_id == concept_id
        ))).scalars())
        if request_ids:
            await db.execute(delete(ApprovalDecisionRecord).where(ApprovalDecisionRecord.approval_request_id.in_(request_ids)))
            await db.execute(delete(AuditEvent).where(AuditEvent.entity_type == "approval_request", AuditEvent.entity_id.in_(request_ids)))
            await db.execute(delete(Notification).where(Notification.event_key.in_([f"approval:requested:{value}" for value in request_ids] + [f"approval:decision:{value}" for value in request_ids])))
            await db.execute(delete(ApprovalRequest).where(ApprovalRequest.id.in_(request_ids)))
        if evaluation_ids:
            await db.execute(delete(PolicyEvaluation).where(PolicyEvaluation.id.in_(evaluation_ids)))
        await db.execute(delete(AuditEvent).where(
            AuditEvent.entity_type == "product_concept", AuditEvent.entity_id == concept_id
        ))
        product = await db.get(Product, product_id)
        if product:
            await db.delete(product)
        await db.commit()


@pytest.mark.asyncio
async def test_idea_system_map_approval_and_project_scope(client: AsyncClient, governed_users):
    name = f"Planning Product {uuid.uuid4()}"
    created = await client.post("/api/v1/conception/ideas", json={
        "name": name,
        "problem_statement": "Daily engineering decisions are not traceable end to end.",
        "vision": "A deterministic engineering control plane.",
        "scope_summary": "Conception, system map and project scope.",
        "requested_by": "test-operator",
    })
    assert created.status_code == 201, created.text
    body = created.json()
    product_id = uuid.UUID(body["product_id"])
    concept_id = uuid.UUID(body["concept"]["id"])
    revision_id = body["blueprint_revision"]["id"]

    try:
        assert body["concept"]["status"] == "draft"
        assert body["blueprint_revision"]["status"] == "draft"

        empty_submit = await client.post(f"/api/v1/product-concepts/{concept_id}:submit")
        assert empty_submit.status_code == 422

        element = await client.post(f"/api/v1/blueprint-revisions/{revision_id}/elements", json={
            "stable_key": "screen.daily-cockpit",
            "family": "experience",
            "element_type": "screen",
            "name": "Daily Engineering Cockpit",
            "spec_snapshot": {"route": "/planning/daily"},
        })
        assert element.status_code == 201, element.text
        element_id = element.json()["element"]["id"]

        validation = await client.post(f"/api/v1/blueprint-revisions/{revision_id}:validate")
        assert validation.status_code == 200
        assert validation.json()["valid"] is True

        submitted = await client.post(f"/api/v1/product-concepts/{concept_id}:submit")
        assert submitted.status_code == 200, submitted.text
        assert submitted.json()["concept"]["status"] == "in_review"

        direct = await client.post(f"/api/v1/product-concepts/{concept_id}:decide", json={
            "decision": "approved", "decided_by": "spoofed-approver"
        })
        assert direct.status_code == 409
        pending = await client.get("/api/v1/governed/approval-requests", params={"status_filter": "pending"})
        assert pending.status_code == 200, pending.text
        request_id = next(row["id"] for row in pending.json() if row["target_id"] == str(concept_id))
        self_decision = await client.post(f"/api/v1/governed/approval-requests/{request_id}:decide", json={
            "decision": "approved", "idempotency_key": f"self-{uuid.uuid4()}"
        })
        assert self_decision.status_code == 403
        decision_key = f"approve-{uuid.uuid4()}"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=governed_users["approver_headers"]) as approver:
            approved = await approver.post(f"/api/v1/governed/approval-requests/{request_id}:decide", json={
                "decision": "approved", "idempotency_key": decision_key
            })
            repeated_decision = await approver.post(f"/api/v1/governed/approval-requests/{request_id}:decide", json={
                "decision": "approved", "idempotency_key": decision_key
            })
        assert approved.status_code == 200, approved.text
        assert repeated_decision.status_code == 200
        assert repeated_decision.json()["id"] == approved.json()["id"]
        assert approved.json()["decided_by_id"] == str(governed_users["approver_id"])

        authorization = await client.post(
            f"/api/v1/product-concepts/{concept_id}:authorize-delivery-planning",
            json={"version": "0.1.0", "project_name": f"Project {name}", "owner": "test-operator"},
        )
        assert authorization.status_code == 200, authorization.text
        project_id = authorization.json()["project_id"]
        scope_id = authorization.json()["project_scope_id"]

        repeated = await client.post(
            f"/api/v1/product-concepts/{concept_id}:authorize-delivery-planning",
            json={"version": "0.1.0", "project_name": f"Project {name}", "owner": "test-operator"},
        )
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()["project_id"] == project_id
        assert repeated.json()["project_scope_id"] == scope_id

        scopes = await client.get(f"/api/v1/projects/{project_id}/scopes")
        assert scopes.status_code == 200
        assert scopes.json()[0]["blueprint_base_revision_id"] == revision_id

        item = await client.post(f"/api/v1/project-scopes/{scope_id}/items", json={
            "system_element_id": element_id,
            "change_type": "add",
            "applicability": "required",
            "acceptance_criteria": [{"criterion": "The cockpit displays the current engineering phase."}],
        })
        assert item.status_code == 201, item.text
        assert item.json()["acceptance_criteria"][0]["criterion"].startswith("The cockpit")
    finally:
        await _cleanup(product_id, concept_id)

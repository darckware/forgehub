"""Batch authorization is atomic; each approved item has its own claim identity."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from app.api.routes import moodle_approval
from app.api.schemas.moodle_approval import StatusIn
from app.core.deps import ActorPrincipal
from app.core.demand_workflow import approval_fingerprint
from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent
from app.db.models.moodle_approval import MoodleApproval
from app.db.models.user import User
from app.tests.test_moodle_telegram_decision import client, request_row  # noqa: F401


async def test_batch_rejects_stale_item_atomically_then_approves_each_exact_request(client, request_row):  # noqa: F811 -- imported pytest fixtures are injected by name
    second_id, request_id = uuid.uuid4(), uuid.uuid4()
    async with AsyncSessionLocal() as db:
        user = await db.get(User, request_row["owner_id"])
        headers = {"Authorization": f"Bearer {create_access_token(user.username)}"}
        original = await db.get(AgentDemand, request_row["message_id"])
        db.add(AgentDemand(id=second_id, from_agent="test-maia", from_agent_id=request_row["agent_id"],
            target_agent_id=request_row["agent_id"], subject="Second batch item", body="Pending", origin_type="task",
            status="new", requires_approval=True, approval_status="pending", working_path=original.working_path))
        await db.flush()
        db.add(MoodleApproval(message_id=second_id, request_id=request_id, source_agent_id=request_row["agent_id"],
            params_hash="a" * 64, state="pending", expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
        await db.commit()
        links = (await db.scalars(select(MoodleApproval).where(MoodleApproval.message_id.in_([original.id, second_id])))).all()
        items = []
        for link in links:
            demand = await db.get(AgentDemand, link.message_id)
            items.append({"message_id": str(demand.id), "request_id": str(link.request_id), "params_hash": link.params_hash,
                "message_updated_at": demand.updated_at.isoformat()})
    try:
        url = "/api/v1/personal/moodle-approvals/authorize"
        payload = {"executor_agent_id": str(request_row["agent_id"]), "instruction": "Use the authorized parameters", "items": items}
        bad = {**payload, "items": [items[0], {**items[1], "params_hash": "b" * 64}]}
        assert (await client.post(url, headers=headers, json=bad)).status_code == 409
        async with AsyncSessionLocal() as db:
            links = (await db.scalars(select(MoodleApproval).where(MoodleApproval.message_id.in_([original.id, second_id])))).all()
            assert all(link.state == "pending" and link.approved_at is None for link in links)
            for link in links:
                demand = await db.get(AgentDemand, link.message_id)
                assert demand.scheduled_at is None and demand.approval_status == "pending"
        response = await client.post(url, headers=headers, json=payload)
        assert response.status_code == 200, response.text
        assert len(response.json()["approved"]) == 2
        async with AsyncSessionLocal() as db:
            links = (await db.scalars(select(MoodleApproval).where(MoodleApproval.message_id.in_([original.id, second_id])))).all()
            assert len({link.approved_at for link in links}) == 1
            for link in links:
                demand = await db.get(AgentDemand, link.message_id)
                assert link.state == "approved" and link.claimed_at is None
                assert demand.approval_status == "approved" and demand.scheduled_at is not None
                assert approval_fingerprint(demand) == demand.approved_content_hash == link.message_hash
                assert str(link.request_id) in demand.body and str(demand.id) in demand.body and link.params_hash in demand.body
                status = await moodle_approval.claim_status(StatusIn(request_id=link.request_id, message_id=demand.id),
                    principal=ActorPrincipal("agent", request_row["agent_id"], "Maia"), db=db)
                assert status["state"] == "approved"
        # A repeated batch cannot produce another authorization or a new run.
        assert (await client.post(url, headers=headers, json=payload)).status_code == 409
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AuditEvent).where(AuditEvent.entity_id == second_id))
            await db.execute(delete(MoodleApproval).where(MoodleApproval.message_id == second_id))
            await db.execute(delete(AgentDemand).where(AgentDemand.id == second_id))
            await db.commit()

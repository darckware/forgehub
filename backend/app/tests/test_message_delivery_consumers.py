"""Verified deliveries silence obsolete failure consumers, preserving attempt history."""
import uuid

import pytest
from sqlalchemy import delete, or_, select

from app.core.config import settings
from app.core.demand_workflow import approval_fingerprint
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent
from app.db.models.notification import Notification


@pytest.fixture
async def delivery_source(test_suite_agent, monkeypatch):
    monkeypatch.setattr(settings, "MESSAGE_TRIAGE_ENABLED", False)
    async with AsyncSessionLocal() as db:
        executor = Agent(name=f"Delivery consumer {uuid.uuid4().hex}", agent_type="executor",
                         runtime_type="codex", profile_slug=f"delivery-test-{uuid.uuid4().hex}")
        db.add(executor)
        await db.flush()
        source = AgentDemand(from_agent="test-suite", from_agent_id=test_suite_agent,
            target_agent_id=executor.id, subject=f"Verified work {uuid.uuid4().hex}",
            body="Already delivered independently. Responda pelo Telegram.", origin_type="task",
            working_path="/tmp/test-delivery-consumer", status="read", channel="agent",
            dispatch_status="failed", dispatch_error="Provider usage limit exceeded",
            dispatch_result="Original attempt evidence", dispatch_attempts=2, agent_run_id=str(uuid.uuid4()))
        db.add(source)
        await db.flush()
        proof = AuditEvent(entity_type="agent_demand", entity_id=source.id,
            event_type="message_delivery_verified", actor="test",
            payload={"content_hash": approval_fingerprint(source), "evidence_ref": "git:1234567",
                     "summary": "Independent delivery verified"})
        db.add(proof)
        await db.commit()
        source_id, executor_id = source.id, executor.id
        try:
            yield db, source, proof
        finally:
            await db.rollback()
            children = list((await db.scalars(select(AgentDemand.id).where(or_(
                AgentDemand.reply_to_id == source_id, AgentDemand.failure_check_source_id == source_id)))).all())
            await db.execute(delete(Notification).where(Notification.event_key.contains(str(source_id))))
            await db.execute(delete(AuditEvent).where(AuditEvent.entity_id.in_([source_id, *children])))
            if children:
                await db.execute(delete(AgentDemand).where(AgentDemand.id.in_(children)))
            await db.execute(delete(AgentDemand).where(AgentDemand.id == source_id))
            await db.execute(delete(Agent).where(Agent.id == executor_id))
            await db.commit()


def attempt_evidence(source):
    return {key: getattr(source, key) for key in ("status", "dispatch_status", "dispatch_result",
        "dispatch_error", "dispatch_attempts", "agent_run_id", "scheduled_at", "body")}


async def test_delivered_work_cannot_open_new_diagnostic_with_triage_disabled(delivery_source):
    from app.core.demand_failure_check import ensure_failure_check, failure_check_eligible
    db, source, proof = delivery_source
    source_id, original = source.id, attempt_evidence(source)
    assert settings.MESSAGE_TRIAGE_ENABLED is False
    assert await failure_check_eligible(db, source) is False
    assert await ensure_failure_check(db, source_id) is None
    await db.commit()
    await db.refresh(source)
    assert attempt_evidence(source) == original
    assert not await db.scalar(select(AgentDemand.id).where(AgentDemand.failure_check_source_id == source_id))


@pytest.mark.parametrize("channel,same_agent,event_type", [
    ("agent", False, "message_delivery_verified"),
    ("agent", True, "message_work_resolved"),
    ("telegram", False, "message_delivery_verified"),
    ("workspace", False, "message_work_resolved"),
    ("assistant", False, "message_delivery_verified"),
])
async def test_feedback_handled_once_without_child_or_notification(
        delivery_source, monkeypatch, channel, same_agent, event_type):
    from app.core import feedback
    db, source, proof = delivery_source
    source.channel, source.channel_ref = channel, "test-no-delivery"
    if same_agent:
        source.target_agent_id = source.from_agent_id
    proof.event_type = event_type
    proof.payload = {**proof.payload, "content_hash": approval_fingerprint(source)}
    await db.commit()
    source_id, proof_id, original = source.id, proof.id, attempt_evidence(source)
    async def unexpected_delivery(*args, **kwargs):
        pytest.fail("Verified delivery must not emit obsolete failure feedback")
    for name in ("_deliver_telegram", "_deliver_workspace", "send_to_group"):
        monkeypatch.setattr(feedback, name, unexpected_delivery)
    assert settings.MESSAGE_TRIAGE_ENABLED is False
    assert source.feedback_sent_at is None
    assert await feedback.deliver_feedback(db, source) is True
    await db.commit()
    await db.refresh(source)
    handled_at = source.feedback_sent_at
    assert handled_at is not None and attempt_evidence(source) == original
    assert await feedback.deliver_feedback(db, source) is False
    await db.commit()
    await db.refresh(source)
    assert source.feedback_sent_at == handled_at and attempt_evidence(source) == original
    assert not await db.scalar(select(AgentDemand.id).where(or_(
        AgentDemand.reply_to_id == source_id, AgentDemand.failure_check_source_id == source_id)))
    assert not await db.scalar(select(Notification.id).where(Notification.event_key.contains(str(source_id))))
    events = (await db.scalars(select(AuditEvent).where(AuditEvent.entity_id == source_id,
        AuditEvent.event_type == "message_feedback_superseded"))).all()
    assert len(events) == 1
    assert events[0].payload["delivery_event_id"] == str(proof_id)
    assert events[0].payload["evidence_ref"] == "git:1234567"


async def test_old_delivery_for_changed_content_does_not_suppress_failure(delivery_source):
    from app.core.demand_failure_check import failure_check_eligible
    db, source, proof = delivery_source
    source.body = "New scope not covered by old delivery"
    await db.commit()
    assert await failure_check_eligible(db, source) is True

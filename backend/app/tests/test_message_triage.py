"""Real isolated DB: analysis never substitutes for execution authority or proof."""
import uuid
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.demand_workflow import WorkflowBlocked, approval_fingerprint
from app.db.base import AsyncSessionLocal
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent
from app.tests.fixtures.demand_cleanup import cleanup_agent_demands


@pytest.fixture
async def triage_db(test_suite_agent):
    from app.db.models.message_triage import MessageAnalysisRun
    async with AsyncSessionLocal() as db:
        run_ids = []
        try:
            yield db, test_suite_agent, run_ids
        finally:
            await db.rollback()
            from app.db.models.moodle_approval import MoodleApproval
            await db.execute(delete(MoodleApproval).where(MoodleApproval.source_agent_id==test_suite_agent))
            await cleanup_agent_demands(db, [test_suite_agent])
            if run_ids:
                await db.execute(delete(MessageAnalysisRun).where(MessageAnalysisRun.id.in_(run_ids)))
            await db.commit()


async def message(db, agent, **kw):
    row = AgentDemand(**dict(from_agent="test-suite", from_agent_id=agent, target_agent_id=agent,
        subject="work-" + uuid.uuid4().hex, body="Deliver a verified change", origin_type="task",
        working_path="/root/project/fake", **kw))
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def test_duplicate_analysis_requests_share_durable_job_and_ignore_pagination(triage_db, monkeypatch):
    from app.core.message_triage import enqueue_analysis
    db, agent, run_ids = triage_db
    monkeypatch.setattr(settings, "MESSAGE_TRIAGE_ENABLED", True)
    first = await enqueue_analysis(db, actor="test", agent_id=agent)
    run_ids.append(first.id)
    second = await enqueue_analysis(db, actor="test", agent_id=agent)
    assert second.id == first.id and second.status == "queued"
    assert first.scope == {"agent_id": str(agent), "context": None}


async def test_unanalyzed_failure_is_not_automatically_an_operator_decision(triage_db):
    from app.core.demand_management import list_agent_work
    db, agent, _ = triage_db
    row = await message(db, agent, dispatch_status="failed", dispatch_error="STATUS: PARTIAL")
    result = await list_agent_work(db, view="decision", agent_id=agent, group="tasks")
    assert row.id not in {uuid.UUID(x["id"]) for x in result["items"]}
    result = await list_agent_work(db, view="processing", agent_id=agent, group="tasks")
    assert str(row.id) in {x["id"] for x in result["items"]}


async def test_real_authorization_stays_visible_without_model(triage_db):
    from app.core.demand_management import list_agent_work
    db, agent, _ = triage_db
    row = await message(db, agent, requires_approval=True, approval_status="pending")
    result = await list_agent_work(db, view="decision", agent_id=agent, group="tasks")
    assert str(row.id) in {x["id"] for x in result["items"]}


async def test_delivery_veto_survives_disabled_triage_and_new_analysis(triage_db, monkeypatch):
    from app.core.demand_dispatch_guard import ensure_task_dispatch_admissible
    db, agent, _ = triage_db
    row = await message(db, agent)
    db.add(AuditEvent(entity_type="agent_demand", entity_id=row.id,
        event_type="message_delivery_verified", actor="operator", payload={
            "content_hash": approval_fingerprint(row), "evidence_ref": "git:1234567", "summary": "Verified deployment"}))
    await db.commit()
    monkeypatch.setattr(settings, "MESSAGE_TRIAGE_ENABLED", False)
    with pytest.raises(WorkflowBlocked, match="delivered"):
        await ensure_task_dispatch_admissible(db, row)


async def test_delivered_source_vetoes_diagnostic_and_resolves_it_as_obsolete(triage_db,monkeypatch):
    from app.core.message_triage import check_admission, deterministic_analysis
    db,agent,_=triage_db
    source=await message(db,agent,dispatch_status="failed",dispatch_error="Old failed attempt")
    source_id=source.id
    db.add(AuditEvent(entity_type="agent_demand",entity_id=source_id,
        event_type="message_delivery_verified",actor="operator",payload={
            "content_hash":approval_fingerprint(source),"evidence_ref":"git:1234567","summary":"Independent delivery verified"}))
    await db.commit()
    child=await message(db,agent,failure_check_source_id=source_id)
    monkeypatch.setattr(settings,"MESSAGE_TRIAGE_ENABLED",False)
    with pytest.raises(WorkflowBlocked,match="delivered"):
        await check_admission(db,child)
    decision=await deterministic_analysis(db,child)
    assert decision.status=="resolved" and decision.category=="obsolete" and decision.proposed_action=="resolve"
    assert source.dispatch_status=="failed" and child.dispatch_status is None


async def test_changed_diagnostic_source_invalidates_an_obsolete_decision(triage_db):
    from app.core import message_triage
    from app.db.models.message_triage import MessageTriageResult
    db,agent,run_ids=triage_db
    source=await message(db,agent,dispatch_status="failed",dispatch_error="Old failed attempt")
    source_id=source.id
    db.add(AuditEvent(entity_type="agent_demand",entity_id=source_id,
        event_type="message_delivery_verified",actor="operator",payload={
            "content_hash":approval_fingerprint(source),"evidence_ref":"git:1234567"}))
    await db.commit()
    child=await message(db,agent,failure_check_source_id=source_id)
    child_id=child.id
    chosen=await message_triage.deterministic_analysis(db,child)
    prepared=await prepared_application(db,agent,run_ids,child)
    async with AsyncSessionLocal() as other:
        current=await other.get(AgentDemand,source_id)
        current.body="Scope changed after the analysis snapshot"
        await other.commit()
    assert await message_triage._apply(db,*prepared,chosen)
    assert await db.get(MessageTriageResult,child_id) is None


@pytest.mark.parametrize("report",["DONE","PARTIAL"])
async def test_completed_diagnostic_archival_preserves_unresolved_original(triage_db,report):
    from app.core import message_triage
    db,agent,run_ids=triage_db
    source=await message(db,agent,dispatch_status="failed",dispatch_error="Original problem persists")
    source_id=source.id
    child=await message(db,agent,failure_check_source_id=source_id,dispatch_status="completed",
        dispatch_result=f"Diagnostic report only.\nSTATUS: {report} | evidence: recorded report")
    child_id=child.id
    chosen=await message_triage.deterministic_analysis(db,child)
    if report=="PARTIAL":
        assert chosen is None
        return
    assert chosen.status=="resolved" and chosen.category=="diagnosis"
    prepared=await prepared_application(db,agent,run_ids,child)
    assert await message_triage._apply(db,*prepared,chosen)
    current=await db.get(AgentDemand,child_id,populate_existing=True)
    original=await db.get(AgentDemand,source_id,populate_existing=True)
    assert current.status=="archived" and current.dispatch_status=="completed"
    assert original.status!="archived" and original.dispatch_status=="failed"
    assert await message_triage.verified_delivery(db,original) is None


async def test_verified_delivery_leaves_active_inbox_without_rewriting_attempt(triage_db):
    from app.core import message_triage
    db,agent,run_ids=triage_db
    row=await message(db,agent,dispatch_status="failed",dispatch_error="Old failure",dispatch_result="Old report")
    row_id=row.id
    db.add(AuditEvent(entity_type="agent_demand",entity_id=row_id,event_type="message_delivery_verified",
        actor="operator",payload={"content_hash":approval_fingerprint(row),"evidence_ref":"git:1234567"}))
    await db.commit()
    chosen=await message_triage.deterministic_analysis(db,row)
    prepared=await prepared_application(db,agent,run_ids,row)
    assert await message_triage._apply(db,*prepared,chosen)
    row=await db.get(AgentDemand,row_id,populate_existing=True)
    assert row.status=="archived" and row.decision_reason
    assert row.dispatch_status=="failed" and row.dispatch_error=="Old failure" and row.dispatch_result=="Old report"
    assert await message_triage.verified_delivery(db,row)


async def test_self_feedback_becomes_history_without_changing_origin_failure(triage_db):
    from app.core.message_triage import deterministic_analysis
    db, agent, _ = triage_db
    source = await message(db, agent, dispatch_status="failed", dispatch_error="STATUS: PARTIAL")
    notice = await message(db, agent, reply_to_id=source.id, dispatch_status="completed",
                           command_text=f"failure-feedback:{source.id}:1")
    result = await deterministic_analysis(db, notice)
    assert result.category == "feedback" and result.proposed_action == "archive_notice"
    assert source.dispatch_status == "failed"


async def test_partial_moodle_report_cannot_be_closed_by_completed_proposal(triage_db):
    from app.core.message_triage import deterministic_analysis
    from app.db.models.moodle_approval import MoodleApproval
    db, agent, _ = triage_db
    row = await message(db, agent, dispatch_status="failed", dispatch_error="STATUS: PARTIAL",
                        dispatch_result="A user exists; enrollment still pending.\nSTATUS: PARTIAL")
    db.add(MoodleApproval(message_id=row.id,request_id=uuid.uuid4(),source_agent_id=agent,
        params_hash="a"*64,message_hash=approval_fingerprint(row),expires_at=datetime.now(timezone.utc)+timedelta(days=1),state="finished",outcome="completed"))
    await db.commit()
    assert await deterministic_analysis(db,row) is None


async def test_delivered_moodle_report_is_resolved_without_rewriting_attempt(triage_db):
    from app.core.message_triage import deterministic_analysis
    from app.db.models.moodle_approval import MoodleApproval
    db, agent, _ = triage_db
    row = await message(db,agent,dispatch_status="failed",dispatch_error="Missing report",
                        dispatch_result="Recorded operation complete.\nSTATUS: DONE | evidence: executed")
    db.add(MoodleApproval(message_id=row.id,request_id=uuid.uuid4(),source_agent_id=agent,
        params_hash="a"*64,message_hash=approval_fingerprint(row),expires_at=datetime.now(timezone.utc)+timedelta(days=1),state="finished",outcome="completed"))
    await db.commit()
    result = await deterministic_analysis(db,row)
    assert result.category=="delivered" and result.proposed_action=="resolve"
    assert row.dispatch_status=="failed"


async def test_admin_delivery_rechecks_version_after_host_evidence(triage_db,monkeypatch):
    from app.core import message_triage
    from app.api.schemas.message_triage import MessageDeliveryIn
    db,agent,_=triage_db
    row=await message(db,agent)
    row_id=row.id
    before=row.updated_at
    async def verify(*args):
        async with AsyncSessionLocal() as other:
            current=await other.get(AgentDemand,row_id)
            current.body="A changed scope, not covered by the old evidence"
            await other.commit()
        return True,"verified"
    monkeypatch.setattr(message_triage,"verify_on_host",verify)
    with pytest.raises(WorkflowBlocked):
        await message_triage.register_delivery(db,row_id,MessageDeliveryIn(expected_updated_at=before,
            evidence_ref="git:1234567",summary="Original delivery verified"),actor="operator")
    assert not await db.scalar(select(AuditEvent.id).where(AuditEvent.entity_id==row_id,
        AuditEvent.event_type=="message_delivery_verified"))


async def test_analysis_api_is_admin_only_and_feature_gated(triage_db, admin_headers, monkeypatch):
    from app.main import app
    from app.core.security import create_access_token
    from app.db.models.user import User
    db, agent, run_ids = triage_db
    username="test-triage-user-"+uuid.uuid4().hex
    user=User(username=username,hashed_password="unused",is_admin=False)
    db.add(user)
    await db.commit()
    user_id=user.id
    nonadmin={"Authorization":"Bearer "+create_access_token(username)}
    try:
        await check_analysis_api(app,agent,run_ids,admin_headers,nonadmin,monkeypatch)
    finally:
        await db.execute(delete(User).where(User.id==user_id))
        await db.commit()


async def check_analysis_api(app,agent,run_ids,admin_headers,nonadmin,monkeypatch):
    from httpx import ASGITransport, AsyncClient
    async with AsyncClient(transport=ASGITransport(app=app),base_url="http://test") as client:
        path="/api/v1/demands/agent-work/analyze"
        assert (await client.post(path,json={})).status_code==401
        assert (await client.post(path,json={},headers=nonadmin)).status_code==403
        monkeypatch.setattr(settings,"MESSAGE_TRIAGE_ENABLED",False)
        assert (await client.post(path,json={},headers=admin_headers)).status_code==503
        monkeypatch.setattr(settings,"MESSAGE_TRIAGE_ENABLED",True)
        assert (await client.post(path,json={"context":"invalid"},headers=admin_headers)).status_code==422
        result=await client.post(path,json={"agent_id":str(agent)},headers=admin_headers)
        assert result.status_code==202,result.text
        data=result.json()
        run_ids.append(uuid.UUID(data["id"]))
        assert data["status"]=="queued"
        latest=await client.get("/api/v1/demands/agent-work/analysis",params={"agent_id":str(agent)},headers=admin_headers)
        assert latest.status_code==200 and latest.json()["id"]==data["id"]
        status=await client.get("/api/v1/demands/agent-work/analysis/"+data["id"],headers=admin_headers)
        assert status.status_code==200 and status.json()["processed"]==0


def advisory(row, **overrides):
    from app.api.schemas.message_triage import TriageSuggestion
    values = dict(message_id=row.id, status="waiting", category="service",
        summary="Aguardar o serviço", reason="O provedor ainda precisa responder.",
        recommendation="Revisar a disponibilidade antes de executar.", proposed_action="none")
    values.update(overrides)
    return TriageSuggestion(**values)


async def prepared_application(db, agent, run_ids, row, related=()):
    """Persist the same observation/lease boundary used by the background worker."""
    from app.core import message_triage
    from app.core.message_triage_context import context_stamp, source_stamp
    run = await message_triage.enqueue_analysis(db, actor="test", agent_id=agent)
    run_ids.append(run.id)
    claim = await message_triage._claim_job(db)
    assert claim is not None and claim[0] == run.id
    stamp = source_stamp(row)
    context, versions = await context_stamp(db, row, related)
    row_id = row.id
    await db.rollback()
    return claim[0], claim[1], row_id, stamp, context, versions


async def test_manual_job_analyzes_all_26_messages_beyond_first_page(triage_db, monkeypatch):
    from app.core import message_triage, message_triage_analysis
    from app.core.demand_management import list_agent_work
    from app.db.models.message_triage import MessageAnalysisItem, MessageTriageResult
    db, agent, run_ids = triage_db
    rows = [await message(db, agent) for _ in range(26)]
    ids = {row.id for row in rows}
    page = await list_agent_work(db, view="processing", agent_id=agent, group="tasks", page_size=25)
    assert page["total"] == 26 and len(page["items"]) == 25
    observed = []
    async def analyze(_db, items, related, agents, availability):
        observed.extend(uuid.UUID(item["id"]) for item in items)
        return [advisory(SimpleNamespace(id=uuid.UUID(item["id"]))) for item in items]
    monkeypatch.setattr(message_triage_analysis, "analyze_messages", analyze)
    run = await message_triage.enqueue_analysis(db, actor="test", agent_id=agent)
    run_id = run.id
    run_ids.append(run_id)
    assert run.total == 26
    await db.rollback()
    assert await message_triage.process_next_analysis() is True
    await db.refresh(run)
    assert run.status == "completed" and run.total == run.processed == 26 and run.applied == 0
    assert set(observed) == ids and len(observed) == 26
    results = (await db.scalars(select(MessageTriageResult).where(MessageTriageResult.message_id.in_(ids)))).all()
    items = (await db.scalars(select(MessageAnalysisItem).where(MessageAnalysisItem.run_id == run_id))).all()
    assert len(results) == 26 and all(result.operator_state == "waiting" for result in results)
    assert len(items) == 26 and all(item.status == "done" for item in items)


async def test_model_outage_preserves_deterministic_notice_and_original_attempt(triage_db, monkeypatch):
    from app.core import message_triage, message_triage_analysis
    from app.core.message_triage_context import source_stamp
    from app.db.models.message_triage import MessageAnalysisItem, MessageTriageResult
    db, agent, run_ids = triage_db
    source = await message(db, agent, dispatch_status="failed", dispatch_error="Provider unavailable",
                           dispatch_result="Original failed attempt evidence", dispatch_attempts=2)
    # Proof at the end of a larger job must survive a provider failure in
    # its first batch, rather than remaining stranded behind that failure.
    for _ in range(24):
        await message(db, agent)
    notice = await message(db, agent, reply_to_id=source.id, dispatch_status="completed",
                           command_text=f"failure-feedback:{source.id}:2", id=uuid.UUID(int=(1<<128)-1))
    source_id, notice_id = source.id, notice.id
    original_stamp = source_stamp(source)
    calls = []
    async def unavailable(*args):
        calls.append(True)
        raise message_triage_analysis.AnalysisError("Analysis unavailable; retry later.")
    monkeypatch.setattr(message_triage_analysis, "analyze_messages", unavailable)
    run = await message_triage.enqueue_analysis(db, actor="test", agent_id=agent)
    run_id = run.id
    run_ids.append(run_id)
    await db.rollback()
    assert await message_triage.process_next_analysis()
    assert calls
    await db.refresh(run)
    assert run.status == "failed" and run.error == message_triage.SAFE_ERROR
    assert run.processed == run.applied == 1
    original = await db.get(AgentDemand, source_id, populate_existing=True)
    assert source_stamp(original) == original_stamp
    assert original.dispatch_status == "failed" and original.dispatch_attempts == 2
    assert original.dispatch_result == "Original failed attempt evidence"
    archived = await db.get(AgentDemand, notice_id, populate_existing=True)
    assert archived.status == "archived" and archived.dispatch_status == "completed"
    result = await db.get(MessageTriageResult, notice_id)
    assert result.category == "feedback" and result.applied_action == "archive_notice"
    assert (await db.get(MessageAnalysisItem, (run_id, notice_id))).status == "done"
    assert (await db.get(MessageAnalysisItem, (run_id, source_id))).status == "pending"
    assert not await db.scalar(select(AuditEvent.id).where(AuditEvent.entity_id == source_id,
        AuditEvent.event_type == "message_work_resolved"))


@pytest.mark.parametrize("changed", ["source", "related"])
async def test_changed_source_or_linked_context_skips_application(triage_db, changed):
    from app.core import message_triage
    from app.db.models.message_triage import MessageAnalysisItem, MessageAnalysisRun, MessageTriageResult
    db, agent, run_ids = triage_db
    row = await message(db, agent)
    linked = await message(db, agent)
    row_id, linked_id = row.id, linked.id
    suggestion = advisory(row)
    prepared = await prepared_application(db, agent, run_ids, row, [linked_id])
    async with AsyncSessionLocal() as other:
        edited = await other.get(AgentDemand, row_id if changed == "source" else linked_id)
        edited.body = "Changed independently after model observation"
        await other.commit()
    assert await message_triage._apply(db, *prepared, suggestion) is True
    assert await db.get(MessageTriageResult, row_id) is None
    assert (await db.get(MessageAnalysisItem, (prepared[0], row_id))).status == "skipped"
    run = await db.get(MessageAnalysisRun, prepared[0])
    assert run.processed == 1 and run.applied == 0
    assert not await db.scalar(select(AuditEvent.id).where(AuditEvent.entity_id == row_id,
        AuditEvent.event_type == "message_triage_decided"))


@pytest.mark.parametrize("fence", ["expired", "replaced_token"])
async def test_expired_or_replaced_lease_cannot_apply_a_suggestion(triage_db, fence):
    from app.core import message_triage
    from app.db.models.message_triage import MessageAnalysisItem, MessageAnalysisRun, MessageTriageResult
    db, agent, run_ids = triage_db
    row = await message(db, agent)
    row_id = row.id
    suggestion = advisory(row)
    prepared = await prepared_application(db, agent, run_ids, row)
    async with AsyncSessionLocal() as other:
        run = await other.get(MessageAnalysisRun, prepared[0])
        if fence == "expired":
            run.lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
        else:
            run.lease_token = uuid.uuid4()
        await other.commit()
    assert await message_triage._apply(db, *prepared, suggestion) is False
    assert await db.get(MessageTriageResult, row_id) is None
    assert (await db.get(MessageAnalysisItem, (prepared[0], row_id))).status == "pending"
    run = await db.get(MessageAnalysisRun, prepared[0], populate_existing=True)
    assert run.processed == run.applied == 0


async def test_ai_resolution_without_independent_proof_remains_waiting(triage_db):
    from app.core import message_triage
    from app.core.message_triage_context import source_stamp
    from app.db.models.message_triage import MessageTriageResult
    db, agent, run_ids = triage_db
    row = await message(db, agent, dispatch_status="failed", dispatch_error="Provider unavailable",
                        dispatch_attempts=2, dispatch_result="Unverified attempt output")
    row_id, original_stamp = row.id, source_stamp(row)
    suggestion = advisory(row, status="resolved", category="delivered", proposed_action="resolve")
    prepared = await prepared_application(db, agent, run_ids, row)
    assert await message_triage._apply(db, *prepared, suggestion)
    result = await db.get(MessageTriageResult, row_id)
    assert result.operator_state == "waiting" and result.proposed_action == "none"
    assert result.applied_action is None
    await db.refresh(row)
    assert source_stamp(row) == original_stamp and row.status != "archived"
    assert not await message_triage.verified_delivery(db, row)
    assert not await db.scalar(select(AuditEvent.id).where(AuditEvent.entity_id == row_id,
        AuditEvent.event_type == "message_work_resolved"))


async def test_advisory_diagnosis_does_not_claim_processing_without_dispatch(triage_db):
    from app.core import message_triage
    from app.db.models.message_triage import MessageTriageResult
    db,agent,run_ids=triage_db
    row=await message(db,agent)
    row_id=row.id
    suggestion=advisory(row,status="processing",proposed_action="diagnose")
    prepared=await prepared_application(db,agent,run_ids,row)
    assert await message_triage._apply(db,*prepared,suggestion)
    result=await db.get(MessageTriageResult,row_id)
    assert result.operator_state=="waiting" and result.proposed_action=="none"
    assert result.applied_action is None


@pytest.mark.parametrize("category", ["authorization", "information"])
async def test_ai_operator_decision_requires_independent_blocking_fact(triage_db, category):
    from app.core import message_triage
    from app.core.message_triage_context import source_stamp
    from app.db.models.message_triage import MessageTriageResult
    db, agent, run_ids = triage_db
    row = await message(db, agent)
    row_id, original_stamp = row.id, source_stamp(row)
    suggestion = advisory(row, status="decision", category=category)
    prepared = await prepared_application(db, agent, run_ids, row)
    assert await message_triage._apply(db, *prepared, suggestion)
    result = await db.get(MessageTriageResult, row_id)
    assert result.operator_state == "waiting" and result.proposed_action == "none"
    assert result.applied_action is None
    await db.refresh(row)
    assert source_stamp(row) == original_stamp and row.requires_approval is False


async def test_answered_blocking_question_invalidates_decision_and_visible_analysis(triage_db):
    from app.core import message_triage
    from app.core.demand_management import list_agent_work
    from app.core.message_triage_context import source_stamp
    from app.db.models.operations import AgentQuestion
    db, agent, run_ids = triage_db
    row = await message(db, agent)
    row_id, original_stamp = row.id, source_stamp(row)
    question = AgentQuestion(agent_id=agent, origin_demand_id=row_id,
        question="Qual é o destino confirmado?", blocking=True, status="pending",
        notify_after=datetime.now(timezone.utc))
    db.add(question)
    await db.commit()
    question_id = question.id
    try:
        chosen = await message_triage.deterministic_analysis(db, row)
        assert chosen.status == "decision"
        prepared = await prepared_application(db, agent, run_ids, row)
        assert await message_triage._apply(db, *prepared, chosen)
        before = await list_agent_work(db, view="decision", agent_id=agent, group="tasks")
        visible = next(item for item in before["items"] if item["id"] == str(row_id))
        assert visible["analysis"] is not None
        async with AsyncSessionLocal() as other:
            answered = await other.get(AgentQuestion, question_id)
            answered.status = "answered"
            answered.answer = "Destino confirmado pelo operador"
            answered.answered_at = datetime.now(timezone.utc)
            answered.answered_by = "test"
            await other.commit()
        await db.rollback()
        current = await db.get(AgentDemand, row_id, populate_existing=True)
        assert source_stamp(current) == original_stamp
        decisions = await list_agent_work(db, view="decision", agent_id=agent, group="tasks")
        assert str(row_id) not in {item["id"] for item in decisions["items"]}
        processing = await list_agent_work(db, view="processing", agent_id=agent, group="tasks")
        visible = next(item for item in processing["items"] if item["id"] == str(row_id))
        assert visible["operator_state"] == "processing" and visible["analysis"] is None
    finally:
        await db.rollback()
        await db.execute(delete(AgentQuestion).where(AgentQuestion.id == question_id))
        await db.commit()


@pytest.mark.parametrize("source_approval_pending", [False, True])
async def test_executable_answer_uses_queue_without_granting_source_approval(triage_db, monkeypatch, source_approval_pending):
    from app.core import message_triage
    from app.db.models.message_triage import MessageTriageResult
    from app.db.models.operations import AgentQuestion
    db, agent, run_ids = triage_db
    source = await message(db, agent, requires_approval=source_approval_pending,
        approval_status="pending" if source_approval_pending else None)
    source_id = source.id
    answer = await message(db, agent, reply_to_id=source_id)
    answer_id = answer.id
    question = AgentQuestion(agent_id=agent, origin_demand_id=source_id, reply_demand_id=answer_id,
        question="Qual formato?", answer="CSV", blocking=True, status="answered",
        answered_at=datetime.now(timezone.utc), notify_after=datetime.now(timezone.utc))
    db.add(question)
    await db.commit()
    question_id = question.id
    try:
        if source_approval_pending:
            from app.core.demand_workflow import ensure_workflow_allowed
            with pytest.raises(WorkflowBlocked, match="original task authorization"):
                await ensure_workflow_allowed(db, answer)
        prepared = await prepared_application(db, agent, run_ids, answer)
        assert await message_triage._apply(db, *prepared,
            advisory(SimpleNamespace(id=answer_id), status="processing", category="ready", proposed_action="queue"))
        result = await db.get(MessageTriageResult, answer_id, populate_existing=True)
        assert result.operator_state == ("waiting" if source_approval_pending else "processing")
        assert result.applied_action == (None if source_approval_pending else "queued")
        source = await db.get(AgentDemand, source_id, populate_existing=True)
        if source_approval_pending: assert source.approval_status == "pending"
        assert source.agent_run_id is None
        if not source_approval_pending:
            monkeypatch.setattr(settings, "MESSAGE_TRIAGE_ENABLED", True)
            current = await db.get(AgentDemand, answer_id, populate_existing=True)
            await message_triage.check_admission(db, current)
            source.body = "Changed original scope after the answer was analyzed"
            await db.commit()
            with pytest.raises(WorkflowBlocked, match="Analysis has changed"):
                await message_triage.check_admission(db, current)
    finally:
        await db.execute(delete(AgentQuestion).where(AgentQuestion.id == question_id))
        await db.commit()


async def test_nested_continuation_cannot_bypass_original_approval(triage_db):
    from app.core.demand_workflow import ensure_workflow_allowed
    db, agent, _ = triage_db
    original = await message(db, agent, requires_approval=True, approval_status="pending")
    intermediate = await message(db, agent, reply_to_id=original.id)
    continuation = await message(db, agent, reply_to_id=intermediate.id)
    with pytest.raises(WorkflowBlocked, match="original task authorization"):
        await ensure_workflow_allowed(db, continuation)


@pytest.mark.parametrize("cycle", [False, True])
async def test_source_graph_distinguishes_shared_ancestor_from_cycle(triage_db, cycle):
    from app.core.demand_workflow import ensure_workflow_allowed
    db, agent, _ = triage_db
    original = await message(db, agent)
    left = await message(db, agent, reply_to_id=original.id)
    right = await message(db, agent, failure_check_source_id=original.id)
    continuation = await message(db, agent, reply_to_id=left.id, failure_check_source_id=right.id)
    if cycle:
        original.reply_to_id = continuation.id
        await db.commit()
        with pytest.raises(WorkflowBlocked, match="Cyclic original task context"):
            await ensure_workflow_allowed(db, continuation)
    else:
        await ensure_workflow_allowed(db, continuation)


async def test_unscheduled_authorized_wait_recovers_without_analysis_or_event(triage_db, monkeypatch):
    from app.core import message_triage
    from app.api.routes import demand as routes
    from app.db.models.mission_cycle import AgentAvailability
    db, agent, run_ids = triage_db
    row = await message(db, agent)
    row_id = row.id
    available = AgentAvailability(agent_id=agent, unavailable_until=datetime.now(timezone.utc) + timedelta(hours=1),
        reason="test quota", recorded_by="test")
    db.add(available)
    await db.commit()
    prepared = await prepared_application(db, agent, run_ids, row)
    await message_triage._apply(db, *prepared, advisory(SimpleNamespace(id=row_id), status="processing", category="ready", proposed_action="queue"))
    await db.refresh(row)
    assert row.scheduled_at is None
    await db.delete(available)
    await db.commit()
    monkeypatch.setattr(settings, "MESSAGE_TRIAGE_ENABLED", False)
    starts = []
    async def slots(_db): return 10
    async def busy(_db): return set()
    async def dispatch(_db, current, target, _command):
        if current.id == row_id:
            starts.append(current.id)
            current.dispatch_status = "dispatched"
            current.agent_run_id = "recovered"
    monkeypatch.setattr(routes, "_dispatch_slots", slots)
    monkeypatch.setattr(routes, "_agents_already_running", busy)
    monkeypatch.setattr(routes, "_execute_dispatch", dispatch)
    await routes.run_scheduled_dispatch_pass(db)
    await routes.run_scheduled_dispatch_pass(db)
    assert starts == [row_id]

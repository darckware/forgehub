# ruff: noqa: F811
# Pytest injects fixtures imported from the existing domain test modules.
"""Contextual advice enriches real decisions without acquiring authority."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete

from app.api.schemas.message_triage import TriageSuggestion
from app.core import message_triage, message_triage_analysis
from app.db.models.message_triage import MessageTriageResult
from app.db.models.operations import AgentQuestion
from app.tests.test_message_triage import triage_db, message  # noqa: F401


@pytest.mark.parametrize("kind", ["authorization", "information"])
async def test_pending_decision_gets_contextual_advice_without_model_authority(triage_db, monkeypatch, kind):
    db, agent, run_ids = triage_db
    row = await message(db, agent, requires_approval=kind == "authorization",
                        approval_status="pending" if kind == "authorization" else None)
    message_id = row.id
    observed = []
    question = None
    if kind == "information":
        question = AgentQuestion(agent_id=agent, origin_demand_id=message_id,
            question="CSV ou XLSX?", context="CSV mantém compatibilidade; XLSX requer validação.", blocking=True,
            status="pending", notify_after=datetime.now(timezone.utc))
        db.add(question)
        await db.commit()


    async def analyze(_db, items, related, agents, availability):
        observed.extend(items)
        return [TriageSuggestion(message_id=message_id, status="resolved", category="delivered",
            summary="Objetivo: exportar os dados aprovados", reason="CSV é compatível; XLSX exige validação adicional.",
            recommendation="Preferir CSV se atende ao contrato; confirmar antes de executar.",
            proposed_action="resolve")]

    monkeypatch.setattr(message_triage_analysis, "analyze_messages", analyze)
    try:
        run = await message_triage.enqueue_analysis(db, actor="test", agent_id=agent)
        run_ids.append(run.id)
        await db.rollback()
        assert await message_triage.process_next_analysis()
        result = await db.get(MessageTriageResult, message_id, populate_existing=True)
        assert observed and observed[0]["id"] == str(message_id)
        if question:
            assert observed[0]["questions"][0]["question"] == "CSV ou XLSX?"
        assert result.summary == "Objetivo: exportar os dados aprovados"
        assert result.operator_state == "decision" and result.category == kind
        assert result.proposed_action == "none" and result.applied_action is None
        await db.refresh(row)
        assert row.dispatch_status is None and row.agent_run_id is None
        assert row.scheduled_at is None
        if kind == "authorization": assert row.approval_status == "pending"
    finally:
        await db.execute(delete(AgentQuestion).where(AgentQuestion.origin_demand_id == message_id))
        await db.commit()


@pytest.mark.parametrize("failure", ["outage", "source_change"])
async def test_decision_advice_preserves_fallback_and_rejects_changed_context(triage_db, monkeypatch, failure):
    from app.db.base import AsyncSessionLocal
    from app.db.models.demand import AgentDemand
    db, agent, run_ids = triage_db
    row = await message(db, agent, requires_approval=True, approval_status="pending")
    message_id = row.id
    observed = []

    async def analyze(_db, items, related, agents, availability):
        observed.extend(items)
        if failure == "outage":
            raise message_triage_analysis.AnalysisError("provider unavailable")
        async with AsyncSessionLocal() as changed:
            source = await changed.get(AgentDemand, message_id)
            source.body = "A different delivery scope"
            await changed.commit()
        return [TriageSuggestion(message_id=message_id, status="processing", category="ready",
            summary="Stale recommendation", reason="Stale context", recommendation="Execute now",
            proposed_action="queue")]

    monkeypatch.setattr(message_triage_analysis, "analyze_messages", analyze)
    run = await message_triage.enqueue_analysis(db, actor="test", agent_id=agent)
    run_ids.append(run.id)
    await db.rollback()
    assert await message_triage.process_next_analysis()
    result = await db.get(MessageTriageResult, message_id, populate_existing=True)
    assert observed
    assert result.summary == "Autorização necessária"
    assert result.operator_state == "decision" and result.applied_action is None
    await db.refresh(row)
    assert row.approval_status == "pending" and row.agent_run_id is None


@pytest.mark.parametrize("change", ["answer", "lease"])
async def test_decision_advice_is_fenced_after_answer_or_expired_lease(triage_db, monkeypatch, change):
    from datetime import timedelta
    from app.db.base import AsyncSessionLocal
    from app.db.models.message_triage import MessageAnalysisRun
    db, agent, run_ids = triage_db
    row = await message(db, agent)
    message_id = row.id
    question = AgentQuestion(agent_id=agent, origin_demand_id=message_id,
        question="Qual formato?", blocking=True, status="pending", notify_after=datetime.now(timezone.utc))
    db.add(question)
    await db.commit()
    question_id = question.id
    job_id = None

    async def analyze(_db, items, related, agents, availability):
        async with AsyncSessionLocal() as changed:
            if change == "answer":
                current = await changed.get(AgentQuestion, question_id)
                current.status, current.answer = "answered", "CSV"
                current.answered_at = datetime.now(timezone.utc)
            else:
                current = await changed.get(MessageAnalysisRun, job_id)
                current.lease_until = datetime.now(timezone.utc) - timedelta(seconds=5)
            await changed.commit()
        return [TriageSuggestion(message_id=message_id, status="processing", category="ready",
            summary="Outdated advice", reason="Old input", recommendation="Queue it", proposed_action="queue")]

    monkeypatch.setattr(message_triage_analysis, "analyze_messages", analyze)
    try:
        run = await message_triage.enqueue_analysis(db, actor="test", agent_id=agent)
        job_id = run.id
        run_ids.append(job_id)
        await db.rollback()
        assert await message_triage.process_next_analysis()
        result = await db.get(MessageTriageResult, message_id, populate_existing=True)
        assert result.summary == "Há uma pergunta para você"
        assert result.proposed_action == "none" and result.applied_action is None
        await db.refresh(row)
        assert row.agent_run_id is None and row.scheduled_at is None
    finally:
        await db.execute(delete(AgentQuestion).where(AgentQuestion.id == question_id))
        await db.commit()


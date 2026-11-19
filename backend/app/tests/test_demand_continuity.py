"""Messages phases 2 and 3 (2026-11-19, MESSAGES_GUIA.md §13): the thread is a
database link, it leaves Decisões only with an explicit outcome, the check's
ORIGEM line decides, and section 4 answers with evidence or says it can't."""
import json
import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent
from app.main import app

pytest_plugins = ["app.tests.test_demand_consolidation"]


@pytest.fixture
async def client(admin_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=admin_headers) as client:
        yield client


async def _known_failure(db, failed):
    """The fixture's failure, as a known (not uncertain) one with a directory."""
    failed.dispatch_error = "The agent run ended as 'failed'."
    failed.agent_run_id = str(uuid.uuid4())
    failed.dispatch_attempts = 1
    failed.working_path = "/srv/forgehub-test/project"
    failed.project_id = None
    failed.context_area = f"area-{uuid.uuid4().hex[:8]}"
    await db.commit()
    await db.refresh(failed)
    return failed


def _common(agent, **extra):
    return dict(from_agent="test-suite", from_agent_id=agent, target_agent_id=agent, origin_type="task", **extra)


async def _decide(client, demand, **body):
    return await client.post(f"/api/v1/demands/{demand.id}/decision",
                             json={"expected_updated_at": demand.updated_at.isoformat(), **body})


async def test_continuation_opens_a_linked_task_and_closes_the_original(client, consolidation_db):
    db, failed, _ = consolidation_db
    failed = await _known_failure(db, failed)
    work = (await client.get(f"/api/v1/demands/{failed.id}/brief")).json()
    assert {"continue", "done_by", "close_delivered"} <= {o["action"] for o in work["options"]}

    response = await _decide(client, failed, action="continue", reason="Falta publicar a migração")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "archived"
    await db.refresh(failed)
    continuation = await db.scalar(select(AgentDemand).where(AgentDemand.continues_id == failed.id))
    assert continuation is not None and continuation.scheduled_at is not None
    assert "Falta publicar a migração" in continuation.body and "Original evidence" in continuation.body
    assert continuation.target_agent_id == failed.target_agent_id
    source = failed
    assert source.decision_reason == f"Continuada por #{continuation.number}: Falta publicar a migração"
    events = (await db.scalars(select(AuditEvent).where(AuditEvent.entity_id == failed.id,
                                                       AuditEvent.event_type == "demand_archive"))).all()
    assert events and events[-1].payload["source"] == "continuation"

    thread = (await client.get(f"/api/v1/demands/{continuation.id}/brief")).json()["thread"]
    assert [(n["number"], n["role"]) for n in thread] == [(failed.number, "original"), (continuation.number, "continuation")]
    assert thread[1]["current"] is True


async def test_no_outcome_while_the_run_is_uncertain(client, consolidation_db):
    db, failed, _ = consolidation_db
    await db.commit()
    for action, extra in (("continue", {"reason": "x"}), ("done_by", {"related_number": 1}),
                          ("close_delivered", {"reason": "x", "evidence_ref": "git:abc"})):
        response = await _decide(client, failed, action=action, **extra)
        assert response.status_code == 409, (action, response.text)
    brief = (await client.get(f"/api/v1/demands/{failed.id}/brief")).json()
    assert brief["blocked"]["continue"] == "reconciliation_required"


async def test_outcomes_validate_their_inputs(client, consolidation_db):
    db, failed, _ = consolidation_db
    failed = await _known_failure(db, failed)
    assert (await _decide(client, failed, action="continue")).status_code == 422
    assert (await _decide(client, failed, action="done_by")).status_code == 422
    assert (await _decide(client, failed, action="close_delivered", reason="ok")).status_code == 422


async def test_done_by_needs_a_completed_task_and_records_the_link(client, consolidation_db, test_suite_agent):
    db, failed, _ = consolidation_db
    failed = await _known_failure(db, failed)
    pending = AgentDemand(subject="ainda na fila", body="b", **_common(test_suite_agent))
    done = AgentDemand(subject="fez", body="b", dispatch_status="completed", **_common(test_suite_agent))
    db.add_all([pending, done])
    await db.commit()
    refused = await _decide(client, failed, action="done_by", related_number=pending.number)
    assert refused.status_code == 409
    response = await _decide(client, failed, action="done_by", related_number=done.number, reason="mesmo escopo")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["done_by_id"] == str(done.id) and body["status"] == "archived"
    assert body["decision_reason"] == f"Feito por #{done.number}: mesmo escopo"
    thread = (await client.get(f"/api/v1/demands/{failed.id}/brief")).json()["thread"]
    assert {(n["number"], n["role"]) for n in thread} == {(failed.number, "original"), (done.number, "done_by")}


async def test_delivered_counts_as_delivery_and_is_never_dispatched_again(client, consolidation_db):
    from app.core.message_triage import verified_delivery
    db, failed, _ = consolidation_db
    failed = await _known_failure(db, failed)
    response = await _decide(client, failed, action="close_delivered", reason="Publicado", evidence_ref="git:abc1234")
    assert response.status_code == 200, response.text
    await db.refresh(failed)
    source = failed
    assert source.status == "archived" and source.decision_reason == "Entregue: Publicado"
    assert (await verified_delivery(db, source)).payload["evidence_ref"] == "git:abc1234"


async def test_origin_verdict_decides_the_original(consolidation_db, test_suite_agent):
    from app.core.demand_continuity import apply_origin_verdict
    db, failed, _ = consolidation_db
    failed = await _known_failure(db, failed)
    check = AgentDemand(subject="Checagem", body="d", failure_check_source_id=failed.id, dispatch_status="completed",
                        dispatch_result="ok\nORIGEM: PARCIAL\nSTATUS: DONE", **_common(test_suite_agent))
    db.add(check)
    await db.commit()
    assert await apply_origin_verdict(db, check) == "partial"
    await db.commit()
    assert (await db.get(AgentDemand, failed.id)).status != "archived"

    check.dispatch_result = "ok\nORIGEM: CONCLUÍDA\nSTATUS: DONE"
    assert await apply_origin_verdict(db, check) == "completed"
    await db.commit()
    source = await db.get(AgentDemand, failed.id)
    assert source.status == "archived"
    assert source.decision_reason == f"Checagem #{check.number}: ORIGEM CONCLUÍDA"
    # Decided once: a second verdict changes nothing.
    assert await apply_origin_verdict(db, check) is None


async def test_partial_check_recommends_a_continuation(client, consolidation_db, test_suite_agent):
    db, failed, _ = consolidation_db
    failed = await _known_failure(db, failed)
    db.add(AgentDemand(subject="Checagem", body="d", failure_check_source_id=failed.id, dispatch_status="completed",
                       dispatch_result="ORIGEM: BLOQUEADA\nSTATUS: DONE", **_common(test_suite_agent)))
    await db.commit()
    brief = (await client.get(f"/api/v1/demands/{failed.id}/brief")).json()
    assert brief["stuck"]["reason"] == "failure_unresolved"
    assert brief["options"][0] == {"action": "continue", "recommended": True}
    assert [n["role"] for n in brief["thread"]] == ["original", "check"]
    assert brief["thread"][1]["verdict"] == "blocked"


async def test_an_agent_continuation_links_and_closes_its_own_failure(consolidation_db, test_suite_agent):
    from app.api.routes.demand import create_demand_and_notify
    from app.api.schemas.demand import DemandSubmitIn
    db, failed, _ = consolidation_db
    failed = await _known_failure(db, failed)
    number = failed.number
    # The bridge token alone (no agent credential) only links: the sender id in
    # the body proves nothing (independent review #3).
    linked = await create_demand_and_notify(db, DemandSubmitIn(
        from_agent="test-suite", from_agent_id=test_suite_agent, target_agent_id=test_suite_agent,
        subject="Só liga", body="b", origin_type="task", continues_number=number))
    assert linked.continues_id == failed.id
    await db.refresh(failed)
    assert failed.status != "archived"
    sent = await create_demand_and_notify(db, DemandSubmitIn(
        from_agent="test-suite", from_agent_id=test_suite_agent, target_agent_id=test_suite_agent,
        subject="Só o que faltou", body="b", origin_type="task", continues_number=number),
        continuation_closer_id=test_suite_agent)
    assert sent.continues_id == failed.id
    await db.refresh(failed)
    source = failed
    assert source.status == "archived" and source.decision_reason == f"Continuada por #{sent.number}"

    with pytest.raises(Exception):
        await create_demand_and_notify(db, DemandSubmitIn(
            from_agent="test-suite", from_agent_id=test_suite_agent, subject="x", body="b",
            origin_type="task", continues_number=10 ** 9))
    await db.rollback()


# ---- phase 3: "já foi feito em outro lugar?" ----

@pytest.fixture(autouse=True)
def _analysis_on(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "MESSAGE_ANALYSIS_ON_DEMAND_ENABLED", True)

def _reply(**data):
    return json.dumps(data, ensure_ascii=False)


async def _candidate(db, failed, agent, result):
    other = AgentDemand(subject="Outra tarefa", body="publicar a migração", dispatch_status="completed",
                        dispatch_result=result, context_area=failed.context_area,
                        task_execution_at=datetime.now(timezone.utc), **_common(agent))
    db.add(other)
    await db.commit()
    return other


async def test_elsewhere_without_candidates_answers_without_the_model(client, consolidation_db, monkeypatch):
    from app.core import forgerouter_llm

    async def boom(*args, **kwargs):
        raise AssertionError("model must not be called")
    monkeypatch.setattr(forgerouter_llm, "chat", boom)
    db, failed, _ = consolidation_db
    failed = await _known_failure(db, failed)
    response = await client.post(f"/api/v1/demands/{failed.id}/brief/elsewhere")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "not_found" and response.json()["candidates"] == []


async def test_elsewhere_match_needs_a_verbatim_quote(client, consolidation_db, test_suite_agent, monkeypatch):
    from app.core import forgerouter_llm
    db, failed, _ = consolidation_db
    failed = await _known_failure(db, failed)
    other = await _candidate(db, failed, test_suite_agent, "Migração publicada em produção no commit abc1234.\nSTATUS: DONE")
    replies = iter([
        _reply(status="done_elsewhere", summary="Feito", matches=[{"id": str(other.id), "quote": "texto inventado que não existe no resultado", "explains": "x"}]),
        _reply(status="done_elsewhere", summary="Feito na outra", matches=[{"id": str(other.id), "quote": "Migração publicada em produção no commit abc1234", "explains": "publicou"}]),
    ])

    async def chat(*args, **kwargs):
        return next(replies)
    monkeypatch.setattr(forgerouter_llm, "chat", chat)

    invented = (await client.post(f"/api/v1/demands/{failed.id}/brief/elsewhere")).json()
    assert invented["status"] == "not_found" and invented["matches"] == []
    assert [c["number"] for c in invented["candidates"]] == [other.number]

    proven = (await client.post(f"/api/v1/demands/{failed.id}/brief/elsewhere")).json()
    assert proven["status"] == "done_elsewhere" and proven["matches"][0]["number"] == other.number
    brief = (await client.get(f"/api/v1/demands/{failed.id}/brief")).json()
    assert brief["elsewhere"]["stale"] is False
    assert brief["options"][0] == {"action": "done_by", "recommended": True}


async def test_elsewhere_survives_model_failure_and_goes_stale_on_change(client, consolidation_db, test_suite_agent, monkeypatch):
    from app.core import forgerouter_llm
    db, failed, _ = consolidation_db
    failed = await _known_failure(db, failed)
    other = await _candidate(db, failed, test_suite_agent, "algo\nSTATUS: DONE")

    async def down(*args, **kwargs):
        raise forgerouter_llm.LlmError("failed", "ForgeRouter unreachable: secret text")
    monkeypatch.setattr(forgerouter_llm, "chat", down)
    result = (await client.post(f"/api/v1/demands/{failed.id}/brief/elsewhere")).json()
    assert result["status"] == "unavailable" and "secret" not in result["summary"]
    assert [c["number"] for c in result["candidates"]] == [other.number]

    failed.body = "Pedido alterado"
    await db.commit()
    assert (await client.get(f"/api/v1/demands/{failed.id}/brief")).json()["elsewhere"]["stale"] is True


async def test_a_finished_check_closes_its_original_through_the_runner_path(consolidation_db, test_suite_agent):
    """The real terminal transition calls the verdict, not only the helper."""
    from app.api.routes import demand as demand_routes
    db, failed, _ = consolidation_db
    failed = await _known_failure(db, failed)
    run_id = str(uuid.uuid4())
    check = AgentDemand(subject="Checagem", body="d", failure_check_source_id=failed.id, dispatch_status="running",
                        agent_run_id=run_id, **_common(test_suite_agent))
    db.add(check)
    await db.commit()
    run = {"run_id": run_id, "status": "completed", "output": "Verifiquei.\nORIGEM: CONCLUIDA\nSTATUS: DONE"}
    await demand_routes._finalize_dispatch(db, check.id, run, expected_run_id=run_id)
    await db.commit()
    await db.refresh(failed)
    assert failed.status == "archived"
    assert failed.decision_reason == f"Checagem #{check.number}: ORIGEM CONCLUÍDA"


async def test_restricted_flows_never_become_an_ordinary_task(client, consolidation_db):
    """Independent review #1: group/STI/personal work keeps its restricted path."""
    db, failed, _ = consolidation_db
    failed = await _known_failure(db, failed)
    failed.channel = "whatsapp_group"
    await db.commit()
    await db.refresh(failed)
    response = await _decide(client, failed, action="continue", reason="x")
    assert response.status_code == 409
    brief = (await client.get(f"/api/v1/demands/{failed.id}/brief")).json()
    assert brief["blocked"]["continue"] == "private_flow"
    failed.channel, failed.context_area = "agent", "sti_approval:x:1"
    await db.commit()
    await db.refresh(failed)
    assert (await _decide(client, failed, action="close_delivered", reason="x", evidence_ref="git:a")).status_code == 409


async def test_private_tasks_never_reach_the_model(client, consolidation_db, test_suite_agent, monkeypatch):
    """Independent review #2: a mention of #N doesn't carry a private task along."""
    from app.core import forgerouter_llm
    db, failed, _ = consolidation_db
    failed = await _known_failure(db, failed)
    db.add_all([
        AgentDemand(subject=f"WhatsApp cita #{failed.number}", body="cliente", channel="whatsapp_group", dispatch_status="completed",
                    dispatch_result="dados do cliente", **_common(test_suite_agent)),
        AgentDemand(subject="Grupo", body=f"#{failed.number}", context_area="instructor:abc:open", dispatch_status="completed",
                    dispatch_result="aluno", **_common(test_suite_agent)),
    ])
    await db.commit()

    async def boom(*args, **kwargs):
        raise AssertionError("no candidate should reach the model")
    monkeypatch.setattr(forgerouter_llm, "chat", boom)
    result = (await client.post(f"/api/v1/demands/{failed.id}/brief/elsewhere")).json()
    assert result["status"] == "not_found" and result["candidates"] == []


async def test_a_quote_from_the_body_is_not_evidence(client, consolidation_db, test_suite_agent, monkeypatch):
    from app.core import forgerouter_llm
    db, failed, _ = consolidation_db
    failed = await _known_failure(db, failed)
    other = await _candidate(db, failed, test_suite_agent, "nada feito ainda\nSTATUS: DONE")
    quote = "publicar a migração"  # the other task's body (a request), padded below to 20+ chars
    other.body = "Pedido: publicar a migração em produção hoje à noite"
    await db.commit()

    async def chat(*args, **kwargs):
        return _reply(status="done_elsewhere", summary="x", matches=[{"id": str(other.id), "quote": "publicar a migração em produção hoje", "explains": quote}])
    monkeypatch.setattr(forgerouter_llm, "chat", chat)
    result = (await client.post(f"/api/v1/demands/{failed.id}/brief/elsewhere")).json()
    assert result["status"] == "not_found" and result["matches"] == []


async def test_a_stale_answer_no_longer_recommends(client, consolidation_db, test_suite_agent, monkeypatch):
    from app.core import forgerouter_llm
    db, failed, _ = consolidation_db
    failed = await _known_failure(db, failed)
    other = await _candidate(db, failed, test_suite_agent, "Migração publicada em produção no commit abc1234.")

    async def chat(*args, **kwargs):
        return _reply(status="done_elsewhere", summary="x", matches=[{"id": str(other.id), "quote": "Migração publicada em produção no commit abc1234", "explains": "y"}])
    monkeypatch.setattr(forgerouter_llm, "chat", chat)
    await client.post(f"/api/v1/demands/{failed.id}/brief/elsewhere")
    await db.refresh(failed)
    failed.body = "Outro pedido"
    await db.commit()
    brief = (await client.get(f"/api/v1/demands/{failed.id}/brief")).json()
    assert brief["elsewhere"]["stale"] is True
    assert brief["options"][0]["action"] != "done_by"


async def test_an_echoed_template_line_is_not_a_verdict(consolidation_db, test_suite_agent):
    from app.core.demand_brief import origin_verdict
    from app.core.demand_continuity import apply_origin_verdict
    from app.core.message_triage import verified_delivery
    assert origin_verdict("ORIGEM: CONCLUIDA | PARCIAL | BLOQUEADA (escolha uma opção).") is None
    assert origin_verdict("ORIGEM: CONCLUIDA | PARCIAL\n**ORIGEM: PARCIAL**") == "partial"
    assert origin_verdict("ORIGEM: PARCIAL\nORIGEM: CONCLUÍDA.") == "completed"
    db, failed, _ = consolidation_db
    failed = await _known_failure(db, failed)
    check = AgentDemand(subject="Checagem", body="d", failure_check_source_id=failed.id, dispatch_status="completed",
                        dispatch_result="ORIGEM: CONCLUIDA\nSTATUS: DONE", **_common(test_suite_agent))
    db.add(check)
    await db.commit()
    await apply_origin_verdict(db, check)
    await db.commit()
    event = await verified_delivery(db, failed)
    assert event is not None and event.payload["evidence_ref"] == f"message:{check.id}"

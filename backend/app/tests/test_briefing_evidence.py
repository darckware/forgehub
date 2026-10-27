"""A green/yellow report cannot replace a recorded corrective action."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.briefing_evidence import (
    BRIEFING_TITLE,
    briefing_failure_reason,
    missing_briefing_actions,
)


def task(number, **overrides):
    data = dict(id=str(number), number=number, from_agent_id="athos", target_agent_id="aegis",
                origin_type="task", status="new", dispatch_status=None,
                created_at=datetime(2026, 10, 25, tzinfo=timezone.utc),
                subject="Investigar segurança", body="Tratar falha #41555")
    data.update(overrides)
    return SimpleNamespace(**data)


@pytest.mark.parametrize("report", [
    "Saúde: verde. Nada a fazer.\nSTATUS: DONE",
    "Saúde: amarelo. #41555 failed; investigar amanhã.\nSTATUS: DONE",
    "Briefing enviado como #41558.\nSTATUS: DONE",
    "ACTION: #41555 -> #99999\nSTATUS: DONE",
])
def test_briefing_requires_real_followup_not_color_or_promise(report):
    briefing = task(41557, target_agent_id="athos")
    assert missing_briefing_actions([task(41555)], [], report, briefing) == [41555]


def test_real_followup_covers_only_the_failure_it_references():
    briefing = task(41557, target_agent_id="athos")
    followup = task(41600)
    report = "ACTION: #41555 -> #41600\nSTATUS: DONE"
    assert missing_briefing_actions([task(41555)], [followup], report, briefing) == []
    assert missing_briefing_actions([task(41555), task(41553)], [followup], report, briefing) == [41553]


def test_action_line_accepts_owner_and_deadline_details():
    report = 'ACTION: #41555 -> #41600 | responsável: Aegis; ação: corrigir; prazo: hoje'
    assert missing_briefing_actions(
        [task(41555)], [task(41600)], report, task(41557, target_agent_id='athos'),
    ) == []


def test_existing_corrective_task_can_be_authored_by_another_agent():
    assert missing_briefing_actions(
        [task(41555)], [task(41600, from_agent_id='hephaestus')],
        'ACTION: #41555 -> #41600', task(41557, target_agent_id='athos'),
    ) == []


@pytest.mark.parametrize("override", [
    {"status": "archived"}, {"dispatch_status": "failed"}, {"origin_type": "incubation"},
    {"from_agent_id": None}, {"target_agent_id": None}, {"body": "Tratar #415550"},
    {"subject": "Briefing matinal", "target_agent_id": "athos"},
])
def test_notification_archived_failed_or_self_briefing_is_not_action(override):
    assert missing_briefing_actions(
        [task(41555)], [task(41600, **override)], "ACTION: #41555 -> #41600",
        task(41557, target_agent_id="athos"),
    ) == [41555]


async def test_completion_gate_reads_actual_routine_failures_and_tasks():
    db = SimpleNamespace(
        scalar=AsyncMock(return_value="run"),
        scalars=AsyncMock(side_effect=[
            SimpleNamespace(all=lambda: [task(41555), task(41553)]),
            SimpleNamespace(all=lambda: [task(41558, subject="Briefing matinal")]),
        ]),
    )
    briefing = task(41557, target_agent_id="athos", subject=f"[Rotina] {BRIEFING_TITLE}")
    reason = await briefing_failure_reason(db, briefing, "Saúde amarelo.\nSTATUS: DONE")
    assert "#41555" in reason and "#41553" in reason


async def test_unrelated_message_does_not_query_briefing_state():
    assert await briefing_failure_reason(None, task(42), "STATUS: DONE") is None


async def test_scheduled_briefing_without_failures_can_complete():
    db = SimpleNamespace(scalar=AsyncMock(return_value="run"),
                         scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [])))
    briefing = task(41557, target_agent_id="athos", subject=f"[Rotina] {BRIEFING_TITLE}")
    assert await briefing_failure_reason(db, briefing, "STATUS: DONE") is None


async def test_done_dispatch_must_pass_briefing_gate(monkeypatch):
    from app.api.routes.demand import _finalize_dispatch
    from app.core import briefing_evidence

    briefing = task(41557, target_agent_id="athos", subject=f"[Rotina] {BRIEFING_TITLE}",
                    consolidated_into_id=None, agent_run_id="runner", dispatch_status="running")
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: briefing)))
    gate = AsyncMock(side_effect=RuntimeError("briefing gate reached"))
    monkeypatch.setattr(briefing_evidence, "briefing_failure_reason", gate)
    with pytest.raises(RuntimeError, match="briefing gate reached"):
        await _finalize_dispatch(db, briefing.id, {"status": "completed", "output": "STATUS: DONE"})
    gate.assert_awaited_once_with(db, briefing, "STATUS: DONE")
    assert briefing.dispatch_status == "running"


def test_generated_briefing_carries_action_and_delivery_contract():
    from app.api.routes.operations import compose_routine_message

    routine = SimpleNamespace(title=BRIEFING_TITLE, timezone="America/Sao_Paulo", deadline_minutes=60,
                              kind="report", instructions="Envie o briefing", expected_evidence="Texto enviado",
                              linked_audit_checks=[])
    body = compose_routine_message(routine, SimpleNamespace(name="Athos"),
                                   datetime(2026, 10, 25, tzinfo=timezone.utc), None, None)
    assert "ACTION: #origem -> #tratamento" in body
    assert "dispatch_error e dispatch_result" in body
    assert "não comprova entrega no Telegram" in body

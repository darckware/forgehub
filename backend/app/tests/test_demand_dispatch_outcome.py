"""ECO-054 5a/5b (2026-11-16, Marcelo): an attempt that stops asking for his
authorization goes to Aprovação, and one that only waits for a person's reply
is "aguardando resposta" -- neither is a failed dispatch."""
import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.api.routes.demand import _finalize_dispatch
from app.api.schemas.demand import DemandDecisionIn
from app.core.completion_report import COMPLETION_CONTRACT, blocked_outcome, parse_completion_report
from app.core.demand_management import work_state_sql
from app.core.demand_thread import build_thread_prompt
from app.core.demand_workflow import WorkflowBlocked, assert_execution_allowed, decide_demand
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent
from app.db.models.notification import Notification


@pytest.mark.parametrize("text, expected", [
    ("STATUS: BLOCKED | AUTORIZAÇÃO: rodar a migração em produção", ("awaiting_authorization", "rodar a migração em produção")),
    ("**STATUS: BLOCKED** | autorizacao: rotacionar a chave", ("awaiting_authorization", "rotacionar a chave")),
    ("STATUS: BLOCKED — AUTORIZAÇÃO: decidir o escopo", ("awaiting_authorization", "decidir o escopo")),
    ("STATUS: BLOCKED | AGUARDANDO RESPOSTA: data de nascimento, do instrutor", ("waiting_reply", "data de nascimento, do instrutor")),
    # A blocker without the label stays a failure; prose never counts.
    ("STATUS: BLOCKED | Moodle timeout", None),
    ("STATUS: BLOCKED | precisa de autorização do Marcelo", None),
    ("STATUS: PARTIAL | AUTORIZAÇÃO: x", None),
    ("STATUS: DONE | AGUARDANDO RESPOSTA: x", None),
    ("STATUS: BLOCKED | AUTORIZAÇÃO:", None),
    # The contract's own model lines, echoed, ask for nothing.
    ("STATUS: BLOCKED | AUTORIZAÇÃO: <o que ele precisa autorizar ou decidir>", None),
])
def test_blocked_outcome(text, expected):
    assert blocked_outcome(*parse_completion_report(text)) == expected


def test_the_contract_explains_both_labels():
    assert "STATUS: BLOCKED | AUTORIZAÇÃO:" in COMPLETION_CONTRACT
    assert "STATUS: BLOCKED | AGUARDANDO RESPOSTA:" in COMPLETION_CONTRACT
    assert parse_completion_report(COMPLETION_CONTRACT) == (None, None)


@pytest_asyncio.fixture
async def agents():
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        sender = Agent(name=f"Outcome Sender {suffix}", agent_type="executor", runtime_type="claude")
        executor = Agent(name=f"Outcome Executor {suffix}", agent_type="executor", runtime_type="claude")
        session.add_all([sender, executor])
        await session.commit()
        ids = (sender.id, executor.id)
    yield ids
    async with AsyncSessionLocal() as session:
        demand_ids = (await session.scalars(select(AgentDemand.id).where(
            AgentDemand.target_agent_id.in_(ids) | AgentDemand.from_agent_id.in_(ids)))).all()
        for demand_id in demand_ids:
            for prefix in ("demand-dispatch-failed", "demand-authorization"):
                await session.execute(delete(Notification).where(Notification.event_key.like(f"{prefix}:{demand_id}:%")))
            await session.execute(delete(AuditEvent).where(AuditEvent.entity_id == demand_id))
        await session.execute(delete(AgentDemand).where(AgentDemand.failure_check_source_id.in_(demand_ids)))
        await session.execute(delete(AgentDemand).where(AgentDemand.reply_to_id.in_(demand_ids)))
        await session.execute(delete(AgentDemand).where(AgentDemand.id.in_(demand_ids)))
        await session.execute(delete(Agent).where(Agent.id.in_(ids)))
        await session.commit()


async def _dispatched(sender_id, executor_id, *, working_path="/srv/forgehub-test/outcome") -> uuid.UUID:
    async with AsyncSessionLocal() as session:
        demand = AgentDemand(
            from_agent="sender", from_agent_id=sender_id, target_agent_id=executor_id,
            subject="outcome contract", body="corrija o ECO-060", origin_type="task",
            working_path=working_path, dispatch_status="dispatched", dispatch_attempts=1,
            agent_run_id=f"run-{uuid.uuid4().hex[:12]}",
        )
        session.add(demand)
        await session.commit()
        return demand.id


async def _finalize(demand_id, output: str):
    async with AsyncSessionLocal() as session:
        row = await session.get(AgentDemand, demand_id)
        reply = await _finalize_dispatch(session, demand_id, {"status": "completed", "output": output},
                                         expected_run_id=row.agent_run_id)
        await session.commit()
    async with AsyncSessionLocal() as session:
        return reply, await session.get(AgentDemand, demand_id)


async def _state(demand_id) -> str:
    async with AsyncSessionLocal() as session:
        return await session.scalar(select(work_state_sql()).where(AgentDemand.id == demand_id))


async def test_authorization_request_goes_to_approval_not_failure(agents):
    demand_id = await _dispatched(*agents)
    reply, demand = await _finalize(demand_id, "Não posso rotacionar sozinho.\nSTATUS: BLOCKED | AUTORIZAÇÃO: rotacionar a chave do srv-app02")
    assert reply is None
    assert demand.dispatch_status is None and demand.dispatch_error is None
    assert demand.agent_run_id is None and demand.scheduled_at is None
    assert (demand.requires_approval, demand.approval_status) == (True, "pending")
    assert (demand.dispatch_outcome, demand.outcome_note) == ("awaiting_authorization", "rotacionar a chave do srv-app02")
    assert "Status: aguardando autorização" in demand.dispatch_result
    assert await _state(demand_id) == "approval"
    with pytest.raises(WorkflowBlocked):
        assert_execution_allowed(demand)  # nothing runs before he decides
    async with AsyncSessionLocal() as session:
        events = (await session.scalars(select(AuditEvent.event_type).where(AuditEvent.entity_id == demand_id))).all()
        notified = await session.scalar(select(Notification.title).where(
            Notification.event_key == f"demand-authorization:{demand_id}:1"))
    assert "demand_attempt_finished" in events
    assert notified.startswith("Autorização pedida")
    # A second finalizer for the same, already-ended run changes nothing.
    async with AsyncSessionLocal() as session:
        assert await _finalize_dispatch(session, demand_id, {"status": "completed", "output": "STATUS: DONE"}) is None
        await session.rollback()


async def test_approval_reruns_with_the_authorization_in_the_prompt(agents):
    demand_id = await _dispatched(*agents)
    await _finalize(demand_id, "STATUS: BLOCKED | AUTORIZAÇÃO: rotacionar a chave")
    async with AsyncSessionLocal() as session:
        demand = await session.get(AgentDemand, demand_id)
        with patch("app.core.dispatch_signal.wake_scheduled_dispatch"):
            await decide_demand(session, demand, DemandDecisionIn(action="approve", reason="pode rotacionar hoje"), actor="admin.teste")
    async with AsyncSessionLocal() as session:
        demand = await session.get(AgentDemand, demand_id)
    assert demand.dispatch_outcome == "authorized" and demand.scheduled_at is not None
    assert_execution_allowed(demand)
    prompt = build_thread_prompt(demand, None)
    assert prompt.startswith("corrija o ECO-060")
    assert "rotacionar a chave" in prompt and "pode rotacionar hoje" in prompt
    # The re-run that finishes clears the outcome.
    async with AsyncSessionLocal() as session:
        row = await session.get(AgentDemand, demand_id)
        row.dispatch_status, row.agent_run_id = "dispatched", "run-second"
        await session.commit()
    _, demand = await _finalize(demand_id, "Rotacionada.\nSTATUS: DONE")
    assert demand.dispatch_status == "completed" and demand.dispatch_outcome is None


async def test_rejection_marks_the_request_refused(agents):
    demand_id = await _dispatched(*agents)
    await _finalize(demand_id, "STATUS: BLOCKED | AUTORIZAÇÃO: apagar o volume")
    async with AsyncSessionLocal() as session:
        demand = await session.get(AgentDemand, demand_id)
        await decide_demand(session, demand, DemandDecisionIn(action="reject", reason="não apague"), actor="admin.teste")
    async with AsyncSessionLocal() as session:
        demand = await session.get(AgentDemand, demand_id)
    assert (demand.approval_status, demand.dispatch_outcome) == ("rejected", "authorization_refused")
    assert demand.scheduled_at is None


async def test_without_a_working_directory_it_stays_a_failure(agents):
    """Approval re-runs the message, which needs an absolute working directory."""
    demand_id = await _dispatched(*agents, working_path=None)
    _, demand = await _finalize(demand_id, "STATUS: BLOCKED | AUTORIZAÇÃO: x")
    assert demand.dispatch_status == "failed" and demand.dispatch_outcome is None


async def test_waiting_for_a_reply_is_not_a_failure(agents):
    demand_id = await _dispatched(*agents)
    _, demand = await _finalize(demand_id, "Perguntei ao instrutor.\nSTATUS: BLOCKED | AGUARDANDO RESPOSTA: data de nascimento do aluno")
    assert demand.dispatch_status == "completed" and demand.dispatch_error is None
    assert (demand.dispatch_outcome, demand.outcome_note) == ("waiting_reply", "data de nascimento do aluno")
    assert await _state(demand_id) == "waiting"


async def test_an_unlabelled_blocker_still_fails(agents):
    demand_id = await _dispatched(*agents)
    _, demand = await _finalize(demand_id, "STATUS: BLOCKED | Moodle fora do ar")
    assert demand.dispatch_status == "failed" and demand.dispatch_outcome is None

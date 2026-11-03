"""A cleanly-exited run is completed work only when the agent ends with
STATUS: DONE (2026-10-24) -- see core/completion_report.py."""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.api.routes.demand import _finalize_dispatch
from app.core.completion_report import (
    COMPLETION_CONTRACT,
    completion_failure_reason,
    parse_completion_status,
    with_completion_contract,
)
from app.core.demand_workflow import requires_reconciliation
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand
from app.db.models.notification import Notification


@pytest.mark.parametrize("text, expected", [
    ("Feito.\nSTATUS: DONE", "DONE"),
    ("Feito.\n**STATUS: DONE**\n", "DONE"),
    ("- `STATUS: partial`", "PARTIAL"),
    ("STATUS: BLOCKED.", "BLOCKED"),
    ("STATUS: PARTIAL\ncorrigido depois\nSTATUS: DONE", "DONE"),
    ("Now let me run the tests:", None),
    ("I will print STATUS: DONE when tests pass", None),
    ("", None),
])
def test_parse_completion_status(text, expected):
    assert parse_completion_status(text) == expected


def test_contract_follows_the_prompt():
    assert with_completion_contract("faça X").startswith("faça X\n\n")
    assert with_completion_contract("faça X").endswith(COMPLETION_CONTRACT)


def test_only_done_has_no_failure_reason():
    assert completion_failure_reason("DONE") is None
    assert "PARTIAL" in completion_failure_reason("PARTIAL")
    assert "completion report" in completion_failure_reason(None)


@pytest_asyncio.fixture
async def agents():
    """(sender, executor) -- distinct registered agents."""
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        sender = Agent(name=f"Report Sender {suffix}", agent_type="executor", runtime_type="claude")
        executor = Agent(name=f"Report Executor {suffix}", agent_type="executor", runtime_type="claude")
        session.add_all([sender, executor])
        await session.commit()
        ids = (sender.id, executor.id)
    yield ids
    async with AsyncSessionLocal() as session:
        demand_ids = (await session.scalars(select(AgentDemand.id).where(
            AgentDemand.target_agent_id.in_(ids) | AgentDemand.from_agent_id.in_(ids)))).all()
        for demand_id in demand_ids:
            await session.execute(delete(Notification).where(
                Notification.event_key.like(f"demand-dispatch-failed:{demand_id}:%")))
        await session.execute(delete(AgentDemand).where(AgentDemand.reply_to_id.in_(demand_ids)))
        await session.execute(delete(AgentDemand).where(AgentDemand.id.in_(demand_ids)))
        await session.execute(delete(Agent).where(Agent.id.in_(ids)))
        await session.commit()


async def _dispatched(sender_id, executor_id) -> uuid.UUID:
    async with AsyncSessionLocal() as session:
        demand = AgentDemand(
            from_agent="sender",
            from_agent_id=sender_id,
            target_agent_id=executor_id,
            subject="report contract",
            body="do the thing",
            origin_type="task",
            requires_response=True,
            dispatch_status="dispatched",
            dispatch_attempts=1,
        )
        session.add(demand)
        await session.commit()
        return demand.id


async def _finalize(demand_id, output: str):
    async with AsyncSessionLocal() as session:
        reply = await _finalize_dispatch(session, demand_id, {"status": "completed", "output": output})
        await session.commit()
    async with AsyncSessionLocal() as session:
        return reply, await session.get(AgentDemand, demand_id)


async def test_done_is_completed(agents):
    demand_id = await _dispatched(*agents)
    reply, demand = await _finalize(demand_id, "Arquivo criado, testes ok.\nSTATUS: DONE")
    assert demand.dispatch_status == "completed"
    assert demand.dispatch_error is None
    assert reply is not None  # requires_response still creates the return


@pytest.mark.parametrize("output, reason", [
    ("Metade feita, falta o deploy.\nSTATUS: PARTIAL", "STATUS: PARTIAL"),
    ("Sem acesso ao banco.\nSTATUS: BLOCKED", "STATUS: BLOCKED"),
    ("Now let me run the tests:", "without the completion report"),
])
async def test_anything_but_done_is_failed_and_keeps_the_result(agents, output, reason):
    demand_id = await _dispatched(*agents)
    reply, demand = await _finalize(demand_id, output)
    assert demand.dispatch_status == "failed"
    assert reason in demand.dispatch_error
    assert output in demand.dispatch_result
    assert reply is None  # no return message for unfinished work
    assert not requires_reconciliation(demand)  # a known failure: reprocess stays available
    async with AsyncSessionLocal() as session:
        notice = await session.scalar(select(Notification.id).where(
            Notification.event_key == f"demand-dispatch-failed:{demand_id}:1"))
    assert notice is not None

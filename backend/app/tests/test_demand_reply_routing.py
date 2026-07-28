"""A dispatch's outcome always lands on the SAME message as
`dispatch_result` -- "processamento", not a new message (2026-07-28,
Marcelo: "não temos resposta automática. somente processamento" +
"gravado na própria mensagem"). A real return message is only created when
the original explicitly asked for one (`requires_response=true`), reverting
2026-07-27's "every reply routes back regardless of requires_response" to a
conditional creation instead of just conditional routing (Marcelo: "preciso
gerar... uma mensagem de retorno quando solicitado pelo agente... e o
padrão é não").

The return message itself: Tipo=task (Marcelo: "Tipo=task" -- "demand" no
longer exists as a value), from/target swapped (executor -> sender),
requires_response=False (no reply loop), reply_to_id pointing back at the
original, already dispatch_status="completed" (it's already-done work, and
needs to read as *arrived* for the "letter model" gate -- see
pages/demands/index.tsx's isIncomingItem).
"""
import uuid

import pytest_asyncio
from sqlalchemy import delete

from app.api.routes.demand import _finalize_dispatch
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand


@pytest_asyncio.fixture
async def agents():
    """(sender, executor) -- distinct registered agents."""
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        sender = Agent(name=f"Reply Sender {suffix}", agent_type="executor", runtime_type="claude")
        executor = Agent(name=f"Reply Executor {suffix}", agent_type="executor", runtime_type="claude")
        session.add_all([sender, executor])
        await session.commit()
        await session.refresh(sender)
        await session.refresh(executor)
        ids = (sender.id, executor.id)
    yield ids
    async with AsyncSessionLocal() as session:
        await session.execute(delete(AgentDemand).where(AgentDemand.target_agent_id.in_(ids)))
        await session.execute(delete(AgentDemand).where(AgentDemand.from_agent_id.in_(ids)))
        await session.execute(delete(Agent).where(Agent.id.in_(ids)))
        await session.commit()


async def _create_dispatched(sender_id, executor_id, *, requires_response: bool) -> uuid.UUID:
    async with AsyncSessionLocal() as session:
        demand = AgentDemand(
            from_agent="sender",
            from_agent_id=sender_id,
            target_agent_id=executor_id,
            subject="original",
            body="do the thing",
            origin_type="task",
            requires_response=requires_response,
            dispatch_status="dispatched",
        )
        session.add(demand)
        await session.commit()
        await session.refresh(demand)
        return demand.id


async def test_requires_response_true_creates_return_message(agents):
    sender_id, executor_id = agents
    demand_id = await _create_dispatched(sender_id, executor_id, requires_response=True)

    async with AsyncSessionLocal() as session:
        reply = await _finalize_dispatch(session, demand_id, {"status": "completed", "output": "done"})
        await session.commit()

    assert reply is not None
    assert reply.target_agent_id == sender_id
    assert reply.from_agent_id == executor_id
    assert reply.origin_type == "task"
    assert reply.reply_to_id == demand_id
    assert reply.requires_response is False
    assert reply.dispatch_status == "completed"
    # body carries the canonical Data/Agente/Ticket/Assunto/Status header
    # (2026-07-28) ahead of the agent's raw output -- see
    # _format_execution_header's docstring.
    assert reply.body.endswith("\n---\ndone")
    assert "Status: completed" in reply.body

    async with AsyncSessionLocal() as session:
        original = await session.get(AgentDemand, demand_id)
        assert original.dispatch_result.endswith("\n---\ndone")
        assert "Status: completed" in original.dispatch_result


async def test_requires_response_false_only_records_result_no_new_message(agents):
    """The default -- "só processamento": the run's output lands on the
    original message, no second row is created at all."""
    sender_id, executor_id = agents
    demand_id = await _create_dispatched(sender_id, executor_id, requires_response=False)

    async with AsyncSessionLocal() as session:
        reply = await _finalize_dispatch(session, demand_id, {"status": "completed", "output": "done"})
        await session.commit()

    assert reply is None

    async with AsyncSessionLocal() as session:
        original = await session.get(AgentDemand, demand_id)
        assert original.dispatch_result.endswith("\n---\ndone")
        assert original.dispatch_status == "completed"


async def test_requires_response_true_with_no_known_sender_still_only_records_result(agents):
    """Nothing to route a return message back to -- from_agent_id is None
    (a human/unregistered sender) -- so no return message is created even
    though requires_response was true; the result still lands on the
    original message."""
    _, executor_id = agents
    async with AsyncSessionLocal() as session:
        demand = AgentDemand(
            from_agent="marcelo",
            from_agent_id=None,
            target_agent_id=executor_id,
            subject="original",
            body="do the thing",
            origin_type="task",
            requires_response=True,
            dispatch_status="dispatched",
        )
        session.add(demand)
        await session.commit()
        await session.refresh(demand)
        demand_id = demand.id

    async with AsyncSessionLocal() as session:
        reply = await _finalize_dispatch(session, demand_id, {"status": "completed", "output": "done"})
        await session.commit()

    assert reply is None

    async with AsyncSessionLocal() as session:
        original = await session.get(AgentDemand, demand_id)
        assert original.dispatch_result.endswith("\n---\ndone")

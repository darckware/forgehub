"""A Tipo=Task message always has an agent to run it -- and when it doesn't,
it is silently downgraded to Backlog rather than rejected (2026-07-27,
Marcelo: "toda task chegando em Incoming precisa ser executada pelo seu
agente" -- then, refining the first cut which returned 400 -- "não seria
melhor sem agente ficar no backlog... para não ser executado").

Two mechanisms, both covered here:
  - `_reconcile_task_origin` reclassifies any create/update that would leave
    a Task message with no target_agent_id as Backlog instead (origin_id
    cleared too -- Backlog never carries one).
  - Task + target + never dispatched + never scheduled gets scheduled_at
    auto-set to now, so the background loop actually runs it instead of it
    sitting inert in Incoming forever.
"""
import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand


@pytest_asyncio.fixture
async def client():
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {create_access_token('test-task-target')}"},
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def agent_id():
    async with AsyncSessionLocal() as session:
        agent = Agent(
            name=f"Task Target Agent {uuid.uuid4().hex[:8]}",
            agent_type="executor", runtime_type="claude",
        )
        session.add(agent)
        await session.commit()
        await session.refresh(agent)
        aid = agent.id
    yield aid
    async with AsyncSessionLocal() as session:
        await session.execute(delete(AgentDemand).where(AgentDemand.target_agent_id == aid))
        await session.execute(delete(Agent).where(Agent.id == aid))
        await session.commit()


@pytest_asyncio.fixture
async def sender_agent_id():
    """A real registered agent to act as From -- Task requires one now too
    (2026-07-28, Marcelo: "Preciso ter agente (from) no tipo task. Isso é
    regra"), distinct from `agent_id` (the target) so tests exercise the
    ordinary two-different-agents case."""
    async with AsyncSessionLocal() as session:
        agent = Agent(
            name=f"Task Sender Agent {uuid.uuid4().hex[:8]}",
            agent_type="executor", runtime_type="claude",
        )
        session.add(agent)
        await session.commit()
        await session.refresh(agent)
        aid = agent.id
    yield aid
    async with AsyncSessionLocal() as session:
        await session.execute(delete(AgentDemand).where(AgentDemand.from_agent_id == aid))
        await session.execute(delete(Agent).where(Agent.id == aid))
        await session.commit()


async def test_create_task_without_target_is_downgraded_to_backlog(client: AsyncClient):
    """Not rejected, not lost -- lands as Backlog, same as filing one directly."""
    response = await client.post(
        "/api/v1/demands",
        json={"from_agent": "marcelo", "subject": "task sem agente", "body": "x", "origin_type": "task"},
    )
    assert response.status_code == 201, response.text
    demand = response.json()
    assert demand["origin_type"] == "backlog"
    assert demand["origin_id"] is None
    assert demand["target_agent_id"] is None
    assert demand["scheduled_at"] is None  # never auto-scheduled once it's Backlog
    await client.delete(f"/api/v1/demands/{demand['id']}")


async def test_create_task_with_target_stays_task_and_auto_schedules_now(
    client: AsyncClient, agent_id, sender_agent_id
):
    response = await client.post(
        "/api/v1/demands",
        json={
            "from_agent": "marcelo", "from_agent_id": str(sender_agent_id),
            "subject": "task com agente", "body": "x",
            "origin_type": "task", "target_agent_id": str(agent_id),
        },
    )
    assert response.status_code == 201, response.text
    demand = response.json()
    assert demand["origin_type"] == "task"
    assert demand["scheduled_at"] is not None
    await client.delete(f"/api/v1/demands/{demand['id']}")


async def test_create_task_with_target_but_no_sender_is_downgraded_to_backlog(
    client: AsyncClient, agent_id
):
    """The other half of the same rule (2026-07-28, Marcelo: "se o agente
    não tem (to), não tem retorno. Preciso ter agente (from) no tipo task.
    Isso é regra"): a target with no *registered* sender is just as inert
    as no target at all -- "marcelo" here never resolves to an Agent."""
    response = await client.post(
        "/api/v1/demands",
        json={
            "from_agent": "marcelo", "subject": "task sem remetente registrado", "body": "x",
            "origin_type": "task", "target_agent_id": str(agent_id),
        },
    )
    assert response.status_code == 201, response.text
    demand = response.json()
    assert demand["origin_type"] == "backlog"
    # target_agent_id itself is untouched by the downgrade -- only
    # origin_type/origin_id are reconciled; Backlog can carry a target, it
    # just isn't required (see test_create_backlog_without_target_is_unaffected
    # for the "never had one" case).
    assert demand["target_agent_id"] == str(agent_id)
    assert demand["scheduled_at"] is None
    await client.delete(f"/api/v1/demands/{demand['id']}")


async def test_create_backlog_without_target_is_unaffected(client: AsyncClient):
    """The ordinary case, untouched by the reconciliation."""
    response = await client.post(
        "/api/v1/demands",
        json={"from_agent": "marcelo", "subject": "backlog sem agente", "body": "x", "origin_type": "backlog"},
    )
    assert response.status_code == 201, response.text
    demand = response.json()
    assert demand["target_agent_id"] is None
    assert demand["scheduled_at"] is None
    await client.delete(f"/api/v1/demands/{demand['id']}")


async def test_promoting_backlog_to_task_without_target_stays_backlog(client: AsyncClient):
    """The reading pane's "Promover a Task" flips origin_type via this same
    PATCH -- an orphan Backlog item (no To, no From-as-agent) must not slip
    through as an inert Task, but the PATCH itself still succeeds."""
    create = await client.post(
        "/api/v1/demands",
        json={"from_agent": "marcelo", "subject": "orfao", "body": "x", "origin_type": "backlog"},
    )
    demand_id = create.json()["id"]
    try:
        response = await client.patch(f"/api/v1/demands/{demand_id}", json={"origin_type": "task"})
        assert response.status_code == 200, response.text
        assert response.json()["origin_type"] == "backlog"
    finally:
        await client.delete(f"/api/v1/demands/{demand_id}")


async def test_promoting_backlog_to_task_with_target_schedules_it(
    client: AsyncClient, agent_id, sender_agent_id
):
    create = await client.post(
        "/api/v1/demands",
        json={
            "from_agent": "marcelo", "from_agent_id": str(sender_agent_id),
            "subject": "promovivel", "body": "x", "origin_type": "backlog",
        },
    )
    demand_id = create.json()["id"]
    try:
        response = await client.patch(
            f"/api/v1/demands/{demand_id}",
            json={"origin_type": "task", "target_agent_id": str(agent_id)},
        )
        assert response.status_code == 200, response.text
        demand = response.json()
        assert demand["origin_type"] == "task"
        assert demand["target_agent_id"] == str(agent_id)
        assert demand["scheduled_at"] is not None
    finally:
        await client.delete(f"/api/v1/demands/{demand_id}")


async def test_clearing_target_on_a_task_downgrades_it_to_backlog(
    client: AsyncClient, agent_id, sender_agent_id
):
    """The invariant holds both ways: a Task edited back into having no
    agent becomes Backlog instead of an inert, unrunnable Task."""
    create = await client.post(
        "/api/v1/demands",
        json={
            "from_agent": "marcelo", "from_agent_id": str(sender_agent_id),
            "subject": "task existente", "body": "x",
            "origin_type": "task", "target_agent_id": str(agent_id),
        },
    )
    demand_id = create.json()["id"]
    try:
        response = await client.patch(f"/api/v1/demands/{demand_id}", json={"target_agent_id": None})
        assert response.status_code == 200, response.text
        assert response.json()["origin_type"] == "backlog"
    finally:
        await client.delete(f"/api/v1/demands/{demand_id}")


async def test_clearing_from_agent_on_a_task_downgrades_it_to_backlog(
    client: AsyncClient, agent_id, sender_agent_id
):
    """The other agent, same invariant (2026-07-28, Marcelo: "Preciso ter
    agente (from) no tipo task. Isso é regra") -- clearing From on an
    already-Task message downgrades it exactly like clearing To does."""
    create = await client.post(
        "/api/v1/demands",
        json={
            "from_agent": "marcelo", "from_agent_id": str(sender_agent_id),
            "subject": "task existente", "body": "x",
            "origin_type": "task", "target_agent_id": str(agent_id),
        },
    )
    demand_id = create.json()["id"]
    try:
        response = await client.patch(f"/api/v1/demands/{demand_id}", json={"from_agent_id": None})
        assert response.status_code == 200, response.text
        assert response.json()["origin_type"] == "backlog"
    finally:
        await client.delete(f"/api/v1/demands/{demand_id}")


async def test_editing_an_already_scheduled_task_does_not_reschedule(
    client: AsyncClient, agent_id, sender_agent_id
):
    """Auto-schedule only fires once (scheduled_at was NULL); a later,
    unrelated edit must not touch an already-set Send-at."""
    create = await client.post(
        "/api/v1/demands",
        json={
            "from_agent": "marcelo", "from_agent_id": str(sender_agent_id),
            "subject": "task agendada", "body": "x",
            "origin_type": "task", "target_agent_id": str(agent_id),
        },
    )
    demand_id = create.json()["id"]
    original_scheduled_at = create.json()["scheduled_at"]
    assert original_scheduled_at is not None
    try:
        response = await client.patch(f"/api/v1/demands/{demand_id}", json={"subject": "renomeada"})
        assert response.status_code == 200, response.text
        assert response.json()["scheduled_at"] == original_scheduled_at
    finally:
        await client.delete(f"/api/v1/demands/{demand_id}")


async def test_omitted_type_defaults_to_backlog_and_needs_no_agent(client: AsyncClient):
    """No Tipo given at all -- the mandatory-field default (2026-07-28) is
    Backlog, same as filing one explicitly."""
    response = await client.post(
        "/api/v1/demands",
        json={"from_agent": "marcelo", "subject": "sem tipo", "body": "x"},
    )
    assert response.status_code == 201, response.text
    demand = response.json()
    assert demand["origin_type"] == "backlog"
    assert demand["target_agent_id"] is None
    await client.delete(f"/api/v1/demands/{demand['id']}")


async def test_demand_type_is_rejected_at_submission(client: AsyncClient):
    """"demand" was retired as a Tipo value (2026-07-28) -- it only ever
    exists on a backend-generated return message, never something a caller
    submits directly."""
    response = await client.post(
        "/api/v1/demands",
        json={"from_agent": "marcelo", "subject": "tipo invalido", "body": "x", "origin_type": "demand"},
    )
    assert response.status_code == 422, response.text


def test_reconcile_clears_origin_id_on_downgrade_no_target():
    """origin_id must never survive onto Backlog -- it's a classification,
    not a polymorphic link (AgentDemand.origin_id's docstring). Unit-level:
    `_reconcile_task_origin` is a pure function, no need for a real linked
    ProjectTask row to prove it drops origin_id alongside the type."""
    from app.api.routes.demand import _reconcile_task_origin

    linked_id = uuid.uuid4()
    from_id = uuid.uuid4()
    origin_type, origin_id = _reconcile_task_origin(
        "task", linked_id, target_agent_id=None, from_agent_id=from_id
    )
    assert origin_type == "backlog"
    assert origin_id is None


def test_reconcile_clears_origin_id_on_downgrade_no_sender():
    """Same downgrade, missing the *other* agent (2026-07-28, Marcelo:
    "Preciso ter agente (from) no tipo task. Isso é regra") -- a Task
    addressed to someone but from nobody known is just as inert as one
    with no target at all."""
    from app.api.routes.demand import _reconcile_task_origin

    linked_id = uuid.uuid4()
    target_id = uuid.uuid4()
    origin_type, origin_id = _reconcile_task_origin(
        "task", linked_id, target_agent_id=target_id, from_agent_id=None
    )
    assert origin_type == "backlog"
    assert origin_id is None


def test_reconcile_leaves_a_targeted_task_with_sender_untouched():
    from app.api.routes.demand import _reconcile_task_origin

    linked_id = uuid.uuid4()
    target_id = uuid.uuid4()
    from_id = uuid.uuid4()
    origin_type, origin_id = _reconcile_task_origin(
        "task", linked_id, target_agent_id=target_id, from_agent_id=from_id
    )
    assert origin_type == "task"
    assert origin_id == linked_id


def test_reconcile_leaves_backlog_untouched():
    from app.api.routes.demand import _reconcile_task_origin

    origin_type, origin_id = _reconcile_task_origin(
        "backlog", None, target_agent_id=None, from_agent_id=None
    )
    assert origin_type == "backlog"
    assert origin_id is None


def test_reconcile_defaults_missing_type_to_backlog():
    """No Tipo given at all is the mandatory-field default case
    (2026-07-28) -- never left as None."""
    from app.api.routes.demand import _reconcile_task_origin

    origin_type, origin_id = _reconcile_task_origin(
        None, None, target_agent_id=None, from_agent_id=None
    )
    assert origin_type == "backlog"
    assert origin_id is None

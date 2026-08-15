"""Tests for the Software Factory cockpit aggregation
(GET /api/v1/factory/cockpit -- app/api/routes/factory.py).

DB strategy matches the rest of the suite: each test creates its own rows
(UUID-suffixed names) against the real company_postgres DB and removes them
in a finally block. There is no transaction rollback/isolation here, so the
assertions only ever look at the rows this test created -- the cockpit
returns every project in the database, so filtering by our own ids is what
keeps the test independent of whatever else lives in the DB.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.backlog import PlanningItem
from app.db.models.demand import AgentDemand
from app.db.models.product import Product, ProductVersion
from app.db.models.project import Project
from app.db.models.system_scope import ProductConcept
from app.db.models.task import ProjectTask, TaskAssignment, TaskExecution


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('test-factory-cockpit')}"}


@pytest_asyncio.fixture
async def client():
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=_auth_headers()) as ac:
        yield ac


@pytest_asyncio.fixture
async def factory_fixture():
    """One product -> version -> project -> planning item -> 2 tasks.

    Mirrors the real chain the cockpit walks: Product -> Project ->
    Planning -> Task, with the concept recorded at product level.
    """
    suffix = uuid.uuid4().hex[:8]
    created: dict = {}
    async with AsyncSessionLocal() as db:
        product = Product(name=f"cockpit-test-{suffix}", status="active")
        db.add(product)
        await db.flush()

        concept = ProductConcept(product_id=product.id, status="approved")
        version = ProductVersion(product_id=product.id, version="0.1.0", status="in_development")
        db.add_all([concept, version])
        await db.flush()

        project = Project(
            name=f"cockpit-project-{suffix}",
            description="Evolução de teste",
            product_version_id=version.id,
            status="active",
        )
        db.add(project)
        await db.flush()

        planning = PlanningItem(
            title=f"cockpit-planning-{suffix}",
            item_type="feature",
            project_id=project.id,
            status="in_progress",
        )
        db.add(planning)
        await db.flush()

        tasks = [
            ProjectTask(title=f"t1-{suffix}", planning_item_id=planning.id, status="done"),
            ProjectTask(title=f"t2-{suffix}", planning_item_id=planning.id, status="in_progress"),
        ]
        db.add_all(tasks)
        await db.commit()

        created = {
            "product_id": product.id,
            "version_id": version.id,
            "project_id": project.id,
            "planning_id": planning.id,
        }

    try:
        yield created
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(
                delete(ProjectTask).where(ProjectTask.planning_item_id == created["planning_id"])
            )
            await db.execute(delete(PlanningItem).where(PlanningItem.id == created["planning_id"]))
            await db.execute(delete(Project).where(Project.id == created["project_id"]))
            await db.execute(
                delete(ProductConcept).where(ProductConcept.product_id == created["product_id"])
            )
            await db.execute(delete(ProductVersion).where(ProductVersion.id == created["version_id"]))
            await db.execute(delete(Product).where(Product.id == created["product_id"]))
            await db.commit()


@pytest_asyncio.fixture
async def telemetry_fixture(factory_fixture):
    """One agent with a mix of TaskExecution outcomes + one AgentDemand
    dispatch, attached to factory_fixture's "done" task -- covers
    agent-telemetry's join chain (TaskExecution -> TaskAssignment -> Agent)
    end to end. There is no ORM relationship for this chain (see
    app/db/models/task.py), so the fixture wires it exactly the way the
    real dispatch path does: an assignment row, then executions against it.
    """
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        agent = Agent(name=f"telemetry-agent-{suffix}", agent_type="executor")
        db.add(agent)
        await db.flush()

        task = (
            await db.execute(
                select(ProjectTask).where(
                    ProjectTask.planning_item_id == factory_fixture["planning_id"],
                    ProjectTask.status == "done",
                ).limit(1)
            )
        ).scalar_one()

        assignment = TaskAssignment(task_id=task.id, agent_id=agent.id, status="active")
        db.add(assignment)
        await db.flush()

        now = datetime.now(timezone.utc)
        executions = [
            TaskExecution(
                task_id=task.id, assignment_id=assignment.id, attempt_number=1,
                status="completed", started_at=now - timedelta(minutes=5),
                finished_at=now - timedelta(minutes=4), actual_cost=1.50, evidence_ref="ok",
            ),
            TaskExecution(
                task_id=task.id, assignment_id=assignment.id, attempt_number=2,
                status="failed", actual_cost=0.75,
            ),
            TaskExecution(
                task_id=task.id, assignment_id=assignment.id, attempt_number=3,
                status="running", actual_cost=0.25,
            ),
        ]
        db.add_all(executions)

        demand = AgentDemand(
            from_agent="tester", subject="dispatch", body="dispatch body",
            target_agent_id=agent.id, origin_type="task", dispatch_status="completed",
        )
        db.add(demand)
        await db.commit()

        created = {
            "agent_id": agent.id,
            "assignment_id": assignment.id,
            "task_id": task.id,
            "demand_id": demand.id,
        }

    try:
        yield created
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(TaskExecution).where(TaskExecution.assignment_id == created["assignment_id"]))
            await db.execute(delete(TaskAssignment).where(TaskAssignment.id == created["assignment_id"]))
            await db.execute(delete(AgentDemand).where(AgentDemand.id == created["demand_id"]))
            await db.execute(delete(Agent).where(Agent.id == created["agent_id"]))
            await db.commit()


@pytest.mark.asyncio
async def test_agent_telemetry_aggregates_executions_and_dispatch(client, factory_fixture, telemetry_fixture):
    resp = await client.get("/api/v1/factory/agent-telemetry")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    row = next(
        (a for a in body["agents"] if a["agent_id"] == str(telemetry_fixture["agent_id"])), None
    )
    assert row is not None, "o agente criado não apareceu na telemetria"

    assert row["executions_total"] == 3
    assert row["executions_successful"] == 1
    assert row["executions_failed"] == 1
    assert row["executions_other"] == 1
    assert row["success_rate"] == pytest.approx(0.5)
    # Só a execução "completed" tem started_at/finished_at -- 60s de duração.
    assert row["avg_duration_seconds"] == pytest.approx(60.0)
    assert row["total_cost"] == pytest.approx(2.5)

    assert row["dispatch_total"] == 1
    assert row["dispatch_completed"] == 1
    assert row["dispatch_failed"] == 0
    assert row["dispatch_success_rate"] == pytest.approx(1.0)

    today = datetime.now(timezone.utc).date().isoformat()
    history_today = next((h for h in row["history"] if h["date"] == today), None)
    assert history_today is not None, "o dia de hoje não apareceu no histórico"
    assert history_today["count"] == 3


@pytest.mark.asyncio
async def test_agent_telemetry_omits_agents_with_no_activity():
    """Um agente sem nenhuma execução/despacho não deve aparecer na lista --
    não é uma linha zerada fictícia, é ausência real."""
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        agent = Agent(name=f"idle-agent-{suffix}", agent_type="executor")
        db.add(agent)
        await db.commit()
        agent_id = agent.id

    try:
        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=_auth_headers()
        ) as ac:
            resp = await ac.get("/api/v1/factory/agent-telemetry")
        assert resp.status_code == 200, resp.text
        ids = {a["agent_id"] for a in resp.json()["agents"]}
        assert str(agent_id) not in ids
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Agent).where(Agent.id == agent_id))
            await db.commit()


@pytest.mark.asyncio
async def test_cockpit_reports_total_cost_for_a_project(client, factory_fixture, telemetry_fixture):
    resp = await client.get("/api/v1/factory/cockpit")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    product = next(p for p in body["products"] if p["product_id"] == str(factory_fixture["product_id"]))
    row = next(r for r in product["projects"] if r["project_id"] == str(factory_fixture["project_id"]))
    assert row["total_cost"] == pytest.approx(2.5)


@pytest.mark.asyncio
async def test_cockpit_reports_five_phases_for_a_project(client, factory_fixture):
    resp = await client.get("/api/v1/factory/cockpit")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    product = next(
        (p for p in body["products"] if p["product_id"] == str(factory_fixture["product_id"])),
        None,
    )
    assert product is not None, "o produto criado não apareceu no cockpit"
    assert product["product_name"].startswith("cockpit-test-")
    # O produto traz a própria versão, para o cadastro caber nesta tela.
    assert [v["version_number"] for v in product["versions"]] == ["0.1.0"]
    assert product["concept_status"] == "approved"

    row = next(
        (r for r in product["projects"] if r["project_id"] == str(factory_fixture["project_id"])),
        None,
    )
    assert row is not None, "o projeto criado não apareceu sob o produto"

    assert [p["key"] for p in row["phases"]] == [
        "conception",
        "designer",
        "procedures",
        "execution",
        "quality",
    ]

    phases = {p["key"]: p for p in row["phases"]}

    # Fase 1 vem do ProductConcept do produto (approved).
    assert phases["conception"]["state"] == "approved"
    assert phases["conception"]["detail"] == "approved"

    # Fase 2 sem blueprint nem escopo = pendente, nunca "aprovado por omissão".
    assert phases["designer"]["state"] == "pending"

    # Fase 3 conta grupos de planejamento: 1 total, 0 concluídos.
    assert phases["procedures"]["total"] == 1
    assert phases["procedures"]["done"] == 0
    assert phases["procedures"]["state"] == "in_progress"

    # Fase 4 conta tarefas através do planning item: 2 total, 1 done.
    assert phases["execution"]["total"] == 2
    assert phases["execution"]["done"] == 1
    assert phases["execution"]["state"] == "in_progress"

    # Fase 5 deriva do status da versão (in_development -> ainda pendente).
    assert phases["quality"]["state"] == "pending"

    assert row["planning_count"] == 1
    assert row["task_count"] == 2
    assert row["version_number"] == "0.1.0"

    # 2026-08-15: every project reports its creation/maintenance
    # classification (server_default -- always set, even for a project
    # created with no explicit project_type like this fixture's) and, when
    # none exists yet, a null pipeline.
    assert row["project_type"] == "creation"
    assert row["pipeline_name"] is None
    assert row["pipeline_template_name"] is None


@pytest.mark.asyncio
async def test_cockpit_reports_project_type_and_active_pipeline(client, factory_fixture):
    """2026-08-15: the Cockpit surfaces which development path a project is
    actually on -- its creation/maintenance classification and its active
    ProjectPipeline's name + the PipelineTemplate it was instantiated from,
    since the Pipelines page isn't reachable from the sidebar today."""
    from app.db.models.pipeline import PipelineTemplate, ProjectPipeline

    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        project = await db.get(Project, factory_fixture["project_id"])
        project.project_type = "maintenance"
        template = PipelineTemplate(name=f"cockpit-template-{suffix}")
        db.add(template)
        await db.flush()
        pipeline = ProjectPipeline(
            project_id=project.id, template_id=template.id, name=f"cockpit-pipeline-{suffix}",
        )
        db.add(pipeline)
        await db.commit()
        template_id, pipeline_id = template.id, pipeline.id

    try:
        resp = await client.get("/api/v1/factory/cockpit")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        product = next(p for p in body["products"] if p["product_id"] == str(factory_fixture["product_id"]))
        row = next(r for r in product["projects"] if r["project_id"] == str(factory_fixture["project_id"]))

        assert row["project_type"] == "maintenance"
        assert row["pipeline_name"] == f"cockpit-pipeline-{suffix}"
        assert row["pipeline_template_name"] == f"cockpit-template-{suffix}"
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(ProjectPipeline).where(ProjectPipeline.id == pipeline_id))
            await db.execute(delete(PipelineTemplate).where(PipelineTemplate.id == template_id))
            await db.commit()


@pytest.mark.asyncio
async def test_cockpit_requires_auth():
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/v1/factory/cockpit")
    assert resp.status_code == 401


# --------------------------------------------------------------------------
# Task dispatch pelo processo de mensagens (POST /tasks/{id}/dispatch)
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_dispatch_task_requires_an_assignment(client, factory_fixture):
    """Sem atribuição ativa e sem target_agent_id explícito não há para quem
    despachar -- falha antes de qualquer chamada ao host-bridge."""
    async with AsyncSessionLocal() as db:
        task = (
            await db.execute(
                select(ProjectTask).where(
                    ProjectTask.planning_item_id == factory_fixture["planning_id"],
                    ProjectTask.status == "in_progress",
                ).limit(1)
            )
        ).scalar_one()
        task_id = task.id

    resp = await client.post(f"/api/v1/tasks/{task_id}/dispatch", json={})
    assert resp.status_code == 400
    assert "assignment" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_dispatch_rejects_a_closed_task(client, factory_fixture):
    """Uma task já concluída não volta para a fila de execução."""
    async with AsyncSessionLocal() as db:
        task = (
            await db.execute(
                select(ProjectTask).where(
                    ProjectTask.planning_item_id == factory_fixture["planning_id"],
                    ProjectTask.status == "done",
                ).limit(1)
            )
        ).scalar_one()
        task_id = task.id

    resp = await client.post(f"/api/v1/tasks/{task_id}/dispatch", json={})
    assert resp.status_code == 422
    assert "done" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_cockpit_lists_a_product_with_no_project():
    """Um produto recém-cadastrado, sem versão usada por nenhum projeto,
    continua aparecendo -- o Cockpit substituiu a tela de Produtos, então o
    que ele omitir fica inalcançável, não só fora de uma lista."""
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        product = Product(name=f"cockpit-lonely-{suffix}", status="active")
        db.add(product)
        await db.flush()
        version = ProductVersion(product_id=product.id, version="0.1.0", status="planned")
        db.add(version)
        await db.commit()
        product_id, version_id = product.id, version.id

    try:
        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=_auth_headers()
        ) as ac:
            resp = await ac.get("/api/v1/factory/cockpit")
        assert resp.status_code == 200, resp.text

        row = next(
            (p for p in resp.json()["products"] if p["product_id"] == str(product_id)), None
        )
        assert row is not None
        assert row["projects"] == []
        assert [v["version_number"] for v in row["versions"]] == ["0.1.0"]
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(ProductVersion).where(ProductVersion.id == version_id))
            await db.execute(delete(Product).where(Product.id == product_id))
            await db.commit()

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

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.backlog import PlanningItem
from app.db.models.product import Product, ProductVersion
from app.db.models.project import Project
from app.db.models.system_scope import ProductConcept
from app.db.models.task import ProjectTask


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

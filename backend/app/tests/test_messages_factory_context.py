import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.security import create_access_token, hash_password
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand
from app.db.models.product import Product, ProductVersion
from app.db.models.project import Project
from app.db.models.system_scope import DevelopmentRequest
from app.db.models.user import User
from app.main import app


@pytest_asyncio.fixture
async def factory_message_world():
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        agent = Agent(
            name=f"Factory context agent {suffix}",
            profile_slug=f"factory-context-{suffix}",
            agent_type="executor",
            runtime_type="codex",
        )
        product = Product(name=f"Factory context product {suffix}")
        other_product = Product(name=f"Other factory product {suffix}")
        user = User(
            username=f"factory-context-{suffix}",
            hashed_password=hash_password("test"),
            is_admin=True,
        )
        db.add_all([agent, product, other_product, user])
        await db.flush()
        request = DevelopmentRequest(
            product_id=product.id,
            title=f"Factory request {suffix}",
            description="Canonical pre-project context",
        )
        version = ProductVersion(product_id=product.id, version=f"0.0.{suffix}")
        other_version = ProductVersion(product_id=other_product.id, version=f"0.1.{suffix}")
        db.add_all([request, version, other_version])
        await db.flush()
        project = Project(name=f"Factory project {suffix}", product_version_id=version.id)
        other_project_row = Project(
            name=f"Other factory project {suffix}",
            product_version_id=other_version.id,
        )
        db.add_all([project, other_project_row])
        await db.commit()
        ids = {
            "agent": agent.id,
            "product": product.id,
            "other_product": other_product.id,
            "request": request.id,
            "version": version.id,
            "other_version": other_version.id,
            "project": project.id,
            "other_project": other_project_row.id,
            "username": user.username,
            "user": user.id,
        }

    yield ids

    async with AsyncSessionLocal() as db:
        await db.execute(delete(AgentDemand).where(AgentDemand.from_agent_id == ids["agent"]))
        await db.execute(delete(Project).where(Project.id.in_([ids["project"], ids["other_project"]])))
        await db.execute(delete(DevelopmentRequest).where(DevelopmentRequest.id == ids["request"]))
        await db.execute(delete(ProductVersion).where(ProductVersion.id.in_([ids["version"], ids["other_version"]])))
        await db.execute(delete(Product).where(Product.id.in_([ids["product"], ids["other_product"]])))
        await db.execute(delete(Agent).where(Agent.id == ids["agent"]))
        await db.execute(delete(User).where(User.id == ids["user"]))
        await db.commit()


@pytest_asyncio.fixture
async def factory_message_client(factory_message_world):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "Authorization": f"Bearer {create_access_token(factory_message_world['username'])}"
        },
    ) as client:
        yield client


async def test_message_factory_context_is_preserved_in_agent_activity(
    factory_message_client: AsyncClient,
    factory_message_world,
):
    world = factory_message_world
    created = await factory_message_client.post(
        "/api/v1/demands",
        json={
            "from_agent": "factory-context-test",
            "from_agent_id": str(world["agent"]),
            "subject": "Conceive and deliver",
            "body": "Keep the canonical factory context attached.",
            "origin_type": "incubation",
            "development_request_id": str(world["request"]),
            "project_id": str(world["project"]),
        },
    )
    assert created.status_code == 201, created.text
    message = created.json()
    assert message["development_request_id"] == str(world["request"])
    assert message["project_id"] == str(world["project"])

    activity = await factory_message_client.get("/api/v1/agent-activity")
    assert activity.status_code == 200, activity.text
    edge = next(item for item in activity.json()["message_edges"] if item["message_id"] == message["id"])
    assert edge["development_request_id"] == str(world["request"])
    assert edge["product_id"] == str(world["product"])
    assert edge["factory_context_path"] == f"/conception?request={world['request']}"


async def test_message_rejects_project_from_another_product(
    factory_message_client: AsyncClient,
    factory_message_world,
):
    world = factory_message_world
    response = await factory_message_client.post(
        "/api/v1/demands",
        json={
            "from_agent": "factory-context-test",
            "from_agent_id": str(world["agent"]),
            "subject": "Invalid mixed context",
            "body": "This must not cross product boundaries.",
            "origin_type": "incubation",
            "development_request_id": str(world["request"]),
            "project_id": str(world["other_project"]),
        },
    )
    assert response.status_code == 409, response.text
    assert "same product" in response.json()["detail"]

"""Catalog classification and context recommendation behavior."""
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest_asyncio.fixture
async def client(auth_headers):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=auth_headers
    ) as test_client:
        yield test_client


async def test_prompt_technique_catalog_is_classified(client: AsyncClient):
    response = await client.get("/api/v1/prompt-techniques")
    assert response.status_code == 200
    rows = response.json()
    codes = {row["code"] for row in rows}
    categories = {row["category"] for row in rows}

    assert {"software_implementation", "gauntlet_loop", "image_generation", "video_generation"} <= codes
    assert {
        "software", "agentic", "content", "marketing", "social_media", "soft_skills",
        "agent_skills",
        "design", "automation", "image", "video",
    } <= categories
    assert all(row["summary"] and row["when_to_use"] for row in rows)
    assert all("instruction_template" not in row for row in rows)


async def test_prompt_technique_catalog_filters_category(client: AsyncClient):
    response = await client.get("/api/v1/prompt-techniques", params={"category": "image"})
    assert response.status_code == 200
    rows = response.json()
    assert rows
    assert all(row["category"] == "image" for row in rows)


async def test_prompt_technique_recommendation_uses_draft_context(client: AsyncClient):
    response = await client.post(
        "/api/v1/prompt-techniques/recommend",
        json={"draft": "Preciso criar uma imagem de produto com iluminação de estúdio"},
    )
    assert response.status_code == 200
    recommendations = response.json()
    assert recommendations[0]["technique_code"] == "image_generation"
    assert recommendations[0]["matched_terms"]


async def test_prompt_technique_recommendation_has_safe_fallback(client: AsyncClient):
    response = await client.post(
        "/api/v1/prompt-techniques/recommend",
        json={"draft": "Por favor ajuste isto"},
    )
    assert response.status_code == 200
    assert response.json()[0]["technique_code"] == "clarity_objectivity"


async def test_prompt_technique_recommends_logo_design(client: AsyncClient):
    response = await client.post(
        "/api/v1/prompt-techniques/recommend",
        json={"draft": "Crie uma logomarca escalável para a marca"},
    )
    assert response.status_code == 200
    assert response.json()[0]["technique_code"] == "logo_design"


async def test_prompt_technique_recommends_workflow_automation(client: AsyncClient):
    response = await client.post(
        "/api/v1/prompt-techniques/recommend",
        json={"draft": "Quero automatizar processo de aprovação e notificações"},
    )
    assert response.status_code == 200
    assert response.json()[0]["technique_code"] == "workflow_automation"


async def test_prompt_technique_recommends_marketing_strategy(client: AsyncClient):
    response = await client.post(
        "/api/v1/prompt-techniques/recommend",
        json={"draft": "Crie uma estratégia de marketing com público, canais e métricas"},
    )
    assert response.status_code == 200
    assert response.json()[0]["technique_code"] == "marketing_strategy"


async def test_prompt_technique_recommends_social_media_post(client: AsyncClient):
    response = await client.post(
        "/api/v1/prompt-techniques/recommend",
        json={"draft": "Crie um post para Instagram com legenda, hashtags e chamada"},
    )
    assert response.status_code == 200
    assert response.json()[0]["technique_code"] == "social_media_post"


async def test_prompt_technique_recommends_conflict_resolution(client: AsyncClient):
    response = await client.post(
        "/api/v1/prompt-techniques/recommend",
        json={"draft": "Ajude a mediar e resolver conflito na equipe"},
    )
    assert response.status_code == 200
    assert response.json()[0]["technique_code"] == "conflict_resolution"


async def test_prompt_technique_recommends_agent_skill_creation(client: AsyncClient):
    response = await client.post(
        "/api/v1/prompt-techniques/recommend",
        json={"draft": "Crie uma nova skill para um agente gerar conteúdo"},
    )
    assert response.status_code == 200
    assert response.json()[0]["technique_code"] == "skill_creation"

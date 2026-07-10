"""Tests for the Agent domain (app/api/routes/agent.py).

Covers: create + get + list for the primary Agent entity, plus business
rule validation cases (skill approval governance, sub-agent skill
inheritance boundary).

DB isolation strategy: this module's own tables (agents, sub_agents,
skills, agent_skills, sub_agent_skills, agent_cost_rates,
agent_capacities) are created directly against the real async engine
(checkfirst=True, scoped to only this domain's Table objects) in a
session-scoped fixture, and every row created by a test is explicitly
deleted in fixture teardown -- this avoids depending on (or racing)
Alembic migration state that other domain agents may be generating
concurrently, while still leaving the shared company_postgres database
clean afterwards. No other domain's tables are touched.
"""
import uuid

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.api.routes import agent as agent_routes
from app.db.base import AsyncSessionLocal, Base, engine
from app.db.models.agent import (
    Agent,
    AgentCapacity,
    AgentCostRate,
    AgentSkill,
    Skill,
    SubAgent,
    SubAgentSkill,
)

_MY_TABLES = [
    Agent.__table__,
    SubAgent.__table__,
    Skill.__table__,
    AgentSkill.__table__,
    SubAgentSkill.__table__,
    AgentCostRate.__table__,
    AgentCapacity.__table__,
]


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _ensure_agent_tables():
    """Create this domain's own tables if they don't already exist yet
    (e.g. when running before the wiring step's migration has been
    applied). Tables are NOT dropped afterwards since other concurrent
    work may depend on them existing; only row-level data is cleaned up
    per-test."""
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn, tables=_MY_TABLES, checkfirst=True
            )
        )
    yield


@pytest_asyncio.fixture
async def client(auth_headers):
    app = FastAPI()
    app.include_router(agent_routes.router)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=auth_headers) as ac:
        yield ac


@pytest_asyncio.fixture
async def cleanup_agent_ids():
    """Yield a list the test appends created Agent ids to; deletes them
    (cascading to sub_agents/agent_skills/cost_rates/capacities) after
    the test runs, regardless of outcome."""
    created_ids: list[uuid.UUID] = []
    yield created_ids
    if created_ids:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Agent).where(Agent.id.in_(created_ids)))
            await db.commit()


@pytest_asyncio.fixture
async def cleanup_skill_ids():
    created_ids: list[uuid.UUID] = []
    yield created_ids
    if created_ids:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Skill).where(Skill.id.in_(created_ids)))
            await db.commit()


def _unique_name(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


@pytest.mark.asyncio
async def test_create_get_list_agent(client, cleanup_agent_ids):
    payload = {
        "name": _unique_name("test-agent"),
        "description": "Created by automated test",
        "agent_type": "executor",
        "status": "active",
    }
    create_resp = await client.post("/api/v1/agents", json=payload)
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    cleanup_agent_ids.append(created["id"])
    assert created["name"] == payload["name"]
    assert created["agent_type"] == "executor"
    assert "id" in created

    get_resp = await client.get(f"/api/v1/agents/{created['id']}")
    assert get_resp.status_code == 200
    detail = get_resp.json()
    assert detail["id"] == created["id"]
    assert detail["sub_agents"] == []
    assert detail["agent_skills"] == []

    list_resp = await client.get("/api/v1/agents")
    assert list_resp.status_code == 200
    listed_ids = {item["id"] for item in list_resp.json()}
    assert created["id"] in listed_ids


@pytest.mark.asyncio
async def test_create_agent_duplicate_name_rejected(client, cleanup_agent_ids):
    name = _unique_name("dup-agent")
    first = await client.post("/api/v1/agents", json={"name": name})
    assert first.status_code == 201
    cleanup_agent_ids.append(first.json()["id"])

    second = await client.post("/api/v1/agents", json={"name": name})
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_create_agent_invalid_status_rejected(client):
    resp = await client.post(
        "/api/v1/agents", json={"name": _unique_name("bad-status"), "status": "bogus"}
    )
    # Pydantic field_validator raises ValueError -> FastAPI returns 422.
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_skill_cannot_self_approve_on_create(client, cleanup_skill_ids):
    """A skill must never be created already approved -- approval is a
    distinct governance action (SPEC 6.5 rule 5/6)."""
    payload = {
        "name": _unique_name("critical-skill"),
        "version": "1.0.0",
        "origin": "internal",
        "risk_level": "critical",
        "permissions": "read:code,write:code",
    }
    resp = await client.post("/api/v1/agents/skills", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    cleanup_skill_ids.append(body["id"])
    assert body["is_approved"] is False


@pytest.mark.asyncio
async def test_third_party_skill_requires_security_review_before_approval(
    client, cleanup_skill_ids
):
    payload = {
        "name": _unique_name("third-party-skill"),
        "version": "1.0.0",
        "origin": "third_party",
        "risk_level": "high",
        "permissions": "read:files",
    }
    create_resp = await client.post("/api/v1/agents/skills", json=payload)
    assert create_resp.status_code == 201
    skill_id = create_resp.json()["id"]
    cleanup_skill_ids.append(skill_id)

    # Attempting to approve without security review must be rejected.
    bad_approve = await client.patch(
        f"/api/v1/agents/skills/{skill_id}", json={"is_approved": True}
    )
    assert bad_approve.status_code == 409

    # Mark security_reviewed first, then approval succeeds.
    review_resp = await client.patch(
        f"/api/v1/agents/skills/{skill_id}", json={"security_reviewed": True}
    )
    assert review_resp.status_code == 200

    approve_resp = await client.patch(
        f"/api/v1/agents/skills/{skill_id}", json={"is_approved": True}
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["is_approved"] is True


@pytest.mark.asyncio
async def test_approved_skill_is_immutable_except_flags(client, cleanup_skill_ids):
    payload = {
        "name": _unique_name("immutable-skill"),
        "version": "1.0.0",
        "origin": "internal",
        "risk_level": "low",
        "permissions": "read:docs",
    }
    create_resp = await client.post("/api/v1/agents/skills", json=payload)
    skill_id = create_resp.json()["id"]
    cleanup_skill_ids.append(skill_id)

    approve_resp = await client.patch(
        f"/api/v1/agents/skills/{skill_id}", json={"is_approved": True}
    )
    assert approve_resp.status_code == 200

    mutate_resp = await client.patch(
        f"/api/v1/agents/skills/{skill_id}", json={"description": "sneaky change"}
    )
    assert mutate_resp.status_code == 409


@pytest.mark.asyncio
async def test_sub_agent_skill_requires_parent_agent_grant(
    client, cleanup_agent_ids, cleanup_skill_ids
):
    """SPEC 6.5 rule 7: a sub-agent may only use skills explicit or
    inherited by permission -- granting a skill to a sub-agent whose
    parent agent does not itself hold that skill must be rejected."""
    agent_resp = await client.post(
        "/api/v1/agents", json={"name": _unique_name("parent-agent")}
    )
    agent_id = agent_resp.json()["id"]
    cleanup_agent_ids.append(agent_id)

    skill_resp = await client.post(
        "/api/v1/agents/skills",
        json={
            "name": _unique_name("ungranted-skill"),
            "version": "1.0.0",
            "origin": "internal",
            "risk_level": "low",
            "permissions": "read:docs",
        },
    )
    skill_id = skill_resp.json()["id"]
    cleanup_skill_ids.append(skill_id)

    sub_agent_resp = await client.post(
        f"/api/v1/agents/{agent_id}/sub-agents", json={"name": _unique_name("sub")}
    )
    assert sub_agent_resp.status_code == 201
    sub_agent_id = sub_agent_resp.json()["id"]

    # Parent agent never granted this skill -> sub-agent grant must fail.
    grant_resp = await client.post(
        f"/api/v1/agents/{agent_id}/sub-agents/{sub_agent_id}/skills",
        json={"skill_id": skill_id},
    )
    assert grant_resp.status_code == 409

    # Granting to the parent agent first makes the sub-agent grant succeed.
    parent_grant_resp = await client.post(
        f"/api/v1/agents/{agent_id}/skills", json={"skill_id": skill_id}
    )
    assert parent_grant_resp.status_code == 201

    grant_resp_2 = await client.post(
        f"/api/v1/agents/{agent_id}/sub-agents/{sub_agent_id}/skills",
        json={"skill_id": skill_id},
    )
    assert grant_resp_2.status_code == 201

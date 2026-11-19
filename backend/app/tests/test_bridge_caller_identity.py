"""MCP split Fase 2a: a bridge-token call that also carries the agent's agt_ credential
may only act as that agent (docs/architecture/MCP_FASE2_AUTHORIZATION_SPEC.md).

The bridge token alone keeps working (2a changes no permission); a valid credential
of another agent, or an invalid credential, is refused.
"""
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent, AgentServiceCredential
from app.db.models.demand import AgentDemand
from app.db.models.operations import AgentQuestion


@pytest_asyncio.fixture
async def client():
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def agents():
    suffix = uuid.uuid4().hex[:8]
    tokens = {name: f"agt_{uuid.uuid4().hex}{uuid.uuid4().hex}" for name in ("alice", "bob", "expired")}
    async with AsyncSessionLocal() as db:
        alice = Agent(name=f"Id Alice {suffix}", agent_type="executor", runtime_type="hermes",
                      profile_slug=f"id-alice-{suffix}")
        bob = Agent(name=f"Id Bob {suffix}", agent_type="executor", runtime_type="hermes",
                    profile_slug=f"id-bob-{suffix}")
        db.add_all([alice, bob])
        await db.flush()
        db.add_all([
            AgentServiceCredential(agent_id=alice.id, label="identity-test",
                                   token_hash=hashlib.sha256(tokens["alice"].encode()).hexdigest()),
            AgentServiceCredential(agent_id=bob.id, label="identity-test",
                                   token_hash=hashlib.sha256(tokens["bob"].encode()).hexdigest()),
            AgentServiceCredential(agent_id=alice.id, label="identity-test-expired",
                                   token_hash=hashlib.sha256(tokens["expired"].encode()).hexdigest(),
                                   expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)),
        ])
        await db.commit()
        data = {"alice": alice.profile_slug, "bob": bob.profile_slug, "ids": [alice.id, bob.id], "tokens": tokens}
    yield data
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AgentDemand).where(AgentDemand.from_agent_id.in_(data["ids"])))
        await db.execute(delete(AgentQuestion).where(AgentQuestion.agent_id.in_(data["ids"])))
        await db.execute(delete(AgentServiceCredential).where(AgentServiceCredential.agent_id.in_(data["ids"])))
        await db.execute(delete(Agent).where(Agent.id.in_(data["ids"])))
        await db.commit()


def _headers(token: str | None = None) -> dict[str, str]:
    headers = {"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN or ""}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _message(sender: str, target: str) -> dict:
    return {"from_agent": sender, "target_agent_slug": target, "subject": "identidade", "body": "teste 2a"}


async def test_bridge_token_alone_still_works(client, agents):
    response = await client.post("/api/v1/demands/submit", json=_message(agents["alice"], agents["bob"]),
                                 headers=_headers())
    assert response.status_code in (200, 201), response.text


async def test_own_credential_may_send_as_itself(client, agents):
    response = await client.post("/api/v1/demands/submit", json=_message(agents["alice"], agents["bob"]),
                                 headers=_headers(agents["tokens"]["alice"]))
    assert response.status_code in (200, 201), response.text


async def test_credential_cannot_send_as_another_agent(client, agents):
    response = await client.post("/api/v1/demands/submit", json=_message(agents["alice"], agents["bob"]),
                                 headers=_headers(agents["tokens"]["bob"]))
    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == "AGENT_IMPERSONATION"


async def test_invalid_or_expired_credential_is_refused(client, agents):
    for token in (agents["tokens"]["expired"], "agt_" + "0" * 64):
        response = await client.post("/api/v1/demands/submit", json=_message(agents["alice"], agents["bob"]),
                                     headers=_headers(token))
        assert response.status_code == 401, response.text
        assert response.json()["detail"]["code"] == "AGENT_CREDENTIAL_INVALID"


async def test_inbox_reads_only_ones_own(client, agents):
    own = await client.get("/api/v1/demands/pending", params={"agent": agents["alice"]},
                           headers=_headers(agents["tokens"]["alice"]))
    assert own.status_code == 200, own.text
    other = await client.get("/api/v1/demands/for-agent", params={"agent": agents["alice"]},
                             headers=_headers(agents["tokens"]["bob"]))
    assert other.status_code == 403, other.text


async def test_questions_only_as_oneself(client, agents):
    asked = await client.post("/api/v1/operations/agent-questions",
                              json={"agent": agents["alice"], "question": "Posso seguir?"},
                              headers=_headers(agents["tokens"]["bob"]))
    assert asked.status_code == 403, asked.text
    listed = await client.get("/api/v1/operations/agent-questions", params={"agent": agents["alice"]},
                              headers=_headers(agents["tokens"]["alice"]))
    assert listed.status_code == 200, listed.text


async def test_edit_and_archive_only_as_oneself(client, agents):
    sent = await client.post("/api/v1/demands/submit", json=_message(agents["alice"], agents["bob"]),
                             headers=_headers(agents["tokens"]["alice"]))
    demand_id = sent.json()["id"]
    edit = await client.patch(f"/api/v1/demands/{demand_id}/agent",
                              json={"agent": agents["alice"], "subject": "outro"},
                              headers=_headers(agents["tokens"]["bob"]))
    assert edit.status_code == 403, edit.text
    archive = await client.post(f"/api/v1/demands/{demand_id}/agent-archive", params={"agent": agents["alice"], "reason": "obsoleta"},
                                headers=_headers(agents["tokens"]["alice"]))
    assert archive.status_code == 200, archive.text


async def test_from_agent_id_cannot_name_another_agent(client, agents):
    """Review F1: /demands/submit uses from_agent_id before the slug."""
    async with AsyncSessionLocal() as db:
        alice = await db.get(Agent, agents["ids"][0])
    body = {**_message(agents["bob"], agents["alice"]), "from_agent_id": str(alice.id)}
    response = await client.post("/api/v1/demands/submit", json=body, headers=_headers(agents["tokens"]["bob"]))
    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == "AGENT_IMPERSONATION"


async def test_only_the_exact_slug_counts(client, agents):
    """Review F4: a name or another case could match here and resolve someone else in the route."""
    for claimed in (agents["alice"].upper(), f"Id Alice {agents['alice'].split('-')[-1]}"):
        response = await client.get("/api/v1/demands/pending", params={"agent": claimed},
                                    headers=_headers(agents["tokens"]["alice"]))
        assert response.status_code == 403, (claimed, response.text)

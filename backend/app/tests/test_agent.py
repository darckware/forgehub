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
from sqlalchemy import delete, select

from app.api.routes import agent as agent_routes
from app.core import agent_telegram
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
from app.db.models.user import User

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


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _ensure_admin_user():
    """GET /{agent_id} is admin-gated (2026-07-29, decrypts
    forgerouter_api_key back into the response) -- auth_headers' JWT
    (conftest.py) is for username "test-suite", so that user needs to
    actually exist with is_admin=True, or get_current_admin 401s/403s.
    Same shared-username convention as test_pipeline.py's fixture; only
    deletes the row afterwards if this fixture is the one that created it,
    in case another concurrently-running test module owns it instead."""
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.username == "test-suite"))).scalar_one_or_none()
        created = user is None
        if created:
            session.add(User(
                username="test-suite", hashed_password="test-only-not-a-real-password",
                is_active=True, is_admin=True,
            ))
            await session.commit()
    yield
    if created:
        async with AsyncSessionLocal() as session:
            user = (await session.execute(select(User).where(User.username == "test-suite"))).scalar_one_or_none()
            if user:
                await session.delete(user)
                await session.commit()


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
async def test_foundation_sync_retires_previously_synced_profile_outside_active_registry(
    client, cleanup_agent_ids, monkeypatch,
):
    suffix = uuid.uuid4().hex[:8]
    stale = Agent(
        name=f"Archived sync agent {suffix}",
        profile_slug=f"archived-sync-{suffix}",
        runtime_type="hermes",
        has_profile=True,
        status="active",
        is_active=True,
    )
    async with AsyncSessionLocal() as db:
        db.add(stale)
        await db.commit()
        await db.refresh(stale)
        cleanup_agent_ids.append(stale.id)

    active_slug = f"active-sync-{suffix}"
    monkeypatch.setattr(agent_routes.hermes_sync, "list_active_provisioned_profiles", lambda: [active_slug])
    monkeypatch.setattr(
        agent_routes.hermes_sync,
        "parse_agent_registry",
        lambda: [{
            "profile_slug": active_slug,
            "name": f"Active sync agent {suffix}",
            "layer": "Governance",
            "telegram_required": False,
            "runtime_tier": "A",
        }],
    )
    monkeypatch.setattr(agent_routes.hermes_sync, "parse_agent_mission", lambda _slug: (None, None))
    monkeypatch.setattr(agent_routes.hermes_sync, "parse_profile_identity", lambda _slug: {})
    monkeypatch.setattr(agent_routes.hermes_sync, "read_profile_forgerouter_api_key", lambda _slug: None)
    monkeypatch.setattr(agent_routes.hermes_sync, "organization_for_profile", lambda _slug: (None, None, None))
    monkeypatch.setattr(agent_routes.hermes_sync, "parse_subagent_catalog", lambda: {})
    monkeypatch.setattr(agent_routes.hermes_sync, "parse_profile_skills", lambda _slug: [])

    response = await client.post("/api/v1/agents/sync/hermes-foundation")

    assert response.status_code == 200, response.text
    async with AsyncSessionLocal() as db:
        active = (
            await db.execute(select(Agent).where(Agent.profile_slug == active_slug))
        ).scalar_one()
        cleanup_agent_ids.append(active.id)
        refreshed_stale = await db.get(Agent, stale.id)
        assert refreshed_stale is not None
        assert refreshed_stale.is_active is False
        assert refreshed_stale.status == "retired"


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


# ---------------------------------------------------------------------------
# Profile files (SOUL.md, IDENTITY.md, ... -- see core/agent_profile_files.py)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_profile_files_use_registered_home_path(client, cleanup_agent_ids, tmp_path):
    """A registered home_path wins over the runtime convention, and the
    listing reports which of the expected files actually exist."""
    (tmp_path / "SOUL.md").write_text("# soul", encoding="utf-8")

    create_resp = await client.post(
        "/api/v1/agents",
        json={"name": _unique_name("test-agent-home"), "agent_type": "executor"},
    )
    assert create_resp.status_code == 201, create_resp.text
    agent_id = create_resp.json()["id"]
    cleanup_agent_ids.append(agent_id)

    patch_resp = await client.patch(
        f"/api/v1/agents/{agent_id}", json={"home_path": str(tmp_path)}
    )
    assert patch_resp.status_code == 200, patch_resp.text
    assert patch_resp.json()["effective_home_path"] == str(tmp_path)

    list_resp = await client.get(f"/api/v1/agents/{agent_id}/profile-files")
    assert list_resp.status_code == 200, list_resp.text
    listing = list_resp.json()
    assert listing["home_resolved"] is True
    by_name = {f["filename"]: f for f in listing["files"]}
    assert by_name["SOUL.md"]["exists"] is True
    assert by_name["IDENTITY.md"]["exists"] is False
    # No profile_slug -> no <PROFILE>_SUBAGENTS.md entry at all.
    assert not any(name.endswith("_SUBAGENTS.md") for name in by_name)

    read_resp = await client.get(f"/api/v1/agents/{agent_id}/profile-files/SOUL.md")
    assert read_resp.status_code == 200
    assert read_resp.json()["content"] == "# soul"

    # A file that does not exist yet reads as null content, not 404 --
    # the editor must be able to create it.
    missing_resp = await client.get(f"/api/v1/agents/{agent_id}/profile-files/IDENTITY.md")
    assert missing_resp.status_code == 200
    assert missing_resp.json()["content"] is None

    write_resp = await client.put(
        f"/api/v1/agents/{agent_id}/profile-files/IDENTITY.md",
        json={"content": "# identity"},
    )
    assert write_resp.status_code == 200, write_resp.text
    assert (tmp_path / "IDENTITY.md").read_text(encoding="utf-8") == "# identity"


@pytest.mark.asyncio
async def test_profile_files_reject_paths_outside_the_allow_list(
    client, cleanup_agent_ids, tmp_path
):
    """`filename` comes straight from the URL, so anything off the
    allow-list -- including traversal -- must 404 rather than read."""
    (tmp_path / "secrets.json").write_text("{}", encoding="utf-8")

    create_resp = await client.post(
        "/api/v1/agents",
        json={"name": _unique_name("test-agent-guard"), "agent_type": "executor"},
    )
    agent_id = create_resp.json()["id"]
    cleanup_agent_ids.append(agent_id)
    await client.patch(f"/api/v1/agents/{agent_id}", json={"home_path": str(tmp_path)})

    for filename in ("secrets.json", "../secrets.json", "..%2F..%2Fetc%2Fpasswd"):
        resp = await client.get(f"/api/v1/agents/{agent_id}/profile-files/{filename}")
        assert resp.status_code == 404, f"{filename} -> {resp.status_code}"

    write_resp = await client.put(
        f"/api/v1/agents/{agent_id}/profile-files/secrets.json",
        json={"content": "pwned"},
    )
    assert write_resp.status_code == 404
    assert (tmp_path / "secrets.json").read_text(encoding="utf-8") == "{}"


@pytest.mark.asyncio
async def test_profile_files_404_when_agent_has_no_directory(client, cleanup_agent_ids):
    """An agent with neither a profile_slug nor a runtime has no profile
    directory -- that is a registration gap, not a server error."""
    create_resp = await client.post(
        "/api/v1/agents",
        json={"name": _unique_name("test-agent-nohome"), "agent_type": "executor"},
    )
    agent_id = create_resp.json()["id"]
    cleanup_agent_ids.append(agent_id)

    list_resp = await client.get(f"/api/v1/agents/{agent_id}/profile-files")
    assert list_resp.status_code == 200
    assert list_resp.json()["home_resolved"] is False
    assert list_resp.json()["home_path"] is None

    read_resp = await client.get(f"/api/v1/agents/{agent_id}/profile-files/SOUL.md")
    assert read_resp.status_code == 404


# ---------------------------------------------------------------------------
# Telegram channel status (see core/agent_telegram.py)
# ---------------------------------------------------------------------------


def test_telegram_gateway_service_only_for_hermes_profiles():
    """The external CLI runtimes carry a profile_slug too -- it is their
    Inbox addressing key, not a directory under /root/.hermes/profiles -- so
    keying the systemd unit off the slug alone invented a
    `hermes-gateway-porthus.service` and reported that non-existent unit as
    down."""
    assert (
        agent_telegram.gateway_service_name("athos", "hermes")
        == "hermes-gateway-athos.service"
    )
    assert agent_telegram.gateway_service_name("porthus", "claude") is None
    assert agent_telegram.gateway_service_name(None, "hermes") is None


def test_telegram_parse_active_services():
    stdout = (
        "Id=hermes-gateway-athos.service\nActiveState=active\n"
        "\n"
        "Id=hermes-gateway-scriba.service\nActiveState=inactive\n"
        "\n"
        "Id=hermes-gateway-atlas.service\nActiveState=active\n"
    )
    assert agent_telegram.parse_active_services(stdout) == {
        "hermes-gateway-athos.service",
        "hermes-gateway-atlas.service",
    }
    assert agent_telegram.parse_active_services("") == set()


def test_telegram_status_reads_env_without_leaking_the_token(tmp_path):
    (tmp_path / ".env").write_text(
        "# comment\n"
        "TELEGRAM_BOT_TOKEN=123456:super-secret\n"
        "TELEGRAM_HOME_CHANNEL=1085550644\n"
        "TELEGRAM_HOME_CHANNEL_NAME=Marcelo\n"
        "OPENAI_API_KEY=must-not-be-read\n",
        encoding="utf-8",
    )
    status = agent_telegram.build_status(
        profile_slug="athos",
        required=True,
        home_path=str(tmp_path),
        runtime_type="hermes",
        active_services={"hermes-gateway-athos.service"},
    )
    assert status.installed is True
    assert status.running is True
    assert status.status == "ok"
    assert status.home_channel_name == "Marcelo"
    # The token is reduced to a boolean and must never reach the response.
    assert "super-secret" not in repr(status)


def test_telegram_config_uses_the_profiles_default_home_when_override_is_empty(
    tmp_path, monkeypatch
):
    """Synced Hermes agents normally leave Agent.home_path NULL."""
    (tmp_path / ".env").write_text(
        "TELEGRAM_BOT_TOKEN=t\nTELEGRAM_HOME_CHANNEL=1085550644\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        agent_telegram,
        "effective_home_path",
        lambda home_path, runtime_type, profile_slug: "/root/.hermes/profiles/atlas",
    )
    monkeypatch.setattr(agent_telegram, "resolve_home_dir", lambda path: tmp_path)

    installed, _ = agent_telegram.read_profile_telegram_config(None, "hermes", "atlas")
    assert installed is True
    assert agent_telegram.read_profile_home_chat(None, "hermes", "atlas") == "1085550644"


def test_telegram_status_states(tmp_path):
    configured = tmp_path / "configured"
    configured.mkdir()
    (configured / ".env").write_text(
        "TELEGRAM_BOT_TOKEN=t\nTELEGRAM_HOME_CHANNEL=1\n", encoding="utf-8"
    )

    # Installed but the gateway is down -- messages silently go nowhere, so
    # this is its own state rather than a generic failure.
    down = agent_telegram.build_status(
        profile_slug="athos",
        required=True,
        home_path=str(configured),
        runtime_type="hermes",
        active_services=set(),
    )
    assert down.status == "not_running"

    # Host-bridge unreachable: "we could not check" must not render as
    # "it is broken".
    unchecked = agent_telegram.build_status(
        profile_slug="athos",
        required=True,
        home_path=str(configured),
        runtime_type="hermes",
        active_services=None,
    )
    assert unchecked.running is None
    assert unchecked.status == "unknown"

    # A required channel with no bot token at all.
    empty = tmp_path / "empty"
    empty.mkdir()
    missing = agent_telegram.build_status(
        profile_slug="athos",
        required=True,
        home_path=str(empty),
        runtime_type="hermes",
        active_services=set(),
    )
    assert missing.status == "not_configured"

    # An external runtime Telegram was never part of.
    external = agent_telegram.build_status(
        profile_slug="porthus",
        required=False,
        home_path=str(empty),
        runtime_type="claude",
        active_services=set(),
    )
    assert external.status == "not_applicable"

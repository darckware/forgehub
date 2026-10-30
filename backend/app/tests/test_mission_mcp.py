"""M0.2a mission MCP: create_internal_project and manage_project_members
(docs/architecture/MCP_MISSION_TOOLS_SPEC.md §0.4, §5.1, §5.2, §9.4).

Runs only against the isolated test database. Each test owns its product,
agents and projects (names start with ``mission-test-`` so test_mission_base's
stale-fixture sweep also catches a killed run) and removes them at the end,
including the receipts its agents wrote.
"""
import hashlib
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

from app.core import command_receipts
from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent, AgentServiceCredential
from app.db.models.command_receipt import AgentCommandReceipt
from app.db.models.governance import AuditEvent, AuthorityDelegation
from app.db.models.mission import ProjectMission
from app.db.models.operations import AgentCharter
from app.db.models.orchestration import ProjectAgentMembership
from app.db.models.product import Product, ProductVersion
from app.db.models.project import Project
from app.db.models.user import User
from app.main import app
from app.mcp import factory_server
from app.tests.test_mission_base import _remove_products

HERMES_NEVER = "Editar código em qualquer repositório (abre Task para Aramis, Dartan ou Porthus)"


class McpWorld:
    def __init__(self, admin_headers: dict[str, str]):
        self.admin = admin_headers
        self.tag = uuid.uuid4().hex[:8]
        self.agent_ids: list[uuid.UUID] = []
        self.user_ids: list[uuid.UUID] = []
        self.product_ids: list[uuid.UUID] = []

    def client(self, headers: dict[str, str] | None = None) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           headers=headers if headers is not None else self.admin)

    async def version(self) -> tuple[uuid.UUID, uuid.UUID]:
        async with AsyncSessionLocal() as db:
            product = Product(name=f"mission-test-mcp-{self.tag}-{uuid.uuid4().hex[:4]}")
            db.add(product)
            await db.flush()
            version = ProductVersion(product_id=product.id, version="1.0")
            db.add(version)
            await db.commit()
            self.product_ids.append(product.id)
            return product.id, version.id

    async def agent(self, label: str, runtime: str | None = "claude", never_does: list[str] | None = None,
                    active: bool = True) -> uuid.UUID:
        async with AsyncSessionLocal() as db:
            agent = Agent(name=f"mission-test-{label}-{self.tag}-{uuid.uuid4().hex[:4]}", runtime_type=runtime,
                          is_active=active, status="active" if active else "inactive")
            db.add(agent)
            await db.flush()
            if never_does is not None:
                db.add(AgentCharter(agent_id=agent.id, mission="test", never_does=never_does))
            await db.commit()
            self.agent_ids.append(agent.id)
            return agent.id

    async def token(self, agent_id: uuid.UUID, actions: list[str] | None = ("mission.manage",),
                    product_id=None, project_id=None) -> str:
        token = f"agt_{uuid.uuid4().hex}{uuid.uuid4().hex}"
        async with AsyncSessionLocal() as db:
            db.add(AgentServiceCredential(agent_id=agent_id, label="mission-mcp-test",
                                          token_hash=hashlib.sha256(token.encode()).hexdigest()))
            if actions:
                grantor = User(username=f"mission-grantor-{uuid.uuid4().hex[:8]}", hashed_password="x", is_admin=True)
                db.add(grantor)
                await db.flush()
                self.user_ids.append(grantor.id)
                now = datetime.now(timezone.utc)
                db.add(AuthorityDelegation(
                    grantor_user_id=grantor.id, grantee_type="agent", grantee_id=agent_id,
                    scope_type="project" if project_id else "product", product_id=product_id,
                    project_id=project_id, allowed_actions=list(actions), max_risk="low",
                    valid_from=now - timedelta(minutes=1), expires_at=now + timedelta(hours=1),
                ))
            await db.commit()
        return token

    @staticmethod
    def bearer(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    async def cleanup(self) -> None:
        if self.product_ids:
            await _remove_products(",".join(f"'{p}'::uuid" for p in self.product_ids))
        async with AsyncSessionLocal() as db:
            ids = ",".join(f"'{a}'" for a in self.agent_ids)
            if ids:
                await db.execute(text(f"DELETE FROM company.agent_command_receipts WHERE principal_id IN ({ids})"))
                await db.execute(text(f"DELETE FROM company.authority_delegations WHERE grantee_id IN ({ids})"))
                await db.execute(text(f"DELETE FROM company.agents WHERE id IN ({ids})"))
            if self.user_ids:
                await db.execute(text("DELETE FROM company.users WHERE id IN ("
                                      + ",".join(f"'{u}'" for u in self.user_ids) + ")"))
            await db.commit()


@pytest_asyncio.fixture
async def mw(admin_headers, monkeypatch):
    monkeypatch.setattr(settings, "MISSION_TOOLS_ENABLED", True)
    command_receipts.agent_write_limiter.reset()
    w = McpWorld(admin_headers)
    yield w
    await w.cleanup()
    command_receipts.agent_write_limiter.reset()


@pytest.fixture
def mcp_as(monkeypatch):
    """Route the MCP's HTTP client to the in-process app, as a given agt_."""
    real_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs.pop("timeout", None)
        return real_client(transport=ASGITransport(app=app), timeout=30.0)

    monkeypatch.setattr(factory_server, "BASE_URL", "http://test")
    monkeypatch.setattr(factory_server.httpx, "AsyncClient", factory)

    def use(token: str | None) -> None:
        if token is None:
            monkeypatch.delenv("FORGEHUB_AGENT_TOKEN", raising=False)
        else:
            monkeypatch.setenv("FORGEHUB_AGENT_TOKEN", token)
    return use


def _key() -> str:
    return f"mission-test-{uuid.uuid4()}"


async def _mission_by_agent(mw: McpWorld, mcp_as) -> tuple[dict, uuid.UUID, str, uuid.UUID]:
    product_id, version_id = await mw.version()
    orchestrator = await mw.agent("orch", runtime="hermes", never_does=[HERMES_NEVER])
    token = await mw.token(orchestrator, product_id=product_id)
    mcp_as(token)
    created = await factory_server.create_internal_project(str(version_id), f"Mission {uuid.uuid4().hex[:6]}", _key())
    return created, orchestrator, token, version_id


# ---------------------------------------------------------------------------
# create_internal_project (§5.1)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_internal_project_idempotent(mw, mcp_as):
    product_id, version_id = await mw.version()
    orchestrator = await mw.agent("orch", runtime="hermes")
    token = await mw.token(orchestrator, product_id=product_id)
    mcp_as(token)
    key = _key()
    name = f"Mission {uuid.uuid4().hex[:6]}"

    first = await factory_server.create_internal_project(str(version_id), name, key)
    assert first["created"] is True and first["replayed"] is False
    assert first["project_type"] == "mission" and first["mission_state"] == "draft"
    assert first["project_status"] == "planned"
    again = await factory_server.create_internal_project(str(version_id), name, key)
    assert again["project_id"] == first["project_id"] and again["replayed"] is True and again["created"] is False

    body = {"product_version_id": str(version_id), "name": name, "project_type": "mission", "idempotency_key": key}
    async with mw.client(mw.bearer(token)) as client:
        replay = await client.post("/api/v1/missions", json=body)
        reused = await client.post("/api/v1/missions", json={**body, "description": "other"})
        clash = await client.post("/api/v1/missions", json={**body, "name": f"  {name.upper()} ",
                                                            "idempotency_key": _key()})
    assert replay.status_code == 200 and replay.headers["Idempotent-Replay"] == "true"
    assert replay.json()["project_id"] == first["project_id"]
    assert reused.status_code == 409 and reused.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert clash.status_code == 409 and clash.json()["detail"]["code"] == "PROJECT_NAME_EXISTS_IN_VERSION"
    assert clash.json()["detail"]["project_id"] == first["project_id"]

    project_id = uuid.UUID(first["project_id"])
    async with AsyncSessionLocal() as db:
        projects = (await db.execute(select(Project.id).where(Project.product_version_id == version_id))).all()
        assert len(projects) == 1
        mission = (await db.execute(select(ProjectMission).where(ProjectMission.project_id == project_id))).scalar_one()
        assert mission.orchestrator_agent_id == orchestrator  # an agent caller orchestrates by default
        receipts = (await db.execute(select(AgentCommandReceipt).where(
            AgentCommandReceipt.principal_id == orchestrator))).scalars().all()
        assert [(r.idempotency_key, r.target_id, r.response_status) for r in receipts] == [(key, project_id, 201)]
        audit = (await db.execute(select(AuditEvent).where(AuditEvent.entity_id == project_id))).scalars().all()
        events = sorted(a.event_type for a in audit)
        assert events == ["mission_created", "project_created"]
        assert all(a.actor != "system" and a.payload["idempotency_key"] == key for a in audit)
        assert {a.payload["authority_source"] for a in audit} == {"delegation"}


@pytest.mark.asyncio
async def test_create_internal_project_maintenance_in_process(mw):
    product_id, version_id = await mw.version()
    agent = await mw.agent("planner", runtime="hermes")
    token = await mw.token(agent, product_id=product_id)
    base = {"product_version_id": str(version_id), "project_type": "maintenance"}
    async with mw.client(mw.bearer(token)) as client:
        created = await client.post("/api/v1/missions", json={
            **base, "name": f"Maint {uuid.uuid4().hex[:6]}", "idempotency_key": _key(),
            "working_directory_path": "/root/project/x"})
        no_key = await client.post("/api/v1/missions", json={**base, "name": "no key"})
        mission_field = await client.post("/api/v1/missions", json={
            **base, "name": "with executors", "idempotency_key": _key(),
            "executor_project_ids": [str(uuid.uuid4())]})
        relative = await client.post("/api/v1/missions", json={
            **base, "name": "relative", "idempotency_key": _key(), "working_directory_path": "rel/path"})
        missing_version = await client.post("/api/v1/missions", json={
            **base, "product_version_id": str(uuid.uuid4()), "name": "x", "idempotency_key": _key()})
    assert created.status_code == 201, created.text
    data = created.json()
    assert data["project_type"] == "maintenance" and data["mission_state"] is None and data["state"] is None
    assert no_key.status_code == 422 and no_key.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"
    assert mission_field.status_code == 422 and mission_field.json()["detail"]["code"] == "MISSION_ONLY_FIELDS"
    assert relative.status_code == 422 and relative.json()["detail"]["code"] == "PATH_NOT_ABSOLUTE"
    assert missing_version.status_code == 404
    async with AsyncSessionLocal() as db:
        project = await db.get(Project, uuid.UUID(data["project_id"]))
        assert project.project_type == "maintenance" and project.owner.startswith("mission-test-planner")
        assert (await db.execute(select(ProjectMission).where(ProjectMission.project_id == project.id))).first() is None
        members = (await db.execute(select(ProjectAgentMembership).where(
            ProjectAgentMembership.project_id == project.id))).scalars().all()
        assert [(m.agent_id, m.role, m.status) for m in members] == [(agent, "coordinator", "active")]


@pytest.mark.asyncio
async def test_create_internal_project_scope_refused(mw):
    product_id, version_id = await mw.version()
    other_product, _other_version = await mw.version()
    agent = await mw.agent("orch", runtime="hermes")
    no_delegation = await mw.token(agent, actions=None)
    wrong_product = await mw.token(agent, product_id=other_product)
    wrong_action = await mw.token(agent, actions=["mission.orchestrate"], product_id=product_id)
    body = {"product_version_id": str(version_id), "name": "refused", "idempotency_key": _key()}
    for token in (no_delegation, wrong_product, wrong_action):
        async with mw.client(mw.bearer(token)) as client:
            response = await client.post("/api/v1/missions", json={**body, "idempotency_key": _key()})
        assert response.status_code == 403 and response.json()["detail"]["code"] == "DELEGATION_REQUIRED"
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(Project.id).where(Project.product_version_id == version_id))).first() is None


# ---------------------------------------------------------------------------
# manage_project_members (§5.2)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_members_rules(mw, mcp_as):
    created, orchestrator, token, _version = await _mission_by_agent(mw, mcp_as)
    project_id = created["project_id"]
    developer = await mw.agent("dev", runtime="claude")
    hermes = await mw.agent("hermes", runtime="hermes", never_does=[HERMES_NEVER, "Atuar como qa"])
    inactive = await mw.agent("inactive", runtime="codex", active=False)
    stranger = await mw.agent("stranger", runtime="claude")

    refused = [
        {"op": "add", "agent_id": str(developer), "role": "developer", "can_approve": True},
        {"op": "add", "agent_id": str(hermes), "role": "developer"},
        {"op": "add", "agent_id": str(inactive), "role": "reviewer"},
        {"op": "update", "agent_id": str(stranger), "role": "reviewer"},
        {"op": "add", "agent_id": str(uuid.uuid4()), "role": "qa"},
    ]
    with pytest.raises(factory_server.FactoryError) as exc:
        await factory_server.manage_project_members(project_id, refused, _key())
    message = str(exc.value)
    assert "(422): MEMBER_RULE_VIOLATION" in message
    for code in ("CAN_APPROVE_NOT_FOR_AGENTS", "CODE_ROLE_REQUIRES_EXTERNAL_RUNTIME", "CHARTER_NEVER_DOES",
                 "AGENT_INACTIVE", "NOT_A_MEMBER", "AGENT_NOT_FOUND"):
        assert code in message, code

    async with mw.client(mw.bearer(token)) as client:
        apply_url = f"/api/v1/missions/{project_id}/members:apply"
        second_coordinator = await client.post(apply_url, json={
            "operations": [{"op": "add", "agent_id": str(developer), "role": "coordinator"}],
            "idempotency_key": _key()})
        invalid_role = await client.post(apply_url, json={
            "operations": [{"op": "add", "agent_id": str(developer), "role": "wizard"}], "idempotency_key": _key()})
        never_qa = await client.post(apply_url, json={
            "operations": [{"op": "add", "agent_id": str(hermes), "role": "qa"}], "idempotency_key": _key()})
        last = await client.post(apply_url, json={
            "operations": [{"op": "release", "agent_id": str(orchestrator)}], "idempotency_key": _key()})
        demote = await client.post(apply_url, json={
            "operations": [{"op": "update", "agent_id": str(orchestrator), "role": "planner"}],
            "idempotency_key": _key()})
        too_many = await client.post(apply_url, json={
            "operations": [{"op": "suspend", "agent_id": str(uuid.uuid4())}] * 21, "idempotency_key": _key()})
    assert second_coordinator.status_code == 422
    assert second_coordinator.json()["detail"]["violations"][0]["code"] == "COORDINATOR_IS_ORCHESTRATOR"
    assert invalid_role.status_code == 422
    assert invalid_role.json()["detail"]["violations"][0]["code"] == "INVALID_ROLE"
    assert never_qa.status_code == 422 and never_qa.json()["detail"]["violations"][0]["code"] == "CHARTER_NEVER_DOES"
    assert last.status_code == 409 and last.json()["detail"]["code"] == "LAST_COORDINATOR"
    assert demote.status_code == 409 and demote.json()["detail"]["code"] == "LAST_COORDINATOR"
    assert too_many.status_code == 422

    # All or nothing: none of the refused calls left a row behind.
    async with AsyncSessionLocal() as db:
        members = (await db.execute(select(ProjectAgentMembership).where(
            ProjectAgentMembership.project_id == uuid.UUID(project_id)))).scalars().all()
        assert [(m.agent_id, m.role, m.status) for m in members] == [(orchestrator, "coordinator", "active")]


@pytest.mark.asyncio
async def test_members_apply_lifecycle_idempotent_and_audited(mw, mcp_as):
    created, orchestrator, token, _version = await _mission_by_agent(mw, mcp_as)
    project_id = created["project_id"]
    developer = await mw.agent("dev", runtime="codex")
    reviewer = await mw.agent("reviewer", runtime="hermes", never_does=[HERMES_NEVER])
    key = _key()
    ops = [
        {"op": "add", "agent_id": str(developer), "role": "developer", "responsibilities": "Backend"},
        {"op": "add", "agent_id": str(reviewer), "role": "reviewer", "can_review": True},
    ]
    first = await factory_server.manage_project_members(project_id, ops, key)
    assert first["replayed"] is False and first["violations"] == []
    roster = {m["agent_id"]: m for m in first["memberships"]}
    assert roster[str(developer)]["role"] == "developer" and roster[str(reviewer)]["can_review"] is True
    replay = await factory_server.manage_project_members(project_id, ops, key)
    assert replay["replayed"] is True and replay["applied"] == first["applied"]
    with pytest.raises(factory_server.FactoryError, match="IDEMPOTENCY_KEY_REUSED"):
        await factory_server.manage_project_members(project_id, ops[:1], key)

    second = await factory_server.manage_project_members(project_id, [
        {"op": "update", "agent_id": str(developer), "role": "architect", "valid_to": "2027-01-31"},
        {"op": "suspend", "agent_id": str(reviewer)},
    ], _key())
    roster = {m["agent_id"]: m for m in second["memberships"]}
    assert roster[str(developer)]["role"] == "architect" and roster[str(developer)]["valid_to"] == "2027-01-31"
    assert roster[str(reviewer)]["status"] == "suspended"
    third = await factory_server.manage_project_members(project_id, [
        {"op": "release", "agent_id": str(reviewer)},
    ], _key())
    assert {m["agent_id"]: m["status"] for m in third["memberships"]}[str(reviewer)] == "released"
    readd = await factory_server.manage_project_members(project_id, [
        {"op": "add", "agent_id": str(reviewer), "role": "qa"},
    ], _key())
    roster = {m["agent_id"]: m for m in readd["memberships"]}
    assert roster[str(reviewer)]["status"] == "active" and roster[str(reviewer)]["role"] == "qa"
    assert roster[str(reviewer)]["id"] == first["applied"][1]["membership_id"]  # same row, never deleted
    with pytest.raises(factory_server.FactoryError, match="MEMBER_ALREADY_EXISTS"):
        await factory_server.manage_project_members(project_id, [
            {"op": "add", "agent_id": str(developer), "role": "developer"}], _key())

    async with AsyncSessionLocal() as db:
        events = (await db.execute(select(AuditEvent).where(
            AuditEvent.entity_id == uuid.UUID(project_id), AuditEvent.event_type.like("membership_%"),
        ).order_by(AuditEvent.created_at))).scalars().all()
        assert sorted(e.event_type for e in events) == sorted([
            "membership_add", "membership_add", "membership_update", "membership_suspend", "membership_release",
            "membership_add"])
        orchestrator_name = (await db.get(Agent, orchestrator)).name
        assert {e.actor for e in events} == {orchestrator_name}
        assert all(e.payload["principal_id"] == str(orchestrator) and e.payload["idempotency_key"] for e in events)


@pytest.mark.asyncio
async def test_members_caller_must_be_coordinator_with_delegation(mw, mcp_as):
    created, orchestrator, _token, _version = await _mission_by_agent(mw, mcp_as)
    project_id = uuid.UUID(created["project_id"])
    member = await mw.agent("member", runtime="claude")
    async with AsyncSessionLocal() as db:
        db.add(ProjectAgentMembership(project_id=project_id, agent_id=member, role="developer", status="active"))
        await db.commit()
    other_product, _other_version = await mw.version()
    member_with_delegation = await mw.token(member, project_id=project_id)
    outsider = await mw.agent("outsider", runtime="claude")
    outsider_with_delegation = await mw.token(outsider, project_id=project_id)
    body = {"operations": [{"op": "add", "agent_id": str(outsider), "role": "qa"}]}
    url = f"/api/v1/missions/{project_id}/members:apply"

    async def refused(token: str, code: str) -> None:
        async with mw.client(mw.bearer(token)) as client:
            response = await client.post(url, json={**body, "idempotency_key": _key()})
        assert response.status_code == 403 and response.json()["detail"]["code"] == code, response.text

    await refused(member_with_delegation, "NOT_PROJECT_COORDINATOR")
    await refused(outsider_with_delegation, "NOT_PROJECT_COORDINATOR")
    # The orchestrator loses its delegation (revoked): refused; one for another product: still refused.
    async with AsyncSessionLocal() as db:
        await db.execute(text("UPDATE company.authority_delegations SET status = 'revoked', revoked_at = now() "
                              f"WHERE grantee_id = '{orchestrator}'"))
        await db.commit()
    await refused(await mw.token(orchestrator, actions=None), "DELEGATION_REQUIRED")
    await refused(await mw.token(orchestrator, product_id=other_product), "DELEGATION_REQUIRED")
    async with mw.client() as client:  # admin
        missing = await client.post(f"/api/v1/missions/{uuid.uuid4()}/members:apply",
                                    json={**body, "idempotency_key": _key()})
        admin_ok = await client.post(url, json={**body, "idempotency_key": _key()})
    assert missing.status_code == 404 and missing.json()["detail"]["code"] == "PROJECT_NOT_FOUND"
    assert admin_ok.status_code == 200, admin_ok.text

    # Another agent's token never acts as the caller: no token at all is a tool error.
    mcp_as(None)
    with pytest.raises(factory_server.FactoryError, match="FORGEHUB_AGENT_TOKEN is required"):
        await factory_server.manage_project_members(str(project_id), body["operations"], _key())


@pytest.mark.asyncio
async def test_members_on_terminal_mission_refused(mw, mcp_as):
    created, _orchestrator, token, _version = await _mission_by_agent(mw, mcp_as)
    project_id = created["project_id"]
    async with AsyncSessionLocal() as db:
        await db.execute(text(
            f"UPDATE company.project_missions SET state = 'cancelled' WHERE project_id = '{project_id}'"))
        await db.commit()
    dev = await mw.agent("dev", runtime="claude")
    async with mw.client(mw.bearer(token)) as client:
        response = await client.post(f"/api/v1/missions/{project_id}/members:apply", json={
            "operations": [{"op": "add", "agent_id": str(dev), "role": "developer"}], "idempotency_key": _key()})
    assert response.status_code == 409 and response.json()["detail"]["code"] == "MISSION_TERMINAL"


# ---------------------------------------------------------------------------
# Switch, limits, retention (§0.4, §0.6, §5)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_tools_disabled_flag(mw, mcp_as, monkeypatch):
    created, _orchestrator, token, version_id = await _mission_by_agent(mw, mcp_as)
    monkeypatch.setattr(settings, "MISSION_TOOLS_ENABLED", False)
    name = f"off {uuid.uuid4().hex[:6]}"
    with pytest.raises(factory_server.FactoryError, match=r"\(503\): MISSION_TOOLS_DISABLED"):
        await factory_server.create_internal_project(str(version_id), name, _key())
    with pytest.raises(factory_server.FactoryError, match=r"\(503\): MISSION_TOOLS_DISABLED"):
        await factory_server.manage_project_members(created["project_id"], [
            {"op": "add", "agent_id": str(uuid.uuid4()), "role": "qa"}], _key())
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(Project.id).where(Project.name == name))).first() is None
        members = (await db.execute(select(ProjectAgentMembership.id).where(
            ProjectAgentMembership.project_id == uuid.UUID(created["project_id"])))).all()
        assert len(members) == 1


@pytest.mark.asyncio
async def test_rate_limit_and_body_size(mw, mcp_as, monkeypatch):
    created, _orchestrator, token, version_id = await _mission_by_agent(mw, mcp_as)
    monkeypatch.setattr(command_receipts, "agent_write_limiter", command_receipts._WriteRateLimiter(1))
    async with mw.client(mw.bearer(token)) as client:
        url = f"/api/v1/missions/{created['project_id']}/members:apply"
        body = {"operations": [{"op": "suspend", "agent_id": str(uuid.uuid4())}]}
        first = await client.post(url, json={**body, "idempotency_key": _key()})
        limited = await client.post(url, json={**body, "idempotency_key": _key()})
        huge = await client.post(url, json={**body, "idempotency_key": _key(), "pad": "x" * (65 * 1024)})
    assert first.status_code == 422  # passed the limiter, refused by the rules
    assert limited.status_code == 429 and limited.json()["detail"]["code"] == "RATE_LIMITED"
    assert int(limited.headers["Retry-After"]) >= 1
    assert huge.status_code == 413 and huge.json()["detail"]["code"] == "PAYLOAD_TOO_LARGE"


@pytest.mark.asyncio
async def test_receipt_retention_sweep(mw):
    agent = await mw.agent("retention", runtime="claude")
    async with AsyncSessionLocal() as db:
        old = AgentCommandReceipt(principal_type="agent", principal_id=agent, idempotency_key=_key(),
                                  command="mission.test", request_hash="0" * 64, response_status=200,
                                  response_body={})
        fresh = AgentCommandReceipt(principal_type="agent", principal_id=agent, idempotency_key=_key(),
                                    command="mission.test", request_hash="0" * 64, response_status=200,
                                    response_body={})
        db.add_all([old, fresh])
        await db.flush()
        await db.execute(text("UPDATE company.agent_command_receipts SET created_at = now() - interval '31 days' "
                              f"WHERE id = '{old.id}'"))
        await db.commit()
        old_id, fresh_id = old.id, fresh.id
    async with AsyncSessionLocal() as db:
        assert await command_receipts.run_command_receipt_retention(db) >= 1
    async with AsyncSessionLocal() as db:
        assert await db.get(AgentCommandReceipt, old_id) is None
        assert await db.get(AgentCommandReceipt, fresh_id) is not None


# ---------------------------------------------------------------------------
# Migration (only this revision moves)
# ---------------------------------------------------------------------------
REVISION = "d3f7a1c9e2b5"
BACKEND_DIR = Path(__file__).resolve().parents[2]


def _alembic(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args], cwd=BACKEND_DIR, capture_output=True, text=True,
        env={**os.environ, "ENVIRONMENT": "test"}, timeout=180,
    )


async def _receipts_table_exists() -> bool:
    async with AsyncSessionLocal() as db:
        return (await db.execute(text("SELECT to_regclass('company.agent_command_receipts')"))).scalar() is not None


@pytest.mark.asyncio
async def test_migration_roundtrip_only_this_revision():
    """Downgrade to the parent and back. Skipped when the shared test database
    carries any other applied head (a sibling slice's revision), since a
    downgrade there would unapply it too."""
    current = _alembic("current").stdout.split()
    heads = [token for token in current if len(token) == 12 and token.isalnum()]
    if heads != [REVISION]:
        pytest.skip(f"database at {heads}, not only {REVISION}")
    down = _alembic("downgrade", f"{REVISION}@-1")
    assert down.returncode == 0, down.stderr
    try:
        assert not await _receipts_table_exists()
        assert "b9e4d2a7c615" in _alembic("current").stdout
    finally:
        up = _alembic("upgrade", REVISION)
        assert up.returncode == 0, up.stderr
    assert await _receipts_table_exists()
    assert REVISION in _alembic("current").stdout

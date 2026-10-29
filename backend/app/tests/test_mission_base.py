"""M0.0 mission base (docs/architecture/MCP_MISSION_TOOLS_SPEC.md §2, §3, §3.1, §6.1, §9.1).

Runs only against the isolated test database. Every test builds its own
product, agents and projects and removes them at the end (no transaction
rollback between tests). The two migration tests run Alembic for real and
always leave the database back at head.
"""
import hashlib
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

from app.api.routes import mission as mission_routes
from app.core.mission import ALLOWED_TRANSITIONS, apply_mission_state
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent, AgentServiceCredential, AgentSkill, Skill
from app.db.models.artifact import Artifact, ArtifactStatus, ArtifactType, ArtifactVersion, ArtifactVersionStatus
from app.db.models.backlog import PlanningItem
from app.db.models.governance import AuditEvent, AuthorityDelegation
from app.db.models.mission import (
    MISSION_STATES,
    MISSION_STATUS_PROJECTION,
    MissionAcceptanceCriterion,
    MissionCriterionTask,
    MissionDecision,
    ProjectMission,
)
from app.db.models.orchestration import ProjectAgentMembership, TaskExecutionReview
from app.db.models.product import Product, ProductVersion
from app.db.models.project import PlanBaseline, Project, ProjectPlan
from app.db.models.task import ProjectTask, TaskAssignment, TaskExecution
from app.db.models.user import User
from app.main import app

BACKEND_DIR = Path(__file__).resolve().parents[2]
PRE_M0_REVISION = "e4b8c1d7a9f3"


def _alembic(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args], cwd=BACKEND_DIR, capture_output=True, text=True,
        env={**os.environ, "ENVIRONMENT": "test"}, timeout=180,
    )


class World:
    """Rows one test owns; `cleanup` removes them in FK-safe order."""

    def __init__(self, admin_headers: dict[str, str]):
        self.admin = admin_headers
        self.tag = uuid.uuid4().hex[:8]
        self.agent_ids: list[uuid.UUID] = []
        self.skill_ids: list[uuid.UUID] = []
        self.user_ids: list[uuid.UUID] = []
        self.product_id: uuid.UUID | None = None
        self.version_id: uuid.UUID | None = None

    def client(self, headers: dict[str, str] | None = None) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           headers=headers if headers is not None else self.admin)

    async def setup(self) -> None:
        async with AsyncSessionLocal() as db:
            product = Product(name=f"mission-test-{self.tag}")
            db.add(product)
            await db.flush()
            version = ProductVersion(product_id=product.id, version="1.0")
            db.add(version)
            await db.commit()
            self.product_id, self.version_id = product.id, version.id

    async def agent(self, label: str) -> uuid.UUID:
        async with AsyncSessionLocal() as db:
            agent = Agent(name=f"mission-test-{label}-{self.tag}-{uuid.uuid4().hex[:4]}", runtime_type="claude")
            db.add(agent)
            await db.commit()
            self.agent_ids.append(agent.id)
            return agent.id

    async def agent_token(self, agent_id: uuid.UUID, actions: list[str] | None, project_id=None) -> dict[str, str]:
        token = f"agt_{uuid.uuid4().hex}{uuid.uuid4().hex}"
        async with AsyncSessionLocal() as db:
            db.add(AgentServiceCredential(agent_id=agent_id, label="mission-test",
                                          token_hash=hashlib.sha256(token.encode()).hexdigest()))
            if actions:
                grantor = User(username=f"mission-grantor-{uuid.uuid4().hex[:8]}", hashed_password="x", is_admin=True)
                db.add(grantor)
                await db.flush()
                self.user_ids.append(grantor.id)
                now = datetime.now(timezone.utc)
                db.add(AuthorityDelegation(
                    grantor_user_id=grantor.id, grantee_type="agent", grantee_id=agent_id, scope_type="project",
                    project_id=project_id, allowed_actions=actions, max_risk="low",
                    valid_from=now - timedelta(minutes=1), expires_at=now + timedelta(hours=1),
                ))
            await db.commit()
        return {"Authorization": f"Bearer {token}"}

    async def skill(self, approved: bool = True) -> uuid.UUID:
        async with AsyncSessionLocal() as db:
            skill = Skill(name=f"mission-test-skill-{uuid.uuid4().hex[:8]}", version="1.0", origin="internal",
                          risk_level="low", permissions="none", is_approved=approved)
            db.add(skill)
            await db.commit()
            self.skill_ids.append(skill.id)
            return skill.id

    async def create_mission(self, **overrides) -> dict:
        orchestrator = overrides.pop("orchestrator_agent_id", None) or await self.agent("orch")
        body = {"product_version_id": str(self.version_id), "name": f"Mission {uuid.uuid4().hex[:6]}",
                "orchestrator_agent_id": str(orchestrator), **overrides}
        async with self.client() as client:
            response = await client.post("/api/v1/missions", json=body)
        assert response.status_code == 201, response.text
        return response.json()

    async def common_project(self) -> dict:
        async with self.client() as client:
            response = await client.post("/api/v1/projects", json={
                "name": f"common-{uuid.uuid4().hex[:6]}", "product_version_id": str(self.version_id)})
        assert response.status_code == 201, response.text
        return response.json()

    async def cleanup(self) -> None:
        await _remove_products(f"SELECT '{self.product_id}'::uuid" if self.product_id else None)
        async with AsyncSessionLocal() as db:
            ids = ",".join(f"'{a}'" for a in self.agent_ids)
            if ids:
                await db.execute(text(f"DELETE FROM company.authority_delegations WHERE grantee_id IN ({ids})"))
                await db.execute(text(f"DELETE FROM company.agents WHERE id IN ({ids})"))
            if self.skill_ids:
                await db.execute(text("DELETE FROM company.skills WHERE id IN ("
                                      + ",".join(f"'{s}'" for s in self.skill_ids) + ")"))
            if self.user_ids:
                await db.execute(text("DELETE FROM company.users WHERE id IN ("
                                      + ",".join(f"'{u}'" for u in self.user_ids) + ")"))
            await db.execute(text(f"DELETE FROM company.artifacts WHERE name LIKE 'mission-test-{self.tag}%'"))
            await db.commit()


async def _remove_products(product_ids_sql: str | None) -> None:
    """Delete every row hanging off the given products' projects, FK-safe."""
    if product_ids_sql is None:
        return
    projects = ("SELECT p.id FROM company.projects p JOIN company.product_versions v "
                f"ON v.id = p.product_version_id WHERE v.product_id IN ({product_ids_sql})")
    items = f"SELECT id FROM company.planning_items WHERE project_id IN ({projects})"
    tasks = f"SELECT id FROM company.project_tasks WHERE planning_item_id IN ({items})"
    executions = f"SELECT id FROM company.task_executions WHERE task_id IN ({tasks})"
    async with AsyncSessionLocal() as db:
        for statement in (
            f"DELETE FROM company.mission_criterion_tasks WHERE task_id IN ({tasks})",
            f"DELETE FROM company.mission_decisions WHERE mission_project_id IN ({projects})",
            f"DELETE FROM company.mission_project_links WHERE mission_project_id IN ({projects}) "
            f"OR executor_project_id IN ({projects})",
            f"DELETE FROM company.project_missions WHERE project_id IN ({projects})",
            f"DELETE FROM company.task_execution_reviews WHERE execution_id IN ({executions})",
            f"DELETE FROM company.task_executions WHERE task_id IN ({tasks})",
            f"DELETE FROM company.task_dependencies WHERE task_id IN ({tasks})",
            f"DELETE FROM company.task_assignments WHERE task_id IN ({tasks})",
            f"DELETE FROM company.project_tasks WHERE id IN ({tasks})",
            f"DELETE FROM company.audit_events WHERE entity_id IN ({projects})",
            f"DELETE FROM company.projects WHERE id IN ({projects})",
            f"DELETE FROM company.products WHERE id IN ({product_ids_sql})",
        ):
            await db.execute(text(statement))
        await db.commit()


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _clean_stale_mission_fixtures():
    """A killed run can skip teardown; its missions would make the migration
    tests' downgrade refuse."""
    stale = "SELECT id FROM company.products WHERE name LIKE 'mission-test-%'"
    await _remove_products(stale)
    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM company.authority_delegations WHERE grantee_id IN "
                              "(SELECT id FROM company.agents WHERE name LIKE 'mission-test-%')"))
        await db.execute(text("DELETE FROM company.agents WHERE name LIKE 'mission-test-%'"))
        await db.execute(text("DELETE FROM company.skills WHERE name LIKE 'mission-test-skill-%'"))
        await db.execute(text("DELETE FROM company.artifacts WHERE name LIKE 'mission-test-%'"))
        await db.execute(text("DELETE FROM company.users WHERE username LIKE 'mission-grantor-%' OR username LIKE 'mission-plain-%'"))
        await db.commit()
    yield


@pytest_asyncio.fixture
async def world(admin_headers):
    w = World(admin_headers)
    await w.setup()
    yield w
    await w.cleanup()


async def _force(project_id, **fields) -> None:
    async with AsyncSessionLocal() as db:
        mission = await db.get(ProjectMission, uuid.UUID(str(project_id)))
        for key, value in fields.items():
            setattr(mission, key, value)
        if "state" in fields:
            project = await db.get(Project, mission.project_id)
            project.status = MISSION_STATUS_PROJECTION[fields["state"]]
        await db.commit()


async def _row_version(project_id) -> int:
    async with AsyncSessionLocal() as db:
        return (await db.get(ProjectMission, uuid.UUID(str(project_id)))).row_version


async def _brief(world: World) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        artifact = Artifact(name=f"mission-test-{world.tag}-brief", artifact_type=ArtifactType.CONTEXT_BRIEF,
                            status=ArtifactStatus.APPROVED)
        db.add(artifact)
        await db.flush()
        db.add(ArtifactVersion(artifact_id=artifact.id, version_number=1, status=ArtifactVersionStatus.FINAL,
                               location_uri="docs/missions/test/BRIEF.md"))
        await db.commit()
        return artifact.id


async def _task(project_id, title="task", **fields) -> ProjectTask:
    async with AsyncSessionLocal() as db:
        item = PlanningItem(title=f"item {title}", item_type="feature", project_id=uuid.UUID(str(project_id)))
        db.add(item)
        await db.flush()
        task = ProjectTask(planning_item_id=item.id, title=title, **fields)
        db.add(task)
        await db.commit()
        await db.refresh(task)
        return task


async def _member(project_id, agent_id, role="developer", can_review=False) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        membership = ProjectAgentMembership(project_id=uuid.UUID(str(project_id)), agent_id=agent_id, role=role,
                                            status="active", can_review=can_review)
        db.add(membership)
        await db.commit()
        return membership.id


async def _assign(task_id, agent_id, membership_id) -> None:
    async with AsyncSessionLocal() as db:
        db.add(TaskAssignment(task_id=task_id, agent_id=agent_id, membership_id=membership_id, status="active"))
        await db.commit()


async def _criterion(project_id, verifier_agent_id, *, status="open", task_ids=()) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        criterion = MissionAcceptanceCriterion(
            mission_project_id=uuid.UUID(str(project_id)), code=f"AC-{uuid.uuid4().hex[:4]}",
            statement="The thing works", verification_method="Run the smoke test",
            verifier_agent_id=verifier_agent_id, status=status,
        )
        db.add(criterion)
        await db.flush()
        for task_id in task_ids:
            db.add(MissionCriterionTask(criterion_id=criterion.id, task_id=task_id))
        await db.commit()
        return criterion.id


async def _baseline(project_id) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        plan = ProjectPlan(project_id=uuid.UUID(str(project_id)), name="plan", status="baselined")
        db.add(plan)
        await db.flush()
        baseline = PlanBaseline(project_plan_id=plan.id, name="baseline 1")
        db.add(baseline)
        await db.commit()
        return baseline.id


async def _transition(world: World, project_id, to, reason=None, headers=None, version=None):
    body = {"to": to, "expected_row_version": version if version is not None else await _row_version(project_id)}
    if reason is not None:
        body["reason"] = reason
    async with world.client(headers) as client:
        return await client.post(f"/api/v1/missions/{project_id}:transition", json=body)


async def _advance(world: World, project_id, to, key=None, headers=None, reason="next stage"):
    async with world.client(headers) as client:
        return await client.post(f"/api/v1/missions/{project_id}/planning:advance", json={
            "to": to, "reason": reason, "idempotency_key": key or uuid.uuid4().hex})


def _codes(response) -> set[str]:
    return {item["code"] for item in response.json()["detail"]["unmet"]}


# ---------------------------------------------------------------------------
# §9.1
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_common_projects_unchanged(world):
    created = await world.common_project()
    project_id = created["id"]
    async with world.client() as client:
        patched = await client.patch(f"/api/v1/projects/{project_id}", json={"status": "active", "project_type": "x"})
        listed = await client.get("/api/v1/projects")
    assert patched.status_code == 200 and patched.json()["status"] == "active"
    # Same response shape as before M0.0: project_type is still not exposed.
    assert "project_type" not in created and set(patched.json()) == set(created)
    assert any(p["id"] == project_id for p in listed.json())
    async with AsyncSessionLocal() as db:
        project = await db.get(Project, uuid.UUID(project_id))
        assert project.project_type == "creation"
        assert await db.get(ProjectMission, project.id) is None
    async with world.client() as client:
        assert (await client.delete(f"/api/v1/projects/{project_id}")).status_code == 204


@pytest.mark.asyncio
async def test_project_create_schema_does_not_accept_mission(world):
    async with world.client() as client:
        response = await client.post("/api/v1/projects", json={
            "name": f"sneaky-{world.tag}", "product_version_id": str(world.version_id), "project_type": "mission"})
    assert response.status_code == 201
    async with AsyncSessionLocal() as db:
        project = await db.get(Project, uuid.UUID(response.json()["id"]))
        assert project.project_type == "creation"
        assert await db.get(ProjectMission, project.id) is None


@pytest.mark.asyncio
async def test_create_mission_projects_draft_and_names_orchestrator(world):
    executor = await world.common_project()
    mission = await world.create_mission(executor_project_ids=[executor["id"]])
    assert mission["state"] == "draft" and mission["project_status"] == "planned"
    assert mission["project_type"] == "mission" and mission["autonomy_level"] == "N0"
    assert mission["executor_project_ids"] == [executor["id"]]
    async with AsyncSessionLocal() as db:
        coordinator = (await db.execute(select(ProjectAgentMembership).where(
            ProjectAgentMembership.project_id == uuid.UUID(mission["project_id"])))).scalars().all()
        assert [(m.role, m.status, str(m.agent_id)) for m in coordinator] == [
            ("coordinator", "active", mission["orchestrator_agent_id"])]
        audit = (await db.execute(select(AuditEvent.event_type).where(
            AuditEvent.entity_id == uuid.UUID(mission["project_id"])))).scalars().all()
        assert "mission_created" in audit
    # A mission is never an executor project (no nesting).
    async with world.client() as client:
        nested = await client.post("/api/v1/missions", json={
            "product_version_id": str(world.version_id), "name": "nested",
            "orchestrator_agent_id": mission["orchestrator_agent_id"],
            "executor_project_ids": [mission["project_id"]]})
    assert nested.status_code == 422 and nested.json()["detail"]["code"] == "EXECUTOR_IS_MISSION"


@pytest.mark.asyncio
async def test_patch_status_refused_for_mission(world):
    mission = await world.create_mission()
    project_id = mission["project_id"]
    async with world.client() as client:
        status_patch = await client.patch(f"/api/v1/projects/{project_id}", json={"status": "completed"})
        type_patch = await client.patch(f"/api/v1/projects/{project_id}", json={"project_type": "creation"})
        name_patch = await client.patch(f"/api/v1/projects/{project_id}", json={"name": "renamed"})
    assert status_patch.status_code == 409
    assert status_patch.json()["detail"]["code"] == "MISSION_STATUS_IS_PROJECTED"
    assert type_patch.status_code == 409
    assert type_patch.json()["detail"]["code"] == "MISSION_STATUS_IS_PROJECTED"
    assert name_patch.status_code == 200 and name_patch.json()["status"] == "planned"


@pytest.mark.asyncio
async def test_mission_delete_refused(world):
    mission = await world.create_mission()
    async with world.client() as client:
        response = await client.delete(f"/api/v1/projects/{mission['project_id']}")
    assert response.status_code == 409 and response.json()["detail"]["code"] == "MISSION_DELETE_REFUSED"
    async with AsyncSessionLocal() as db:
        assert await db.get(Project, uuid.UUID(mission["project_id"])) is not None


@pytest.mark.asyncio
async def test_autonomy_level_n0_only(world):
    orchestrator = await world.agent("orch")
    async with world.client() as client:
        refused = await client.post("/api/v1/missions", json={
            "product_version_id": str(world.version_id), "name": "n1", "orchestrator_agent_id": str(orchestrator),
            "autonomy_level": "N1"})
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "AUTONOMY_LEVEL_NOT_ALLOWED"
    mission = await world.create_mission(orchestrator_agent_id=orchestrator)
    async with world.client() as client:
        patched = await client.patch(f"/api/v1/missions/{mission['project_id']}", json={
            "expected_row_version": mission["row_version"], "autonomy_level": "N3"})
    assert patched.status_code == 422 and patched.json()["detail"]["code"] == "AUTONOMY_LEVEL_NOT_ALLOWED"
    async with AsyncSessionLocal() as db:
        with pytest.raises(Exception):
            await db.execute(text(
                f"UPDATE company.project_missions SET autonomy_level = 'N9' WHERE project_id = '{mission['project_id']}'"))
            await db.commit()


async def _prepared_mission(world: World) -> tuple[dict, uuid.UUID, uuid.UUID]:
    """A mission whose every precondition can be met: brief approved, deadline,
    budget, a criterion with a linked task, and a current baseline."""
    verifier = await world.agent("verifier")
    mission = await world.create_mission(
        brief_artifact_id=str(await _brief(world)),
        deadline_at=(datetime.now(timezone.utc) + timedelta(days=10)).isoformat(),
        budget_limit="100.00",
    )
    project_id = mission["project_id"]
    task = await _task(project_id, status="done")
    criterion_id = await _criterion(project_id, verifier, task_ids=[task.id])
    await _force(project_id, current_baseline_id=await _baseline(project_id))
    return mission, criterion_id, verifier


async def _set_criterion(criterion_id, status) -> None:
    async with AsyncSessionLocal() as db:
        (await db.get(MissionAcceptanceCriterion, criterion_id)).status = status
        await db.commit()


@pytest.mark.asyncio
async def test_state_projection_all_transitions(world):
    mission, criterion_id, _ = await _prepared_mission(world)
    project_id = mission["project_id"]
    setup = {
        ("planning", "ready"): {"planning_stage": "baseline"},
    }
    criterion_status = {("active", "verifying"): "proven", ("verifying", "active"): "failed"}
    pairs = sorted(ALLOWED_TRANSITIONS) + [(f"paused:{s}", s) for s in ("planning", "ready", "active", "verifying")]
    for from_state, to_state in pairs:
        if (from_state, to_state) == ("verifying", "awaiting_acceptance"):
            continue
        if from_state.startswith("paused:"):
            await _force(project_id, state="paused", paused_from_state=from_state.split(":")[1])
        else:
            await _force(project_id, state=from_state,
                         paused_from_state="active" if from_state == "paused" else None,
                         planning_stage=setup.get((from_state, to_state), {}).get("planning_stage", "draft_plan"))
        await _set_criterion(criterion_id, criterion_status.get((from_state, to_state), "open"))
        response = await _transition(world, project_id, to_state, reason="because")
        assert response.status_code == 200, (from_state, to_state, response.text)
        body = response.json()
        assert body["state"] == to_state
        assert body["project_status"] == MISSION_STATUS_PROJECTION[to_state], (from_state, to_state)
        async with AsyncSessionLocal() as db:
            project = await db.get(Project, uuid.UUID(project_id))
            assert project.status == MISSION_STATUS_PROJECTION[to_state]
            event = f"mission_{from_state.split(':')[0]}_to_{to_state}"
            assert await db.scalar(select(AuditEvent.id).where(
                AuditEvent.entity_id == project.id, AuditEvent.event_type == event).limit(1)) is not None

    # verifying -> awaiting_acceptance needs the dossier, which M0.0 cannot read.
    await _force(project_id, state="verifying", paused_from_state=None)
    refused = await _transition(world, project_id, "awaiting_acceptance")
    assert refused.status_code == 409 and _codes(refused) == {"DOSSIER_NOT_RECORDED"}

    # Every pair outside the table is refused, including completing by transition.
    for from_state in MISSION_STATES:
        for to_state in MISSION_STATES:
            if (from_state, to_state) in ALLOWED_TRANSITIONS or from_state == to_state == "paused":
                continue
            if from_state == "paused" and to_state == "planning":
                continue  # resume target, checked below
            await _force(project_id, state=from_state,
                         paused_from_state="planning" if from_state == "paused" else None)
            response = await _transition(world, project_id, to_state, reason="x")
            assert response.status_code == 409, (from_state, to_state)
            assert response.json()["detail"]["code"] == "MISSION_TRANSITION_NOT_ALLOWED", (from_state, to_state)

    # The only writer of `completed` (the acceptance decision, §8) projects it too.
    project, state = Project(status="active"), ProjectMission(state="awaiting_acceptance", row_version=1,
                                                               paused_seconds=0)
    apply_mission_state(project, state, "completed", "accepted", datetime.now(timezone.utc))
    assert (state.state, project.status) == ("completed", "completed")


@pytest.mark.asyncio
async def test_transition_preconditions(world):
    mission = await world.create_mission()
    project_id = mission["project_id"]
    not_allowed = await _transition(world, project_id, "ready")
    assert not_allowed.json()["detail"]["code"] == "MISSION_TRANSITION_NOT_ALLOWED"

    response = await _transition(world, project_id, "planning")
    assert response.status_code == 409
    assert _codes(response) == {"BRIEF_MISSING", "DEADLINE_MISSING", "BUDGET_MISSING"}

    async with world.client() as client:
        stale = await client.post(f"/api/v1/missions/{project_id}:transition",
                                  json={"to": "planning", "expected_row_version": 99})
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "ROW_VERSION_CONFLICT"

    await _force(project_id, state="planning", planning_stage="consolidation")
    response = await _transition(world, project_id, "ready")
    assert _codes(response) == {"PLANNING_PIPELINE_UNFINISHED", "NO_CRITERIA", "DEADLINE_MISSING",
                                "BUDGET_MISSING", "BASELINE_MISSING"}

    await _force(project_id, state="paused", paused_from_state="active")
    no_reason = await _transition(world, project_id, "active")
    assert no_reason.status_code == 422 and no_reason.json()["detail"]["code"] == "REASON_REQUIRED"
    wrong_resume = await _transition(world, project_id, "ready", reason="resume")
    assert wrong_resume.json()["detail"]["code"] == "MISSION_TRANSITION_NOT_ALLOWED"

    # active -> verifying needs every criterion proven.
    await _force(project_id, state="active", paused_from_state=None)
    response = await _transition(world, project_id, "verifying")
    assert _codes(response) == {"CRITERIA_NOT_ALL_PROVEN"}


@pytest.mark.asyncio
async def test_orchestrator_acts_only_with_delegation(world):
    mission, _, _ = await _prepared_mission(world)
    project_id = mission["project_id"]
    orchestrator = uuid.UUID(mission["orchestrator_agent_id"])
    await _force(project_id, state="ready", planning_stage=None)

    without = await world.agent_token(orchestrator, None)
    assert (await _transition(world, project_id, "active", headers=without)).status_code == 403

    stranger = await world.agent_token(await world.agent("stranger"), ["mission.orchestrate"], uuid.UUID(project_id))
    assert (await _transition(world, project_id, "active", headers=stranger)).status_code == 403

    granted = await world.agent_token(orchestrator, ["mission.orchestrate"], uuid.UUID(project_id))
    planning_only = await _transition(world, project_id, "cancelled", reason="no", headers=granted)
    assert planning_only.status_code == 403  # cancelling is Marcelo's
    unblocked_pause = await _transition(world, project_id, "paused", reason="tired", headers=granted)
    assert unblocked_pause.json()["detail"]["code"] == "ORCHESTRATOR_PAUSE_ONLY_WHEN_BLOCKED"
    started = await _transition(world, project_id, "active", headers=granted)
    assert started.status_code == 200 and started.json()["project_status"] == "active"
    async with AsyncSessionLocal() as db:
        event = (await db.execute(select(AuditEvent).where(
            AuditEvent.entity_id == uuid.UUID(project_id), AuditEvent.event_type == "mission_ready_to_active"
        ))).scalar_one()
        assert event.actor != "system" and event.payload["principal_type"] == "agent"
        assert event.payload["delegation_id"] is not None


@pytest.mark.asyncio
async def test_orchestrator_capacity_blocks_start(world):
    orchestrator = await world.agent("busy")
    for _ in range(2):
        other = await world.create_mission(orchestrator_agent_id=orchestrator)
        await _force(other["project_id"], state="active")
    mission, _, _ = await _prepared_mission(world)
    await _force(mission["project_id"], state="ready", orchestrator_agent_id=orchestrator)
    response = await _transition(world, mission["project_id"], "active")
    assert response.status_code == 409 and _codes(response) == {"ORCHESTRATOR_AT_CAPACITY"}


@pytest.mark.asyncio
async def test_non_admin_user_cannot_act(world, auth_headers):
    mission = await world.create_mission()
    async with AsyncSessionLocal() as db:
        user = User(username=f"mission-plain-{world.tag}", hashed_password="x", is_admin=False)
        db.add(user)
        await db.commit()
        world.user_ids.append(user.id)
    from app.core.security import create_access_token
    headers = {"Authorization": f"Bearer {create_access_token(user.username)}"}
    response = await _transition(world, mission["project_id"], "cancelled", reason="x", headers=headers)
    assert response.status_code == 403 and response.json()["detail"]["code"] == "MISSION_ADMIN_ONLY"


# ---------------------------------------------------------------------------
# §3.1 planning pipeline
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_planning_stage_exit_conditions(world):
    mission = await world.create_mission()
    project_id = mission["project_id"]
    orchestrator = uuid.UUID(mission["orchestrator_agent_id"])
    async with world.client() as client:
        not_planning = await client.post(f"/api/v1/missions/{project_id}/planning:advance", json={
            "to": "auto_check", "reason": "go", "idempotency_key": uuid.uuid4().hex})
    assert not_planning.json()["detail"]["code"] == "MISSION_NOT_PLANNING"

    await _force(project_id, state="planning", planning_stage="draft_plan")
    key = uuid.uuid4().hex
    response = await _advance(world, project_id, "auto_check", key=key)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "PLANNING_EXIT_CONDITIONS_UNMET"
    assert _codes(response) == {"PLAN_DRAFT_MISSING", "NO_TASKS", "NO_CRITERIA", "DEADLINE_MISSING",
                                "BUDGET_MISSING", "RISK_LEVEL_MISSING", "REVIEW_LAYERS_MISSING",
                                "ENVIRONMENT_NOT_RECORDED"}

    # The refused attempt is recorded, and the same key replays it.
    async with AsyncSessionLocal() as db:
        decision = (await db.execute(select(MissionDecision).where(
            MissionDecision.mission_project_id == uuid.UUID(project_id)))).scalar_one()
        assert (decision.action, decision.status, decision.refusal_code) == (
            "advance_planning", "refused", "PLANNING_EXIT_CONDITIONS_UNMET")
    replay = await _advance(world, project_id, "auto_check", key=key)
    assert replay.status_code == 409 and replay.json()["detail"]["replayed"] is True
    reused = await _advance(world, project_id, "auto_check", key=key, reason="other words")
    assert reused.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    # Fill everything M0.0 can read: only the environment remains.
    async with world.client() as client:
        patched = await client.patch(f"/api/v1/missions/{project_id}", json={
            "expected_row_version": await _row_version(project_id), "risk_level": "medium",
            "required_review_layers": ["backend", "security"],
            "deadline_at": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(), "budget_limit": "50"})
    assert patched.status_code == 200, patched.text
    async with AsyncSessionLocal() as db:
        db.add(ProjectPlan(project_id=uuid.UUID(project_id), name="draft plan", status="draft"))
        await db.commit()
    executor = await world.agent("exec")
    task = await _task(project_id)
    await _assign(task.id, executor, await _member(project_id, executor))
    await _criterion(project_id, await world.agent("verifier"), task_ids=[task.id])
    response = await _advance(world, project_id, "auto_check")
    assert _codes(response) == {"ENVIRONMENT_NOT_RECORDED"}
    assert response.json()["detail"]["unmet"][0]["not_recorded"] is True

    # P2 auto check: reviewer independence and the environment prerequisites.
    await _force(project_id, planning_stage="auto_check")
    response = await _advance(world, project_id, "critical_review")
    assert _codes(response) == {"NO_INDEPENDENT_REVIEWER", "ENVIRONMENT_PREREQUISITES_NOT_RECORDED"}
    reviewer = await world.agent("rev")
    await _member(project_id, reviewer, role="reviewer", can_review=True)
    response = await _advance(world, project_id, "critical_review")
    assert _codes(response) == {"ENVIRONMENT_PREREQUISITES_NOT_RECORDED"}

    # Stages whose evidence has no table yet always refuse, naming why.
    expected = {
        "critical_review": ("consolidation", {"REVIEW_ARTIFACTS_NOT_RECORDED"}),
        "consolidation": ("cross_review", {"REVIEW_DISPOSITIONS_NOT_RECORDED"}),
        "cross_review": ("decisions", {"CROSS_REVIEWS_NOT_RECORDED"}),
        "decisions": ("application", {"FLAGGED_ITEMS_NOT_RECORDED"}),
        "application": ("baseline", {"ENVIRONMENT_PREREQUISITES_NOT_RECORDED",
                                     "APPLICATION_VERIFICATION_NOT_RECORDED"}),
    }
    for stage, (to, codes) in expected.items():
        await _force(project_id, planning_stage=stage)
        response = await _advance(world, project_id, to)
        assert response.status_code == 409 and _codes(response) == codes, stage

    # risk/layers are fixed after P1.
    async with world.client() as client:
        locked = await client.patch(f"/api/v1/missions/{project_id}", json={
            "expected_row_version": await _row_version(project_id), "risk_level": "low"})
    assert locked.status_code == 409 and locked.json()["detail"]["code"] == "PLANNING_FIXED_AFTER_P1"

    # The orchestrator conducts with its delegation; a stage is never left by an outsider.
    granted = await world.agent_token(orchestrator, ["mission.orchestrate"], uuid.UUID(project_id))
    by_agent = await _advance(world, project_id, "baseline", headers=granted)
    assert by_agent.status_code == 409 and by_agent.json()["detail"]["code"] == "PLANNING_EXIT_CONDITIONS_UNMET"
    stranger = await world.agent_token(await world.agent("x"), ["mission.orchestrate"], uuid.UUID(project_id))
    assert (await _advance(world, project_id, "baseline", headers=stranger)).status_code == 403


@pytest.mark.asyncio
async def test_planning_cannot_skip_decisions(world, monkeypatch):
    async def all_met(db, mission):
        return [], []

    monkeypatch.setattr(mission_routes, "planning_exit_conditions", all_met)
    mission = await world.create_mission()
    project_id = mission["project_id"]
    await _force(project_id, state="planning", planning_stage="draft_plan", risk_level="medium")

    skipping = await _advance(world, project_id, "critical_review")
    assert skipping.json()["detail"]["code"] == "PLANNING_STAGE_OUT_OF_ORDER"
    for to in ("auto_check", "critical_review", "consolidation"):
        assert (await _advance(world, project_id, to)).status_code == 200, to
    # Medium risk: cross review is mandatory, decisions can't be reached from consolidation.
    jump = await _advance(world, project_id, "decisions")
    assert jump.json()["detail"]["code"] == "PLANNING_STAGE_OUT_OF_ORDER"
    assert (await _advance(world, project_id, "cross_review")).status_code == 200
    skip_decisions = await _advance(world, project_id, "application")
    assert skip_decisions.status_code == 409
    assert skip_decisions.json()["detail"]["code"] == "PLANNING_STAGE_OUT_OF_ORDER"
    assert (await _advance(world, project_id, "decisions")).status_code == 200
    applied = await _advance(world, project_id, "application")
    assert applied.status_code == 200 and applied.json()["mission"]["planning_stage"] == "application"
    assert (await _advance(world, project_id, "baseline")).status_code == 200
    # baseline is left only by the governed baseline approval (§7), not by advance.
    beyond = await _advance(world, project_id, "baseline")
    assert beyond.json()["detail"]["code"] == "PLANNING_STAGE_OUT_OF_ORDER"

    # Low risk: consolidation -> decisions is allowed and recorded as a skip,
    # but consolidation -> application still skips decisions.
    await _force(project_id, planning_stage="consolidation", risk_level="low")
    assert (await _advance(world, project_id, "application")).json()["detail"]["code"] == (
        "PLANNING_STAGE_OUT_OF_ORDER")
    low = await _advance(world, project_id, "decisions")
    assert low.status_code == 200
    async with AsyncSessionLocal() as db:
        decision = await db.get(MissionDecision, uuid.UUID(low.json()["decision_id"]))
        assert decision.status == "applied" and decision.facts["cross_review_skipped"] is True
        assert decision.actor_type == "user" and decision.authority_source == "admin"


@pytest.mark.asyncio
async def test_auto_check_flags_missing_skill_for_executor_and_reviewer(world):
    mission = await world.create_mission()
    project_id = mission["project_id"]
    skill = await world.skill()
    inactive = await world.skill(approved=False)
    executor, reviewer = await world.agent("exec"), await world.agent("rev")
    task = await _task(project_id)
    await _assign(task.id, executor, await _member(project_id, executor))
    await _member(project_id, reviewer, role="reviewer", can_review=True)
    async with AsyncSessionLocal() as db:
        db.add(ProjectPlan(project_id=uuid.UUID(project_id), name="draft plan", status="draft"))
        await db.commit()

    # required_skill_ids is editable only while planning, and only with real skills.
    async with world.client() as client:
        locked = await client.patch(f"/api/v1/tasks/{task.id}", json={"required_skill_ids": [str(skill)]})
    assert locked.status_code == 409 and locked.json()["detail"]["code"] == "REQUIRED_SKILLS_LOCKED"
    await _force(project_id, state="planning", planning_stage="auto_check")
    async with world.client() as client:
        unknown = await client.patch(f"/api/v1/tasks/{task.id}", json={"required_skill_ids": [str(uuid.uuid4())]})
        saved = await client.patch(f"/api/v1/tasks/{task.id}",
                                   json={"required_skill_ids": [str(skill), str(inactive)]})
    assert unknown.status_code == 422 and unknown.json()["detail"]["code"] == "UNKNOWN_SKILL_IDS"
    assert saved.status_code == 200 and set(saved.json()["required_skill_ids"]) == {str(skill), str(inactive)}

    def gaps(response):
        return {(i["code"], i.get("skill_id")) for i in response.json()["detail"]["unmet"] if "skill_id" in i}

    response = await _advance(world, project_id, "critical_review")
    assert gaps(response) == {
        ("EXECUTOR_MISSING_SKILL", str(skill)), ("REVIEWER_MISSING_SKILL", str(skill)),
        ("SKILL_NOT_ACTIVE", str(inactive)),
        ("EXECUTOR_MISSING_SKILL", str(inactive)), ("REVIEWER_MISSING_SKILL", str(inactive)),
    }
    not_evaluated = response.json()["detail"]["not_evaluated"]
    assert [i["code"] for i in not_evaluated] == ["SKILL_RUNTIME_PRESENCE"]

    async with AsyncSessionLocal() as db:
        db.add(AgentSkill(agent_id=executor, skill_id=skill))
        await db.commit()
    assert gaps(await _advance(world, project_id, "critical_review")) == {
        ("REVIEWER_MISSING_SKILL", str(skill)), ("SKILL_NOT_ACTIVE", str(inactive)),
        ("EXECUTOR_MISSING_SKILL", str(inactive)), ("REVIEWER_MISSING_SKILL", str(inactive)),
    }
    async with AsyncSessionLocal() as db:
        db.add_all([AgentSkill(agent_id=reviewer, skill_id=skill)])
        (await db.get(ProjectTask, task.id)).required_skill_ids = [skill]
        await db.commit()
    response = await _advance(world, project_id, "critical_review")
    assert gaps(response) == set()
    # The only thing left is the environment, which no table records yet.
    assert _codes(response) == {"ENVIRONMENT_PREREQUISITES_NOT_RECORDED"}

    # A skill deleted after being required is a gap, never a silent pass.
    async with AsyncSessionLocal() as db:
        gone = uuid.uuid4()
        (await db.get(ProjectTask, task.id)).required_skill_ids = [skill, gone]
        await db.commit()
    assert ("SKILL_NOT_FOUND", str(gone)) in gaps(await _advance(world, project_id, "critical_review"))


# ---------------------------------------------------------------------------
# Migration (runs Alembic for real; always ends at head)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_existing_members_reviews_preserved(world):
    project = await world.common_project()
    project_id = uuid.UUID(project["id"])
    executor, reviewer = await world.agent("exec"), await world.agent("rev")
    executor_membership = await _member(project_id, executor)
    reviewer_membership = await _member(project_id, reviewer, role="reviewer", can_review=True)
    task = await _task(project_id)
    async with AsyncSessionLocal() as db:
        execution = TaskExecution(task_id=task.id, status="completed")
        db.add(execution)
        await db.flush()
        review = TaskExecutionReview(execution_id=execution.id, reviewer_membership_id=reviewer_membership,
                                     status="approved", score=90, feedback="ok")
        db.add(review)
        await db.commit()
        review_id = review.id

    def snapshot_sql():
        return text(
            "SELECT m.id, m.role, m.status, m.can_review, r.id, r.status, r.score, r.feedback "
            "FROM company.project_agent_memberships m "
            "LEFT JOIN company.task_execution_reviews r ON r.reviewer_membership_id = m.id "
            f"WHERE m.project_id = '{project_id}' ORDER BY m.id")

    async with AsyncSessionLocal() as db:
        before = (await db.execute(snapshot_sql())).all()
    leftover = await _mission_count()
    assert leftover == 0, "another mission exists in the test database; the downgrade would refuse"
    try:
        down = _alembic("downgrade", PRE_M0_REVISION)
        assert down.returncode == 0, down.stderr
    finally:
        up = _alembic("upgrade", "head")
        assert up.returncode == 0, up.stderr
    async with AsyncSessionLocal() as db:
        after = (await db.execute(snapshot_sql())).all()
    assert after == before and {executor_membership, reviewer_membership} <= {row[0] for row in after}
    assert review_id in {row[4] for row in after}


async def _mission_count() -> int:
    async with AsyncSessionLocal() as db:
        return await db.scalar(text("SELECT count(*) FROM company.projects WHERE project_type = 'mission'"))


@pytest.mark.asyncio
async def test_migration_upgrade_downgrade_roundtrip(world):
    assert await _mission_count() == 0
    mission = await world.create_mission()
    try:
        refused = _alembic("downgrade", PRE_M0_REVISION)
        assert refused.returncode != 0 and "Refusing to downgrade M0.0" in refused.stderr
        assert "f2c7a4e9b1d3" in _alembic("current").stdout

        async with AsyncSessionLocal() as db:
            await db.execute(text(f"DELETE FROM company.audit_events WHERE entity_id = '{mission['project_id']}'"))
            await db.execute(text(
                f"DELETE FROM company.project_missions WHERE project_id = '{mission['project_id']}'"))
            await db.execute(text(f"DELETE FROM company.projects WHERE id = '{mission['project_id']}'"))
            await db.commit()
        down = _alembic("downgrade", PRE_M0_REVISION)
        assert down.returncode == 0, down.stderr
        async with AsyncSessionLocal() as db:
            check = await db.scalar(text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'ck_projects_project_type'"))
            assert "mission" not in check and "maintenance" in check
            assert await db.scalar(text("SELECT to_regclass('company.project_missions')")) is None
    finally:
        up = _alembic("upgrade", "head")
        assert up.returncode == 0, up.stderr
    async with AsyncSessionLocal() as db:
        check = await db.scalar(text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'ck_projects_project_type'"))
        assert "mission" in check
    assert (await world.create_mission())["state"] == "draft"

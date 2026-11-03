"""M0.0b mission planning records (docs/architecture/MCP_MISSION_TOOLS_SPEC.md §2.6).

A mission walks P1 -> baseline on real records only; each exit condition
refuses without its record and passes with it; the reviewer, verifier and
Marcelo are always the authenticated principal. Runs only against the
isolated test database; every test removes what it created. The migration
test round-trips this revision only and leaves the database where it found it.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app.core.mission import NOT_RECORDED_CONDITIONS
from app.core.plan_baseline import create_mission_baseline
from app.db.base import AsyncSessionLocal
from app.db.models.artifact import Artifact, ArtifactStatus, ArtifactType, ArtifactVersion, ArtifactVersionStatus
from app.db.models.governance import AuditEvent
from app.db.models.mission import ProjectMission
from app.db.models.project import PlanBaseline, ProjectPlan
from app.db.models.task import TaskExecutionTarget
from app.tests.test_mission_base import (  # noqa: F401  (_clean_stale_mission_fixtures is an autouse fixture)
    World,
    _alembic,
    _assign,
    _brief,
    _clean_stale_mission_fixtures,
    _codes,
    _criterion,
    _force,
    _member,
    _row_version,
    _task,
    _transition,
)

REVISION = "c5a8e2f71d04"
DOWN_REVISION = "d3f7a1c9e2b5"
REVIEW = "mission.plan.review"


async def _drop_plans(project_id) -> None:
    """Baselines hold their tasks RESTRICT: drop plans (and so baselines)
    before the world removes the tasks."""
    async with AsyncSessionLocal() as db:
        await db.execute(text("UPDATE company.project_missions SET current_baseline_id = NULL "
                              "WHERE project_id = :p"), {"p": str(project_id)})
        await db.execute(text("DELETE FROM company.project_plans WHERE project_id = :p"), {"p": str(project_id)})
        await db.commit()


@pytest_asyncio.fixture
async def world(admin_headers):
    w = World(admin_headers)
    w.mission_ids = []
    await w.setup()
    yield w
    for project_id in w.mission_ids:
        await _drop_plans(project_id)
    await w.cleanup()


async def _doc(world: World, checksum: str | None = None) -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        artifact = Artifact(name=f"mission-test-{world.tag}-doc-{uuid.uuid4().hex[:4]}",
                            artifact_type=ArtifactType.CONTEXT_BRIEF, status=ArtifactStatus.APPROVED)
        db.add(artifact)
        await db.flush()
        version = ArtifactVersion(artifact_id=artifact.id, version_number=1, status=ArtifactVersionStatus.FINAL,
                                  location_uri="docs/missions/test/REVIEW.md", checksum=checksum)
        db.add(version)
        await db.commit()
        return version.id


class Cast:
    """A mission in planning/draft_plan with everything M0.0 already read
    (risk, layers, deadline, budget, a task with executor and criterion) and
    the people of §2.6: a planner agent, the orchestrator and three reviewers."""

    async def build(self, world: World, risk="medium") -> "Cast":
        self.world = world
        mission = await world.create_mission(brief_artifact_id=str(await _brief(world)))
        self.project_id = mission["project_id"]
        world.mission_ids.append(self.project_id)
        pid = uuid.UUID(self.project_id)
        self.orchestrator = uuid.UUID(mission["orchestrator_agent_id"])
        async with world.client() as client:
            patched = await client.patch(f"/api/v1/missions/{self.project_id}", json={
                "expected_row_version": await _row_version(self.project_id), "risk_level": risk,
                "required_review_layers": ["backend", "security"],
                "deadline_at": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
                "budget_limit": "50"})
        assert patched.status_code == 200, patched.text
        await _force(self.project_id, state="planning", planning_stage="draft_plan")
        executor = await world.agent("exec")
        self.task = await _task(self.project_id)
        await _assign(self.task.id, executor, await _member(self.project_id, executor))
        await _criterion(self.project_id, await world.agent("verifier"), task_ids=[self.task.id])

        self.orch = await world.agent_token(self.orchestrator, ["mission.orchestrate", REVIEW], pid)
        async with AsyncSessionLocal() as db:  # the orchestrator's coordinator membership can also review
            await db.execute(text("UPDATE company.project_agent_memberships SET can_review = true "
                                  "WHERE project_id = :p AND agent_id = :a"),
                             {"p": self.project_id, "a": str(self.orchestrator)})
            await db.commit()
        self.planner = await world.agent("planner")
        await _member(self.project_id, self.planner, role="reviewer", can_review=True)
        self.planner_h = await world.agent_token(self.planner, ["mission.plan.submit", REVIEW], pid)
        self.reviewers = []
        for label in ("r1", "r2", "r3"):
            agent = await world.agent(label)
            await _member(self.project_id, agent, role="reviewer", can_review=True)
            self.reviewers.append((agent, await world.agent_token(agent, [REVIEW], pid)))
        return self

    def url(self, suffix: str) -> str:
        return f"/api/v1/missions/{self.project_id}{suffix}"

    async def post(self, suffix: str, body: dict, headers=None):
        async with self.world.client(headers) as client:
            return await client.post(self.url(suffix), json=body)

    async def advance(self, to: str, headers=None):
        async with self.world.client(headers) as client:
            return await client.post(self.url("/planning:advance"), json={
                "to": to, "reason": "next stage", "idempotency_key": uuid.uuid4().hex})

    async def register_plan(self, headers=None) -> str:
        response = await self.post("/plans", {"name": f"plan {uuid.uuid4().hex[:4]}"}, headers or self.planner_h)
        assert response.status_code == 201, response.text
        return response.json()["project_plan_id"]

    async def review(self, plan_id, kind, layer, headers, **extra):
        return await self.post("/plan-reviews", {"project_plan_id": plan_id, "kind": kind, "layer": layer,
                                                 "artifact_version_id": str(await _doc(self.world)), **extra},
                               headers)


def _code(response) -> str:
    return response.json()["detail"]["code"]


@pytest.mark.asyncio
async def test_mission_walks_p1_to_baseline_on_real_records(world):
    cast = await Cast().build(world)
    (r1, r1_h), (r2, r2_h), (_r3, r3_h) = cast.reviewers
    refusals = []

    async def refused(to, *codes):
        response = await cast.advance(to)
        assert response.status_code == 409, response.text
        refusals.append(response.json()["detail"])
        assert set(codes) <= _codes(response), (to, _codes(response))
        return _codes(response)

    async def advanced(to):
        response = await cast.advance(to)
        assert response.status_code == 200, (to, response.text)
        refusals.append(response.json())

    # P1: no plan and no task environment.
    await refused("auto_check", "PLAN_DRAFT_MISSING", "TASK_ENVIRONMENT_MISSING")
    # A draft created outside the mission route has no author: fail closed.
    async with AsyncSessionLocal() as db:
        db.add(ProjectPlan(project_id=uuid.UUID(cast.project_id), name="generic draft", status="draft"))
        await db.commit()
    await refused("auto_check", "PLAN_VERSION_NOT_REGISTERED")
    # A reviewer with no mission.plan.submit cannot register a version.
    assert (await cast.post("/plans", {"name": "x"}, r1_h)).status_code == 403
    plan_id = await cast.register_plan()
    async with world.client() as client:
        bad = await client.patch(f"/api/v1/tasks/{cast.task.id}", json={"target_environment": "staging"})
        env = await client.patch(f"/api/v1/tasks/{cast.task.id}", json={"target_environment": "test"})
    assert bad.status_code == 422
    assert env.status_code == 200 and env.json()["target_environment"] == "test"
    await advanced("auto_check")

    # P2: prerequisites recorded and publish targets in the task's environment.
    async with AsyncSessionLocal() as db:
        db.add(TaskExecutionTarget(task_id=cast.task.id, kind="publish", target_key="production:site"))
        await db.commit()
    await refused("critical_review", "TASK_ENVIRONMENT_PREREQUISITES_MISSING", "PUBLISH_TARGET_ENVIRONMENT_MISMATCH")
    async with world.client() as client:
        none = await client.patch(f"/api/v1/tasks/{cast.task.id}", json={"environment_prerequisites": []})
    assert none.status_code == 200 and none.json()["environment_prerequisites"] == []
    codes = await refused("critical_review", "PUBLISH_TARGET_ENVIRONMENT_MISMATCH")
    assert "TASK_ENVIRONMENT_PREREQUISITES_MISSING" not in codes
    async with AsyncSessionLocal() as db:
        await db.execute(text("UPDATE company.task_execution_targets SET target_key = 'test:site' "
                              "WHERE task_id = :t"), {"t": str(cast.task.id)})
        await db.commit()
    await advanced("critical_review")

    # P3: one opinion per required layer by a non-planner, or Marcelo's waiver.
    await refused("consolidation", "LAYER_REVIEW_MISSING")
    assert _code(await cast.review(plan_id, "layer", "backend", cast.planner_h)) == "REVIEWER_IS_PLANNER"
    assert _code(await cast.review(plan_id, "layer", "backend", cast.orch)) == "REVIEWER_IS_PLANNER"
    assert _code(await cast.review(plan_id, "layer", "frontend", r1_h)) == "LAYER_NOT_REQUIRED"
    assert _code(await cast.review(plan_id, "cross", "backend", r1_h)) == "PLANNING_STAGE_MISMATCH"
    assert _code(await cast.review(plan_id, "layer", "backend", world.admin)) == "REVIEW_REQUIRES_AGENT"
    # No agent writes with another's identity: the reviewer is never a body field.
    forged = await cast.review(plan_id, "layer", "backend", r1_h, reviewer_agent_id=str(r2))
    assert forged.status_code == 422
    review = await cast.review(plan_id, "layer", "backend", r1_h)
    assert review.status_code == 201, review.text
    assert review.json()["reviewer_agent_id"] == str(r1)
    assert _code(await cast.review(plan_id, "layer", "backend", r1_h)) == "REVIEW_ALREADY_RECORDED"
    review_id = review.json()["id"]
    await refused("consolidation", "LAYER_REVIEW_MISSING")
    waiver = {"project_plan_id": plan_id, "layer": "security", "reason": "no security surface in this plan"}
    assert _code(await cast.post("/review-waivers", waiver, cast.orch)) == "MARCELO_DECISION_REQUIRES_ADMIN"
    assert (await cast.post("/review-waivers", waiver)).status_code == 201

    items = {}
    for label, flagged in (("a", False), ("b", True), ("c", False), ("d", False)):
        created = await cast.post(f"/plan-reviews/{review_id}/items",
                                  {"text": f"point {label}", "needs_marcelo_decision": flagged}, r1_h)
        assert created.status_code == 201, created.text
        items[label] = created.json()["id"]
    assert _code(await cast.post(f"/plan-reviews/{review_id}/items", {"text": "x"}, r2_h)) == "NOT_REVIEW_AUTHOR"
    await advanced("consolidation")

    # P4: every item disposed, with a reason.
    await refused("cross_review", "ITEM_WITHOUT_DISPOSITION")
    assert len([c for c in refusals[-1]["unmet"] if c["code"] == "ITEM_WITHOUT_DISPOSITION"]) == 4
    dispose = "/review-items/{}:dispose"
    assert (await cast.post(dispose.format(items["a"]), {"disposition": "accept", "reason": "ok"}, r1_h)
            ).status_code == 403
    blank = await cast.post(dispose.format(items["a"]), {"disposition": "accept", "reason": "   "}, cast.orch)
    assert blank.status_code == 422
    for label, disposition in (("a", "accept"), ("b", "adjust"), ("c", "accept")):
        done = await cast.post(dispose.format(items[label]), {"disposition": disposition, "reason": "fine"},
                               cast.orch)
        assert done.status_code == 200, done.text
    await refused("cross_review", "ITEM_WITHOUT_DISPOSITION")  # d is still open
    assert (await cast.post(dispose.format(items["d"]), {"disposition": "reject", "reason": "out of scope"})
            ).status_code == 200
    cleared = await cast.post(dispose.format(items["b"]), {"disposition": "adjust", "reason": "fine",
                                                           "needs_marcelo_decision": False}, cast.orch)
    assert _code(cleared) == "FLAG_CANNOT_BE_CLEARED"
    await advanced("cross_review")

    # P5: two cross reviews, different reviewers on different layers, neither a planner.
    await refused("decisions", "CROSS_REVIEWS_INSUFFICIENT")
    assert (await cast.review(plan_id, "cross", "backend", r1_h)).status_code == 201
    assert (await cast.review(plan_id, "cross", "backend", r2_h)).status_code == 201
    await refused("decisions", "CROSS_REVIEWS_INSUFFICIENT")  # same layer
    assert _code(await cast.review(plan_id, "cross", "security", cast.planner_h)) == "REVIEWER_IS_PLANNER"
    assert (await cast.review(plan_id, "cross", "security", r2_h)).status_code == 201
    await advanced("decisions")

    # P6: every flagged item has Marcelo's decision, by admin JWT only.
    await refused("application", "FLAGGED_ITEM_UNDECIDED")
    decide = "/review-items/{}:decide"
    by_agent = await cast.post(decide.format(items["b"]), {"decision": "adjust", "reason": "yes"}, cast.orch)
    assert by_agent.status_code == 403 and _code(by_agent) == "MARCELO_DECISION_REQUIRES_ADMIN"
    assert _code(await cast.post(decide.format(items["a"]), {"decision": "accept", "reason": "x"})) == (
        "ITEM_NOT_FLAGGED")
    decided = await cast.post(decide.format(items["b"]), {"decision": "adjust", "reason": "adjust the schedule"})
    assert decided.status_code == 200 and decided.json()["marcelo_decision"] == "adjust"
    assert _code(await cast.post(dispose.format(items["b"]), {"disposition": "reject", "reason": "no"},
                                 cast.orch)) == "ITEM_ALREADY_DECIDED"
    await advanced("application")

    # P7: the validator again + a confirmed sampled verification by a non-planner.
    await refused("baseline", "APPLICATION_VERIFICATION_MISSING")
    sample = [items["a"], items["b"], items["c"]]
    verify = {"project_plan_id": plan_id, "sampled_item_ids": sample, "result": "confirmed"}
    assert _code(await cast.post("/plan-verifications", verify, cast.planner_h)) == "REVIEWER_IS_PLANNER"
    assert _code(await cast.post("/plan-verifications", {**verify, "sampled_item_ids": [items["d"], *sample]},
                                 r2_h)) == "SAMPLE_ITEM_INVALID"
    assert _code(await cast.post("/plan-verifications", {**verify, "sampled_item_ids": sample[:2]}, r2_h)) == (
        "SAMPLE_TOO_SMALL")
    assert (await cast.post("/plan-verifications", {**verify, "result": "discrepancies"}, r2_h)).status_code == 201
    await refused("baseline", "APPLICATION_VERIFICATION_DISCREPANCIES")
    assert (await cast.post("/plan-verifications", verify, r3_h)).status_code == 201
    await advanced("baseline")

    # The baseline itself: M0.2b's governed approval, here its core function.
    async with AsyncSessionLocal() as db:
        mission = await db.get(ProjectMission, uuid.UUID(cast.project_id))
        plan = await db.get(ProjectPlan, uuid.UUID(plan_id))
        plan.status = "approved"
        baseline = await create_mission_baseline(db, mission, plan, [cast.task.id], name="b1", actor="test")
        await db.commit()
        assert (await db.get(ProjectMission, mission.project_id)).current_baseline_id == baseline.id
        assert (await db.get(PlanBaseline, baseline.id)).project_plan_id == plan.id

    # Nothing passed for lack of data, and every write is audited.
    assert NOT_RECORDED_CONDITIONS == {}
    assert not any(u.get("not_recorded") for r in refusals for u in r.get("unmet", []))
    async with AsyncSessionLocal() as db:
        events = set((await db.execute(select(AuditEvent.event_type).where(
            AuditEvent.entity_type == "mission", AuditEvent.entity_id == uuid.UUID(cast.project_id)))).scalars())
    assert {"mission_plan_version_registered", "mission_task_environment_set", "mission_plan_review_recorded",
            "mission_review_waived", "mission_review_item_recorded", "mission_review_item_disposed",
            "mission_review_item_decided", "mission_plan_verification_recorded"} <= events
    async with world.client() as client:
        records = (await client.get(cast.url("/planning-records"))).json()
    assert records["author"]["author_id"] == str(cast.planner)
    assert len(records["reviews"]) == 4 and len(records["items"]) == 4 and len(records["verifications"]) == 2


@pytest.mark.asyncio
async def test_new_plan_version_voids_old_records(world):
    cast = await Cast().build(world)
    (_r1, r1_h), (_r2, r2_h), _ = cast.reviewers
    old_plan = await cast.register_plan()
    await _force(cast.project_id, planning_stage="critical_review")
    assert (await cast.review(old_plan, "layer", "backend", r1_h)).status_code == 201
    assert (await cast.review(old_plan, "layer", "security", r2_h)).status_code == 201
    assert (await cast.advance("consolidation")).status_code == 200

    new_plan = await cast.register_plan(cast.orch)
    async with AsyncSessionLocal() as db:
        assert (await db.get(ProjectPlan, uuid.UUID(old_plan))).status == "superseded"
        mission = await db.get(ProjectMission, uuid.UUID(cast.project_id))
        assert mission.planning_stage == "draft_plan"
    # Old opinions don't count for the new version, and can't be written against it.
    await _force(cast.project_id, planning_stage="critical_review")
    response = await cast.advance("consolidation")
    missing = {u["layer"] for u in response.json()["detail"]["unmet"] if u["code"] == "LAYER_REVIEW_MISSING"}
    assert missing == {"backend", "security"}
    assert _code(await cast.review(old_plan, "layer", "backend", r1_h)) == "PLAN_VERSION_NOT_CURRENT"
    assert (await cast.review(new_plan, "layer", "backend", r1_h)).status_code == 201
    # Cumulative: leaving a later stage re-checks the earlier records on the new version.
    await _force(cast.project_id, planning_stage="application")
    codes = _codes(await cast.advance("baseline"))
    assert {"LAYER_REVIEW_MISSING", "CROSS_REVIEWS_INSUFFICIENT", "APPLICATION_VERIFICATION_MISSING"} <= codes


@pytest.mark.asyncio
async def test_low_risk_skips_cross_reviews_only(world):
    cast = await Cast().build(world, risk="low")
    (_r1, r1_h), (_r2, r2_h), _ = cast.reviewers
    plan_id = await cast.register_plan()
    await _force(cast.project_id, planning_stage="critical_review")
    for layer, headers in (("backend", r1_h), ("security", r2_h)):
        assert (await cast.review(plan_id, "layer", layer, headers)).status_code == 201
    await _force(cast.project_id, planning_stage="consolidation")
    skipped = await cast.advance("decisions")
    assert skipped.status_code == 200, skipped.text


@pytest.mark.asyncio
async def test_task_environment_written_only_while_planning(world):
    mission = await world.create_mission()
    world.mission_ids.append(mission["project_id"])
    task = await _task(mission["project_id"])
    async with world.client() as client:
        locked = await client.patch(f"/api/v1/tasks/{task.id}", json={"target_environment": "test"})
    assert locked.status_code == 409 and _code(locked) == "TASK_ENVIRONMENT_LOCKED"
    common = await world.common_project()
    free = await _task(common["id"])
    async with world.client() as client:
        saved = await client.patch(f"/api/v1/tasks/{free.id}", json={
            "target_environment": "production", "environment_prerequisites": ["database at head"]})
    assert saved.status_code == 200 and saved.json()["environment_prerequisites"] == ["database at head"]


@pytest.mark.asyncio
async def test_dossier_gates_awaiting_acceptance(world):
    mission = await world.create_mission()
    project_id = mission["project_id"]
    world.mission_ids.append(project_id)
    good = "a" * 64
    doc = str(await _doc(world, checksum=f"sha256:{good}"))
    async with world.client() as client:
        early = await client.post(f"/api/v1/missions/{project_id}/dossier",
                                  json={"artifact_version_id": doc, "file_sha256": good})
    assert _code(early) == "MISSION_NOT_VERIFYING"

    await _force(project_id, state="verifying", state_changed_at=datetime.now(timezone.utc))
    response = await _transition(world, project_id, "awaiting_acceptance")
    assert response.status_code == 409 and "DOSSIER_MISSING" in _codes(response)
    assert not any(u.get("not_recorded") for u in response.json()["detail"]["unmet"])

    stranger = await world.agent_token(await world.agent("x"), ["mission.dossier.register"], uuid.UUID(project_id))
    async with world.client(stranger) as client:
        refused = await client.post(f"/api/v1/missions/{project_id}/dossier",
                                    json={"artifact_version_id": doc, "file_sha256": good})
    assert refused.status_code == 403
    async with world.client() as client:
        mismatch = await client.post(f"/api/v1/missions/{project_id}/dossier",
                                     json={"artifact_version_id": doc, "file_sha256": "b" * 64})
        registered = await client.post(f"/api/v1/missions/{project_id}/dossier",
                                       json={"artifact_version_id": doc, "file_sha256": good.upper()})
    assert _code(mismatch) == "DOSSIER_HASH_MISMATCH"
    assert registered.status_code == 201 and registered.json()["file_sha256"] == good
    assert (await _transition(world, project_id, "awaiting_acceptance")).status_code == 200

    # A dossier from an earlier verifying stay doesn't count for a new one.
    await _force(project_id, state="verifying", state_changed_at=datetime.now(timezone.utc) + timedelta(seconds=1))
    assert "DOSSIER_MISSING" in _codes(await _transition(world, project_id, "awaiting_acceptance"))


@pytest.mark.asyncio
async def test_migration_roundtrip_own_revision_only():
    before = _alembic("current")
    assert REVISION in before.stdout, before.stdout + before.stderr

    async def tables() -> set[str]:
        async with AsyncSessionLocal() as db:
            return set((await db.execute(text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'company' "
                "AND table_name IN ('mission_plan_versions', 'mission_plan_reviews', 'mission_review_waivers', "
                "'mission_review_items', 'mission_plan_verifications', 'mission_dossiers')"))).scalars())

    down = _alembic("downgrade", DOWN_REVISION)
    try:
        assert down.returncode == 0, down.stderr
        assert DOWN_REVISION in _alembic("current").stdout
        assert await tables() == set()
    finally:
        up = _alembic("upgrade", REVISION)
    assert up.returncode == 0, up.stderr
    assert REVISION in _alembic("current").stdout
    assert len(await tables()) == 6

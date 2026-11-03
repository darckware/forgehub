"""Initial M0 rehearsal: test environment and mission membership guards."""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.core.config import assert_test_database_target, settings
from app.core.mission_documents import project_slug
from app.mcp import factory_server
from app.db.base import AsyncSessionLocal
from app.db.models.mission import MissionPlanSubmission, ProjectMission
from app.db.models.personal import PersonalNote
from app.db.models.product import Product
from app.db.models.project import PlanBaseline
from app.db.models.task import TaskExecutionTarget
from app.tests.test_mission_base import _transition
from app.tests.test_mission_plan_approval import _remove_plan_approvals
from app.tests.test_mission_planning_records import Cast, world as planning_source  # noqa: F401,F811
from app.tests.test_mission_dispatch import (
    _assign, _audits, _dispatch, _latest_execution, _report, runner, world,  # noqa: F401,F811
)
from app.tests.test_mission_dispatch_context import _canary
from app.tests.test_mission_base import _member
from app.tests.test_task_baseline_guard import _code, _mission
from app.tests.test_mission_mcp import _key, docs_root, mcp_as, mw  # noqa: F401


@pytest.mark.asyncio
async def test_mission_rehearsal_membership(mw, mcp_as, docs_root, monkeypatch):  # noqa: F811
    assert settings.ENVIRONMENT == "test"
    assert_test_database_target(settings.POSTGRES_HOST, settings.POSTGRES_PORT, settings.POSTGRES_DB,
                                settings.POSTGRES_USER)
    monkeypatch.setattr(settings, "MISSION_TOOLS_ENABLED", True)
    product_id, version_id = await mw.version()
    coordinator = await mw.agent("coordinator", runtime="hermes")
    executor = await mw.agent("executor", runtime="codex")
    reviewer = await mw.agent("reviewer", runtime="agy")
    documentation = await mw.agent("documentation", runtime="hermes")
    mcp_as(await mw.token(coordinator, product_id=product_id))
    name = f"mission-test-{uuid.uuid4().hex}"
    created = await factory_server.create_internal_project(str(version_id), name, _key())
    assert created["mission_state"] == "draft"
    project_id = created["project_id"]
    mcp_as(await mw.token(coordinator, project_id=uuid.UUID(project_id)))
    for operation, code in (
        ({"op": "add", "agent_id": str(executor), "role": "developer", "can_approve": True},
         "CAN_APPROVE_NOT_FOR_AGENTS"),
        ({"op": "add", "agent_id": str(documentation), "role": "developer"},
         "CODE_ROLE_REQUIRES_EXTERNAL_RUNTIME"),
        ({"op": "release", "agent_id": str(coordinator)}, "LAST_COORDINATOR"),
    ):
        with pytest.raises(factory_server.FactoryError, match=code):
            await factory_server.manage_project_members(project_id, [operation], _key())
    members = await factory_server.manage_project_members(project_id, [
        {"op": "add", "agent_id": str(executor), "role": "developer"},
        {"op": "add", "agent_id": str(reviewer), "role": "reviewer", "can_review": True},
        {"op": "add", "agent_id": str(documentation), "role": "documentation"},
    ], _key())
    assert members["replayed"] is False

    # Step 7: the documentation member attaches a file inside this mission.
    slug = project_slug(name)
    doc_path = f"missions/{slug}/notes.md"
    path = docs_root / doc_path
    path.parent.mkdir(parents=True)
    path.write_text("Rehearsal notes", encoding="utf-8")
    mcp_as(await mw.token(documentation, project_id=uuid.UUID(project_id)))
    attached = await factory_server.attach_project_document(project_id, "project", project_id, doc_path, _key())
    assert attached["link_created"] is True
    with pytest.raises(factory_server.FactoryError, match="DOC_PATH_NOT_ALLOWED"):
        await factory_server.attach_project_document(project_id, "project", project_id,
                                                     f"missions/{slug}/../{slug}/notes.md", _key())


@pytest_asyncio.fixture
async def planning_world(planning_source):  # noqa: F811
    return planning_source


@pytest.mark.asyncio
async def test_rehearsal_step3_planning_to_active(planning_world, monkeypatch):  # noqa: F811
    monkeypatch.setattr(settings, "MISSION_TOOLS_ENABLED", True)
    world = planning_world  # noqa: F811
    cast = await Cast().build(world)
    (_, r1_h), (_, r2_h), (_, r3_h) = cast.reviewers
    try:
        async def advanced(to):
            response = await cast.advance(to)
            assert response.status_code == 200, (to, response.text)

        plan_id = await cast.register_plan()
        async with world.client() as client:
            env = await client.patch(f"/api/v1/tasks/{cast.task.id}", json={
                "target_environment": "test", "environment_prerequisites": []})
        assert env.status_code == 200, env.text
        await advanced("auto_check")
        async with AsyncSessionLocal() as db:
            db.add(TaskExecutionTarget(task_id=cast.task.id, kind="publish", target_key="test:site"))
            await db.commit()
        await advanced("critical_review")
        review = await cast.review(plan_id, "layer", "backend", r1_h)
        assert review.status_code == 201, review.text
        waiver = {"project_plan_id": plan_id, "layer": "security", "reason": "no security surface in this plan"}
        assert (await cast.post("/review-waivers", waiver)).status_code == 201
        items = {}
        for label, flagged in (("a", False), ("b", True), ("c", False), ("d", False)):
            created = await cast.post(f"/plan-reviews/{review.json()['id']}/items",
                                      {"text": f"point {label}", "needs_marcelo_decision": flagged}, r1_h)
            assert created.status_code == 201, created.text
            items[label] = created.json()["id"]
        await advanced("consolidation")
        for label, disposition in (("a", "accept"), ("b", "adjust"), ("c", "accept"), ("d", "reject")):
            done = await cast.post(f"/review-items/{items[label]}:dispose",
                                   {"disposition": disposition, "reason": "fine"}, cast.orch)
            assert done.status_code == 200, done.text
        await advanced("cross_review")
        assert (await cast.review(plan_id, "cross", "backend", r1_h)).status_code == 201
        assert (await cast.review(plan_id, "cross", "security", r2_h)).status_code == 201
        await advanced("decisions")
        decided = await cast.post(f"/review-items/{items['b']}:decide",
                                  {"decision": "adjust", "reason": "adjust the schedule"})
        assert decided.status_code == 200, decided.text
        await advanced("application")
        verify = {"project_plan_id": plan_id, "sampled_item_ids": [items[x] for x in ("a", "b", "c")],
                  "result": "confirmed"}
        assert (await cast.post("/plan-verifications", verify, r3_h)).status_code == 201
        await advanced("baseline")
        async with AsyncSessionLocal() as db:
            mission = await db.get(ProjectMission, uuid.UUID(cast.project_id))
            assert mission.planning_stage == "baseline"

        submitted = await cast.post("/plans:submit", {"task_ids": [str(cast.task.id)],
                                                        "idempotency_key": _key()}, cast.planner_h)
        assert submitted.status_code == 201, submitted.text
        request_id = submitted.json()["approval_request_id"]
        url = f"/api/v1/governed/approval-requests/{request_id}:decide"
        body = {"decision": "approved", "comments": "ok", "idempotency_key": _key()}
        orchestrator_headers = await world.agent_token(
            cast.orchestrator, ["governance.approval.decide"], uuid.UUID(cast.project_id))
        async with world.client(orchestrator_headers) as client:
            refused = await client.post(url, json=body)
        assert refused.status_code in (403, 409), refused.text
        async with world.client() as client:
            approved = await client.post(url, json=body)
        assert approved.status_code == 200, approved.text
        async with AsyncSessionLocal() as db:
            mission = await db.get(ProjectMission, uuid.UUID(cast.project_id))
            baseline = await db.get(PlanBaseline, mission.current_baseline_id)
            submission = await db.get(MissionPlanSubmission, uuid.UUID(request_id))
            assert baseline and baseline.superseded_at is None and baseline.content_hash
            assert submission.baseline_id == baseline.id and submission.plan_hash
        for state in ("ready", "active"):
            response = await _transition(world, cast.project_id, state)
            assert response.status_code == 200, response.text
        assert response.json()["state"] == "active"
    finally:
        await _remove_plan_approvals([cast.project_id], [cast.task.id])


@pytest.mark.asyncio
async def test_rehearsal_step4_5_dispatch_and_report(world, runner, tmp_path, monkeypatch):  # noqa: F811
    mission = await _mission(world)
    task = await mission.task("rehearsal dispatch")
    reviewer = await world.agent("reviewer")
    await _member(mission.project_id, reviewer, role="reviewer", can_review=True)
    await mission.baseline([task.id])
    maia, lara, kb = (_canary(kind) for kind in ("MAIA", "LARA", "KB"))
    note_id = None
    try:
        async with AsyncSessionLocal() as db:
            note = PersonalNote(title="rehearsal fictitious note", content=f"recado {maia}")
            db.add(note)
            product = await db.get(Product, world.product_id)
            product.darckware_client_name = lara
            await db.commit()
            note_id = note.id
        kb_file = tmp_path / "knowledge_base" / "fixture.md"
        kb_file.parent.mkdir(parents=True)
        kb_file.write_text(f"KB fixture {kb}", encoding="utf-8")

        assigned = await _assign(world, mission, task.id, mission.executor)
        assert assigned.status_code in (200, 201), assigned.text
        dispatched = await _dispatch(world, task.id)
        assert dispatched.status_code in (200, 201), dispatched.text
        assert all(canary not in runner.prompts[-1] for canary in (maia, lara, kb))
        audits = await _audits(task.id, "task.dispatched")
        assert audits and audits[-1].payload["context_manifest"]
        again = await _dispatch(world, task.id)
        assert again.status_code == 409 and _code(again) == "TASK_RUN_IN_FLIGHT", again.text

        execution = await _latest_execution(task.id)
        executor = await world.agent_token(mission.executor, ["mission.execution.report"])
        evidence = [f"db:project:{mission.project_id}"]
        reported = await _report(world, task.id, execution.id, executor, evidence=evidence)
        assert reported.status_code == 200 and reported.json()["status"] == "reported", reported.text
        verified = await _report(world, task.id, execution.id, executor, evidence=evidence, status="verified")
        assert verified.status_code == 422, verified.text
        reviewer_token = await world.agent_token(reviewer, ["mission.execution.report"])
        refused = await _report(world, task.id, execution.id, reviewer_token, evidence=evidence)
        assert _code(refused) == "NOT_EXECUTOR", refused.text
        async with world.client() as client:
            done = await client.patch(f"/api/v1/tasks/{task.id}", json={"status": "done"})
        # COMPLETION_EXECUTION_NOT_VERIFIED is the first guard for a reported execution.
        assert done.status_code == 409 and _code(done) == "COMPLETION_EXECUTION_NOT_VERIFIED", done.text
    finally:
        if note_id is not None:
            async with AsyncSessionLocal() as db:
                await db.execute(text("DELETE FROM company.personal_notes WHERE id = :id"), {"id": note_id})
                await db.commit()

"""Tests for the Pipeline domain.

No migration has been generated yet for this domain (the wiring step
owns alembic/versions). These tests ensure this domain's own tables
exist via `Base.metadata.create_all(checkfirst=True)` against the real
`company_postgres` database (a harmless no-op if another process/agent
already created them with the same definition). Tables owned by OTHER
domains (`projects`, `artifacts`) are required as FK targets by
project_pipelines/pipeline_stage_required_artifacts -- this module
never creates or drops those tables; it only inserts/deletes the
specific stub rows it needs inside each fixture, so it never disturbs
real data left by other domains' tests.
"""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db.base import Base, engine
from app.db.models.pipeline import (  # noqa: F401  (registers tables on Base.metadata)
    PipelineStage,
    PipelineStageDependency,
    PipelineStageGate,
    PipelineStageRequiredArtifact,
    PipelineTemplate,
    PipelineTemplateRequiredArtifact,
    PipelineTemplateStage,
    ProjectPipeline,
)
from app.api.routes import pipeline as pipeline_routes
from app.main import app
from app.db.models.user import User

# main.py's wiring step (separate from this domain step) is responsible
# for adding `app.include_router(pipeline.router)` for real. Until that
# runs, the shared `app` instance has no pipeline routes mounted, so we
# include it here for the lifetime of the test process only -- this
# does not modify app/main.py on disk. Guard against double-registration
# in case the wiring step has already run by the time these tests execute.
if not any(getattr(r, "path", "").startswith("/api/v1/pipelines") for r in app.routes):
    app.include_router(pipeline_routes.router)

_OUR_TABLES = [
    PipelineTemplate.__table__,
    PipelineTemplateStage.__table__,
    PipelineTemplateRequiredArtifact.__table__,
    ProjectPipeline.__table__,
    PipelineStage.__table__,
    PipelineStageDependency.__table__,
    PipelineStageRequiredArtifact.__table__,
    PipelineStageGate.__table__,
]

@pytest_asyncio.fixture(scope="module", autouse=True)
async def _setup_schema():
    # checkfirst=True (the create_all default): only creates tables
    # that don't already exist, so this is a no-op if another domain
    # agent's process already created them with the same definition.
    # We intentionally never drop_all here -- these are this domain's
    # real, permanent tables, not test scaffolding.
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=_OUR_TABLES))
    from app.db.base import AsyncSessionLocal
    created_user = False
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.username == "test-suite"))).scalar_one_or_none()
        if user is None:
            session.add(User(
                username="test-suite", hashed_password="test-only-not-a-real-password",
                is_active=True, is_admin=True,
            ))
            await session.commit()
            created_user = True
    yield
    if created_user:
        async with AsyncSessionLocal() as session:
            user = (await session.execute(select(User).where(User.username == "test-suite"))).scalar_one_or_none()
            if user:
                await session.delete(user)
                await session.commit()


@pytest_asyncio.fixture
async def client(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=auth_headers) as ac:
        yield ac


@pytest_asyncio.fixture
async def project_id():
    """Insert one real `projects` row (Project domain's table) so the
    project_pipelines.project_id FK has a valid target, then delete
    only that row afterwards -- never touches other domains' data.

    `projects.product_version_id` is itself a required FK into
    `product_versions` (Product domain); a dedicated Product +
    ProductVersion row is created here (and deleted in teardown) rather
    than scavenging for a row left behind by another domain's tests --
    relying on incidental cross-module leftovers made this fixture
    order-dependent (it would `pytest.skip` whenever no other module
    happened to leave a row behind, e.g. once the Backlog/Project
    domain tests started cleaning up their own rows properly).
    """
    from sqlalchemy import text

    from app.db.base import AsyncSessionLocal
    from app.db.models.product import Product, ProductVersion

    async with AsyncSessionLocal() as session:
        product = Product(name=f"Pipeline Test Product {uuid.uuid4()}")
        session.add(product)
        await session.flush()
        version = ProductVersion(product_id=product.id, version="0.1.0")
        session.add(version)
        await session.commit()
        product_id = product.id
        version_id = version.id

    new_id = uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO company.projects (id, name, product_version_id, status) "
                "VALUES (:id, :name, :product_version_id, 'planned')"
            ),
            {"id": new_id, "name": f"pipeline-test-{new_id}", "product_version_id": version_id},
        )
    yield new_id
    async with engine.begin() as conn:
        # Delete any pipeline rows this test created for the project,
        # bottom-up (leaf tables first), before deleting the stub project
        # row itself -- none of these tables have ON DELETE CASCADE, and
        # raw SQL here bypasses the ORM-level cascade="all, delete-orphan".
        pipeline_ids_row = await conn.execute(
            text("SELECT id FROM company.project_pipelines WHERE project_id = :id"),
            {"id": new_id},
        )
        pipeline_ids = [row[0] for row in pipeline_ids_row.fetchall()]
        if pipeline_ids:
            stage_ids_row = await conn.execute(
                text("SELECT id FROM company.pipeline_stages WHERE pipeline_id = ANY(:ids)"),
                {"ids": pipeline_ids},
            )
            stage_ids = [row[0] for row in stage_ids_row.fetchall()]
            if stage_ids:
                checkpoint_rows = await conn.execute(
                    text("SELECT id FROM company.progress_checkpoints WHERE project_id = :id"),
                    {"id": new_id},
                )
                checkpoint_ids = [row[0] for row in checkpoint_rows.fetchall()]
                if checkpoint_ids:
                    await conn.execute(
                        text("DELETE FROM company.notifications WHERE event_key = ANY(:keys)"),
                        {"keys": [
                            f"progress:{kind}:{checkpoint_id}"
                            for checkpoint_id in checkpoint_ids
                            for kind in ("blocked", "failed", "paused", "heartbeat_lost", "resumed")
                        ]},
                    )
                    await conn.execute(
                        text(
                            "DELETE FROM company.audit_events "
                            "WHERE entity_type = 'progress_checkpoint' AND entity_id = ANY(:ids)"
                        ),
                        {"ids": checkpoint_ids},
                    )
                await conn.execute(
                    text(
                        "DELETE FROM company.audit_events "
                        "WHERE entity_type = 'pipeline_stage' AND entity_id = ANY(:ids)"
                    ),
                    {"ids": stage_ids},
                )
                await conn.execute(
                    text(
                        "DELETE FROM company.pipeline_stage_dependencies "
                        "WHERE stage_id = ANY(:ids) OR depends_on_stage_id = ANY(:ids)"
                    ),
                    {"ids": stage_ids},
                )
                await conn.execute(
                    text("DELETE FROM company.pipeline_stage_gates WHERE stage_id = ANY(:ids)"),
                    {"ids": stage_ids},
                )
                await conn.execute(
                    text(
                        "DELETE FROM company.pipeline_stage_required_artifacts "
                        "WHERE stage_id = ANY(:ids)"
                    ),
                    {"ids": stage_ids},
                )
                await conn.execute(
                    text("DELETE FROM company.pipeline_stages WHERE id = ANY(:ids)"),
                    {"ids": stage_ids},
                )
            await conn.execute(
                text("DELETE FROM company.project_pipelines WHERE id = ANY(:ids)"),
                {"ids": pipeline_ids},
            )
        await conn.execute(text("DELETE FROM company.projects WHERE id = :id"), {"id": new_id})
        await conn.execute(
            text("DELETE FROM company.product_versions WHERE id = :id"), {"id": version_id}
        )
        await conn.execute(text("DELETE FROM company.products WHERE id = :id"), {"id": product_id})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_get_list_pipeline(client: AsyncClient, project_id: uuid.UUID):
    create_payload = {
        "project_id": str(project_id),
        "name": "Main delivery pipeline",
        "status": "active",
        "is_active": True,
        "stages": [
            {
                "name": "Discovery",
                "stage_type": "discovery",
                "order_index": 0,
                "status": "pending",
            },
            {
                "name": "Implementation",
                "stage_type": "implementation",
                "order_index": 1,
                "status": "pending",
                "requires_approval": True,
                "required_artifacts": [
                    {"artifact_type": "source_code", "is_mandatory": True}
                ],
                "gates": [
                    {"gate_type": "approval", "name": "Code review", "is_mandatory": True}
                ],
            },
        ],
    }

    create_resp = await client.post("/api/v1/pipelines", json=create_payload)
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    pipeline_id = created["id"]
    assert created["name"] == "Main delivery pipeline"
    assert len(created["stages"]) == 2
    assert created["stages"][1]["required_artifacts"][0]["artifact_type"] == "source_code"

    get_resp = await client.get(f"/api/v1/pipelines/{pipeline_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == pipeline_id

    list_resp = await client.get("/api/v1/pipelines", params={"project_id": str(project_id)})
    assert list_resp.status_code == 200
    listed = list_resp.json()
    assert any(p["id"] == pipeline_id for p in listed)


@pytest.mark.asyncio
async def test_only_one_active_pipeline_per_project(client: AsyncClient, project_id: uuid.UUID):
    payload = {
        "project_id": str(project_id),
        "name": "Pipeline A",
        "is_active": True,
        "stages": [],
    }
    resp_a = await client.post("/api/v1/pipelines", json=payload)
    assert resp_a.status_code == 201
    pipeline_a_id = resp_a.json()["id"]

    payload["name"] = "Pipeline B"
    resp_b = await client.post("/api/v1/pipelines", json=payload)
    assert resp_b.status_code == 201
    pipeline_b_id = resp_b.json()["id"]

    # Rule 6.2.2: creating pipeline B as active deactivates pipeline A.
    get_a = await client.get(f"/api/v1/pipelines/{pipeline_a_id}")
    assert get_a.json()["is_active"] is False

    get_b = await client.get(f"/api/v1/pipelines/{pipeline_b_id}")
    assert get_b.json()["is_active"] is True


@pytest.mark.asyncio
async def test_stage_cannot_complete_with_missing_mandatory_artifact(
    client: AsyncClient, project_id: uuid.UUID
):
    """Business-rule violation case (SPEC 6.2.7): 4xx expected."""
    payload = {
        "project_id": str(project_id),
        "name": "Gated pipeline",
        "is_active": True,
        "stages": [
            {
                "name": "Build",
                "stage_type": "build",
                "order_index": 0,
                "status": "pending",
                "required_artifacts": [
                    {"artifact_type": "deployment_package", "is_mandatory": True, "is_fulfilled": False}
                ],
            }
        ],
    }
    create_resp = await client.post("/api/v1/pipelines", json=payload)
    assert create_resp.status_code == 201
    stage_id = create_resp.json()["stages"][0]["id"]

    complete_resp = await client.patch(f"/api/v1/pipelines/stages/{stage_id}", json={"status": "completed"})
    assert complete_resp.status_code == 409
    assert "evaluate-completion" in complete_resp.json()["detail"]


@pytest.mark.asyncio
async def test_stage_completion_requires_current_assessment_and_is_idempotent(
    client: AsyncClient, project_id: uuid.UUID
):
    created = await client.post("/api/v1/pipelines", json={
        "project_id": str(project_id), "name": "Recoverable pipeline", "is_active": True,
        "stages": [{"name": "Implementation", "stage_type": "implementation", "order_index": 0}],
    })
    assert created.status_code == 201, created.text
    stage_id = created.json()["stages"][0]["id"]

    direct = await client.patch(f"/api/v1/pipelines/stages/{stage_id}", json={"status": "completed"})
    assert direct.status_code == 409

    first = await client.post(f"/api/v1/pipeline-stages/{stage_id}:evaluate-completion")
    second = await client.post(f"/api/v1/pipeline-stages/{stage_id}:evaluate-completion")
    assert first.status_code == second.status_code == 200
    assert first.json()["result"] == "ready"
    assert first.json()["id"] == second.json()["id"]

    body = {"assessment_id": first.json()["id"], "idempotency_key": f"complete-{uuid.uuid4()}"}
    complete = await client.post(f"/api/v1/pipeline-stages/{stage_id}:complete", json=body)
    retry = await client.post(f"/api/v1/pipeline-stages/{stage_id}:complete", json=body)
    assert complete.status_code == retry.status_code == 200
    assert complete.json()["checkpoint"]["id"] == retry.json()["checkpoint"]["id"]

    progress = await client.get(f"/api/v1/projects/{project_id}/progress")
    timeline = await client.get(f"/api/v1/projects/{project_id}/progress-timeline")
    assert progress.status_code == timeline.status_code == 200
    assert progress.json()["stages"][0]["effective_status"] == "completed"
    assert timeline.json()[-1]["checkpoint_type"] == "completed"


@pytest.mark.asyncio
async def test_stage_completion_rejects_stale_assessment(
    client: AsyncClient, project_id: uuid.UUID
):
    created = await client.post("/api/v1/pipelines", json={
        "project_id": str(project_id), "name": "Stale assessment pipeline", "is_active": True,
        "stages": [{"name": "Testing", "stage_type": "testing", "order_index": 0}],
    })
    stage_id = created.json()["stages"][0]["id"]
    assessment = await client.post(f"/api/v1/pipeline-stages/{stage_id}:evaluate-completion")
    changed = await client.patch(f"/api/v1/pipelines/stages/{stage_id}", json={"name": "Testing revised"})
    assert changed.status_code == 200
    response = await client.post(f"/api/v1/pipeline-stages/{stage_id}:complete", json={
        "assessment_id": assessment.json()["id"], "idempotency_key": f"stale-{uuid.uuid4()}",
    })
    assert response.status_code == 409
    assert "stale" in response.json()["detail"]


@pytest.mark.asyncio
async def test_execution_checkpoint_block_and_resume_preserve_stop_point(
    client: AsyncClient, project_id: uuid.UUID
):
    from app.db.base import AsyncSessionLocal
    from app.db.models.backlog import PlanningItem
    from app.db.models.task import ProjectTask, TaskExecution

    created = await client.post("/api/v1/pipelines", json={
        "project_id": str(project_id), "name": "Checkpoint pipeline", "is_active": True,
        "stages": [{"name": "Build", "stage_type": "build", "order_index": 0}],
    })
    stage_id = created.json()["stages"][0]["id"]
    async with AsyncSessionLocal() as session:
        item = PlanningItem(
            title="Checkpoint item", item_type="feature", project_id=project_id,
            status="in_progress", priority="medium",
        )
        session.add(item); await session.flush()
        task = ProjectTask(planning_item_id=item.id, title="Checkpoint task", status="in_progress")
        session.add(task); await session.flush()
        execution = TaskExecution(task_id=task.id, attempt_number=1, status="running")
        session.add(execution); await session.commit()
        execution_id = execution.id

    key = f"checkpoint-{uuid.uuid4()}"
    checkpoint_body = {
        "pipeline_stage_id": stage_id, "checkpoint_type": "progress",
        "step_key": "build.compile", "step_label": "Compile application",
        "resume_from_step_key": "build.compile", "idempotency_key": key,
    }
    first = await client.post(f"/api/v1/executions/{execution_id}/checkpoints", json=checkpoint_body)
    retry = await client.post(f"/api/v1/executions/{execution_id}/checkpoints", json=checkpoint_body)
    assert first.status_code == retry.status_code == 200
    assert first.json()["id"] == retry.json()["id"]

    blocked = await client.post(f"/api/v1/executions/{execution_id}:block", json={
        "step_key": "build.compile", "step_label": "Compile application",
        "blocker_code": "dependency_unavailable", "message": "Package registry unavailable",
        "resume_from_step_key": "build.compile", "idempotency_key": f"block-{uuid.uuid4()}",
    })
    assert blocked.status_code == 200, blocked.text
    progress = await client.get(f"/api/v1/projects/{project_id}/progress")
    assert progress.json()["stopped_at"]["reason"] == "dependency_unavailable"
    assert progress.json()["first_safe_action"] == "Reconcile and resume from build.compile"

    resumed = await client.post(f"/api/v1/executions/{execution_id}:resume", json={
        "step_key": "build.compile", "step_label": "Resume compilation",
        "resume_from_step_key": "build.compile", "idempotency_key": f"resume-{uuid.uuid4()}",
    })
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["execution_status"] == "running"
    timeline = await client.get(f"/api/v1/projects/{project_id}/progress-timeline")
    assert [item["checkpoint_type"] for item in timeline.json()][-3:] == ["progress", "blocked", "resumed"]


@pytest.mark.asyncio
async def test_dependent_stage_blocked_by_incomplete_dependency(
    client: AsyncClient, project_id: uuid.UUID
):
    """Business-rule violation case (SPEC 6.2.9): 4xx expected."""
    payload = {
        "project_id": str(project_id),
        "name": "Dependency pipeline",
        "is_active": True,
        "stages": [
            {"name": "Stage One", "stage_type": "discovery", "order_index": 0, "status": "pending"},
        ],
    }
    create_resp = await client.post("/api/v1/pipelines", json=payload)
    assert create_resp.status_code == 201
    pipeline_id = create_resp.json()["id"]
    stage_one_id = create_resp.json()["stages"][0]["id"]

    stage_two_payload = {
        "name": "Stage Two",
        "stage_type": "implementation",
        "order_index": 1,
        "status": "pending",
        "depends_on_stage_ids": [stage_one_id],
    }
    stage_two_resp = await client.post(f"/api/v1/pipelines/{pipeline_id}/stages", json=stage_two_payload)
    assert stage_two_resp.status_code == 201
    stage_two_id = stage_two_resp.json()["id"]

    # Stage One is still "pending" (not completed) -> advancing Stage Two
    # must be blocked.
    advance_resp = await client.patch(
        f"/api/v1/pipelines/stages/{stage_two_id}", json={"status": "in_progress"}
    )
    assert advance_resp.status_code == 409
    assert "has not completed" in advance_resp.json()["detail"]

import asyncio
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
import httpx
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, text

from app.core.agent_activity import build_agent_activity, classify_flow_stage
from app.core.security import create_access_token, hash_password
from app.db.base import AsyncSessionLocal, engine
from app.db.models.agent import Agent
from app.db.models.backlog import PlanningItem
from app.db.models.demand import AgentDemand
from app.db.models.governance import (
    ApprovalRequest,
    Policy,
    PolicyBinding,
    PolicyEvaluation,
    PolicyVersion,
)
from app.db.models.product import Product, ProductVersion
from app.db.models.progress import ProgressCheckpoint
from app.db.models.project import ChangeRequest, Project
from app.db.models.notification import Notification
from app.db.models.orchestration import ProjectAgentMembership
from app.db.models.task import ProjectTask, TaskAssignment, TaskExecution
from app.db.models.profile import Profile, ProfileActionPermission
from app.db.models.system_scope import (
    DevelopmentRequest,
    ProductConcept,
    ProductConceptRevision,
    SystemBlueprint,
    SystemBlueprintRevision,
)
from app.db.models.user import User
from app.main import app


@dataclass(frozen=True)
class ActivityWorld:
    product_id: uuid.UUID
    version_id: uuid.UUID
    project_id: uuid.UUID
    planning_item_id: uuid.UUID
    task_id: uuid.UUID
    agent_id: uuid.UUID
    assignment_id: uuid.UUID
    execution_id: uuid.UUID
    checkpoint_id: uuid.UUID
    demand_id: uuid.UUID
    policy_id: uuid.UUID
    policy_version_id: uuid.UUID
    policy_binding_id: uuid.UUID
    policy_evaluation_id: uuid.UUID
    approval_id: uuid.UUID


@pytest_asyncio.fixture
async def activity_api_users():
    """Real principals keep route authorization tests at the HTTP boundary."""
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        profile = Profile(name=f"activity-limited-{suffix}")
        reader_profile = Profile(name=f"activity-reader-{suffix}")
        admin = User(
            username=f"activity-admin-{suffix}",
            hashed_password=hash_password("test"),
            is_admin=True,
        )
        db.add_all([profile, reader_profile, admin])
        await db.flush()
        limited = User(
            username=f"activity-limited-{suffix}",
            hashed_password=hash_password("test"),
            profile_id=profile.id,
        )
        reader = User(
            username=f"activity-reader-{suffix}",
            hashed_password=hash_password("test"),
            profile_id=reader_profile.id,
        )
        db.add_all([
            limited,
            reader,
            ProfileActionPermission(
                profile_id=reader_profile.id,
                action_key="demands.view",
                allowed=True,
            ),
        ])
        await db.commit()
        headers = {
            "admin": {"Authorization": f"Bearer {create_access_token(admin.username)}"},
            "limited": {"Authorization": f"Bearer {create_access_token(limited.username)}"},
            "reader": {"Authorization": f"Bearer {create_access_token(reader.username)}"},
            "admin_username": admin.username,
        }
        ids = (profile.id, reader_profile.id, admin.id, limited.id, reader.id)

    try:
        yield headers
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(User).where(User.id.in_(ids[2:])))
            await db.execute(delete(Profile).where(Profile.id.in_(ids[:2])))
            await db.commit()


@pytest_asyncio.fixture
async def activity_client(activity_api_users):
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers=activity_api_users["admin"],
    ) as client:
        yield client


@pytest_asyncio.fixture
async def activity_world():
    suffix = uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        product = Product(name=f"Agent Activity Product {suffix}")
        db.add(product)
        await db.flush()
        version = ProductVersion(product_id=product.id, version=f"0.0.{suffix}")
        db.add(version)
        await db.flush()
        project = Project(
            name=f"Agent Activity Project {suffix}",
            product_version_id=version.id,
            working_directory_path="/root/project/forgehub",
        )
        db.add(project)
        await db.flush()
        planning_item = PlanningItem(
            title="Observe canonical activity",
            item_type="feature",
            project_id=project.id,
        )
        db.add(planning_item)
        await db.flush()
        task = ProjectTask(
            title="Aggregate canonical activity",
            planning_item_id=planning_item.id,
            status="in_progress",
        )
        agent = Agent(
            name=f"Agent Activity Worker {suffix}",
            agent_type="executor",
            runtime_type="codex",
            profile_slug=f"activity-{suffix}",
            avatar_data_url="data:image/png;base64,AA==",
        )
        db.add_all([task, agent])
        await db.flush()
        db.add(
            ProjectAgentMembership(
                project_id=project.id,
                agent_id=agent.id,
                role="developer",
                status="active",
            )
        )
        await db.flush()
        assignment = TaskAssignment(
            task_id=task.id,
            agent_id=agent.id,
            status="active",
            assigned_at=now,
        )
        db.add(assignment)
        await db.flush()
        execution = TaskExecution(
            task_id=task.id,
            assignment_id=assignment.id,
            executor_type="agent",
            runtime_type="codex",
            status="failed",
            started_at=now,
            finished_at=now,
            outcome_summary="Runner stopped before verification",
        )
        db.add(execution)
        await db.flush()
        checkpoint = ProgressCheckpoint(
            project_id=project.id,
            task_id=task.id,
            task_execution_id=execution.id,
            sequence=1,
            checkpoint_type="failed",
            step_key="run-tests",
            step_label="Run focused tests",
            state_snapshot={},
            completed_requirement_keys=[],
            evidence_refs=[],
            last_confirmed_at=now,
            resume_from_step_key="verify-tests",
            error_code="EXEC_RUNTIME_502",
            message="Runner stopped before verification",
            actor_type="agent",
            actor_id=agent.id,
            actor_name=agent.name,
            idempotency_key=f"activity-checkpoint-{suffix}",
        )
        demand = AgentDemand(
            from_agent=agent.profile_slug,
            from_agent_id=agent.id,
            target_agent_id=agent.id,
            project_id=project.id,
            subject="Run canonical aggregation",
            body="Names in this prose are decorative and must not be parsed.",
            origin_type="task",
            origin_id=task.id,
            task_execution_id=execution.id,
            dispatch_status="failed",
            dispatch_error="gateway returned 502",
            dispatch_attempts=1,
            requires_response=True,
        )
        db.add_all([checkpoint, demand])

        policy = Policy(
            name=f"Agent Activity Approval {suffix}",
            policy_type="approval_required",
            rules={},
            is_active=True,
            entity_type="project_task",
        )
        db.add(policy)
        await db.flush()
        policy_version = PolicyVersion(
            policy_id=policy.id,
            version=1,
            rules_snapshot={},
            content_hash=suffix.ljust(64, "0"),
            status="active",
        )
        db.add(policy_version)
        await db.flush()
        binding = PolicyBinding(
            policy_version_id=policy_version.id,
            target_type="project_task",
            target_id=project.id,
            is_active=True,
        )
        db.add(binding)
        await db.flush()
        evaluation = PolicyEvaluation(
            policy_binding_id=binding.id,
            policy_version_id=policy_version.id,
            target_type="project_task",
            target_id=task.id,
            target_hash=suffix.ljust(64, "1"),
            input_hash=suffix.ljust(64, "2"),
            outcome="approval_required",
            result={},
            evaluated_at=now,
        )
        db.add(evaluation)
        await db.flush()
        approval = ApprovalRequest(
            target_type="project_task",
            target_id=task.id,
            target_hash=evaluation.target_hash,
            approval_type="task_completion",
            policy_evaluation_id=evaluation.id,
            status="pending",
            requested_by_type="agent",
            requested_by_id=agent.id,
            requested_by_name=agent.name,
            idempotency_key=f"activity-approval-{suffix}",
        )
        db.add(approval)
        await db.commit()

        world = ActivityWorld(
            product_id=product.id,
            version_id=version.id,
            project_id=project.id,
            planning_item_id=planning_item.id,
            task_id=task.id,
            agent_id=agent.id,
            assignment_id=assignment.id,
            execution_id=execution.id,
            checkpoint_id=checkpoint.id,
            demand_id=demand.id,
            policy_id=policy.id,
            policy_version_id=policy_version.id,
            policy_binding_id=binding.id,
            policy_evaluation_id=evaluation.id,
            approval_id=approval.id,
        )

    yield world

    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM company.approval_requests WHERE id = :id"),
            {"id": world.approval_id},
        )
        await conn.execute(
            text("DELETE FROM company.policy_evaluations WHERE id = :id"),
            {"id": world.policy_evaluation_id},
        )
        await conn.execute(
            text("DELETE FROM company.policy_bindings WHERE id = :id"),
            {"id": world.policy_binding_id},
        )
        await conn.execute(
            text("DELETE FROM company.policy_versions WHERE id = :id"),
            {"id": world.policy_version_id},
        )
        await conn.execute(
            text("DELETE FROM company.policies WHERE id = :id"),
            {"id": world.policy_id},
        )
        await conn.execute(
            text("DELETE FROM company.agent_demands WHERE id = :id"),
            {"id": world.demand_id},
        )
        await conn.execute(
            text("DELETE FROM company.progress_checkpoints WHERE id = :id"),
            {"id": world.checkpoint_id},
        )
        await conn.execute(
            text("DELETE FROM company.task_executions WHERE id = :id"),
            {"id": world.execution_id},
        )
        await conn.execute(
            text("DELETE FROM company.task_assignments WHERE id = :id"),
            {"id": world.assignment_id},
        )
        await conn.execute(
            text("DELETE FROM company.project_tasks WHERE id = :id"),
            {"id": world.task_id},
        )
        await conn.execute(
            text("DELETE FROM company.agents WHERE id = :id"),
            {"id": world.agent_id},
        )
        await conn.execute(
            text("DELETE FROM company.planning_items WHERE id = :id"),
            {"id": world.planning_item_id},
        )
        await conn.execute(
            text("DELETE FROM company.projects WHERE id = :id"),
            {"id": world.project_id},
        )
        await conn.execute(
            text("DELETE FROM company.product_versions WHERE id = :id"),
            {"id": world.version_id},
        )
        await conn.execute(
            text("DELETE FROM company.products WHERE id = :id"),
            {"id": world.product_id},
        )


def _incident_payload() -> dict[str, object]:
    return {
        "key": "execution_failed:missing",
        "kind": "execution_failed",
        "severity": "error",
        "title": "Execution failed",
        "occurred_at": datetime.now(timezone.utc),
        "source_type": "task_execution",
        "source_id": uuid.uuid4(),
        "affected_agent_id": None,
        "project_id": None,
        "task_id": None,
        "execution_id": None,
        "checkpoint_id": None,
        "resume_from_step_key": None,
        "error_code": "EXEC_RUNTIME_502",
        "blocker_code": None,
        "summary": "Runner stopped",
        "recommended_action": "request_athos_monitoring",
        "prior_attempts": [],
    }


@pytest.mark.parametrize(
    ("source_type", "source_status", "expected"),
    [
        ("agent_demand", "new", "incoming"),
        ("agent_demand", "incubating", "planning"),
        ("agent_demand", "dispatched", "queued"),
        ("task_execution", "pending", "queued"),
        ("task_execution", "running", "executing"),
        ("task_execution", "verified", "verifying"),
        ("task_execution", "failed", "attention"),
        ("approval_request", "pending", "attention"),
        ("agent_demand", "archived", "archived"),
    ],
)
def test_classify_flow_stage(source_type, source_status, expected):
    assert classify_flow_stage(source_type, source_status) == expected


@pytest.mark.asyncio
async def test_build_activity_joins_message_execution_checkpoint_and_approval(
    activity_world,
):
    async with AsyncSessionLocal() as db:
        view = await build_agent_activity(
            db,
            project_id=activity_world.project_id,
            window_minutes=60,
        )

    agent = next(item for item in view.agents if item.id == activity_world.agent_id)
    assert agent.current_execution_id == activity_world.execution_id
    assert agent.latest_checkpoint.resume_from_step_key == "verify-tests"
    assert any(
        edge.message_id == activity_world.demand_id for edge in view.message_edges
    )
    incident = next(
        item
        for item in view.incidents
        if item.execution_id == activity_world.execution_id
    )
    assert incident.error_code == "EXEC_RUNTIME_502"
    assert incident.checkpoint_id == activity_world.checkpoint_id
    assert any(
        event.source_id == activity_world.approval_id for event in view.timeline
    )
    assert {
        (item.source_type, item.source_id, item.source_status, item.stage)
        for item in view.flow_items
        if item.source_id
        in {
            activity_world.demand_id,
            activity_world.execution_id,
            activity_world.approval_id,
        }
    } == {
        ("agent_demand", activity_world.demand_id, "failed", "attention"),
        ("task_execution", activity_world.execution_id, "failed", "attention"),
        ("approval_request", activity_world.approval_id, "pending", "attention"),
    }
    timeline_by_source = {event.source_id: event for event in view.timeline}
    assert timeline_by_source[activity_world.demand_id].lane == "communication"
    assert timeline_by_source[activity_world.execution_id].lane == "execution"
    assert timeline_by_source[activity_world.checkpoint_id].lane == "checkpoint"
    assert timeline_by_source[activity_world.approval_id].lane == "governance"
    assert timeline_by_source[activity_world.execution_id].source_status == "failed"


@pytest.mark.asyncio
async def test_build_activity_includes_membership_only_project(activity_world):
    membership_project_id = uuid.uuid4()
    try:
        async with AsyncSessionLocal() as db:
            project = Project(
                id=membership_project_id,
                name="Membership-only activity project",
                product_version_id=activity_world.version_id,
                status="active",
            )
            db.add(project)
            await db.flush()
            db.add(
                ProjectAgentMembership(
                    project_id=project.id,
                    agent_id=activity_world.agent_id,
                    role="reviewer",
                    status="active",
                )
            )
            await db.commit()

        async with AsyncSessionLocal() as db:
            view = await build_agent_activity(db, project_id=None, window_minutes=60)

        assert any(project.id == membership_project_id for project in view.projects)
        assert any(
            relation.kind == "membership"
            and relation.from_id == str(activity_world.agent_id)
            and relation.to_id == str(membership_project_id)
            for relation in view.topology_relations
        )
        assert any(
            relation.kind == "portal_sync"
            and relation.from_id == str(membership_project_id)
            and relation.to_id == "site:darckware"
            for relation in view.topology_relations
        )
    finally:
        async with engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM company.projects WHERE id = :id"),
                {"id": membership_project_id},
            )


@pytest.mark.asyncio
async def test_build_activity_includes_planned_task_without_execution(activity_world):
    task_id = uuid.uuid4()
    try:
        async with AsyncSessionLocal() as db:
            db.add(
                ProjectTask(
                    id=task_id,
                    title="Planned without an execution",
                    planning_item_id=activity_world.planning_item_id,
                    status="planned",
                )
            )
            await db.commit()

        async with AsyncSessionLocal() as db:
            view = await build_agent_activity(
                db,
                project_id=activity_world.project_id,
                window_minutes=60,
            )

        item = next(flow for flow in view.flow_items if flow.source_id == task_id)
        assert item.source_type == "project_task"
        assert item.source_status == "planned"
        assert item.stage == "planning"
        assert item.project_id == activity_world.project_id
    finally:
        async with engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM company.project_tasks WHERE id = :id"),
                {"id": task_id},
            )


@pytest.mark.asyncio
async def test_build_activity_preserves_db_state_when_forgerouter_is_unavailable(
    activity_world,
    monkeypatch,
):
    """Optional telemetry failure cannot erase canonical Postgres activity."""

    async def unavailable_forgerouter_activity(*args, **kwargs):
        raise httpx.ConnectError("ForgeRouter is unavailable")

    monkeypatch.setattr(
        "app.core.agent_activity.read_recent_forgerouter_activity",
        unavailable_forgerouter_activity,
    )

    async with AsyncSessionLocal() as db:
        view = await build_agent_activity(
            db,
            project_id=activity_world.project_id,
            window_minutes=60,
        )

    assert any(agent.id == activity_world.agent_id for agent in view.agents)
    assert any(edge.message_id == activity_world.demand_id for edge in view.message_edges)
    assert next(
        freshness
        for freshness in view.source_freshness
        if freshness.name == "forgerouter"
    ).status == "unavailable"


@pytest.mark.asyncio
async def test_build_activity_includes_change_request_task_execution_for_project(
    activity_world,
):
    """Project activity resolves executions through a task's change request."""

    async with AsyncSessionLocal() as db:
        change_request = ChangeRequest(
            project_id=activity_world.project_id,
            title="Keep change-request execution visible",
        )
        db.add(change_request)
        await db.flush()
        task = ProjectTask(
            title="Execute approved change request",
            change_request_id=change_request.id,
            status="in_progress",
        )
        db.add(task)
        await db.flush()
        assignment = TaskAssignment(
            task_id=task.id,
            agent_id=activity_world.agent_id,
            status="active",
            assigned_at=datetime.now(timezone.utc),
        )
        db.add(assignment)
        await db.flush()
        execution = TaskExecution(
            task_id=task.id,
            assignment_id=assignment.id,
            executor_type="agent",
            runtime_type="codex",
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        db.add(execution)
        await db.commit()

        try:
            view = await build_agent_activity(
                db,
                project_id=activity_world.project_id,
                window_minutes=60,
            )

            assert any(
                item.current_execution_id == execution.id for item in view.agents
            )
        finally:
            await db.delete(task)
            await db.delete(change_request)
            await db.commit()


@pytest.mark.asyncio
async def test_build_activity_excludes_unlinked_notifications_from_project_timeline(
    activity_world,
):
    """A project view cannot attribute globally linked notifications by prose."""

    notification = Notification(
        source="system",
        severity="warning",
        title="Global alert",
        event_key=f"activity-unlinked-{uuid.uuid4()}",
        occurred_at=datetime.now(timezone.utc),
    )
    async with AsyncSessionLocal() as db:
        db.add(notification)
        await db.commit()

        try:
            view = await build_agent_activity(
                db,
                project_id=activity_world.project_id,
                window_minutes=60,
            )

            assert all(
                event.source_id != notification.id for event in view.timeline
            )
        finally:
            await db.delete(notification)
            await db.commit()


@pytest.mark.asyncio
async def test_build_activity_resolves_reply_outside_the_demand_window(activity_world):
    """A selected request stops waiting when its canonical reply is older."""

    old = datetime.now(timezone.utc) - timedelta(hours=2)
    reply = AgentDemand(
        from_agent="reply-worker",
        from_agent_id=activity_world.agent_id,
        target_agent_id=activity_world.agent_id,
        project_id=activity_world.project_id,
        subject="Canonical reply",
        body="This text is not used to detect the reply.",
        origin_type="task",
        origin_id=activity_world.task_id,
        reply_to_id=activity_world.demand_id,
        dispatch_status="completed",
        requires_response=False,
        created_at=old,
        updated_at=old,
    )
    async with AsyncSessionLocal() as db:
        db.add(reply)
        await db.commit()

        try:
            view = await build_agent_activity(
                db,
                project_id=activity_world.project_id,
                window_minutes=60,
            )

            edge = next(
                item
                for item in view.message_edges
                if item.message_id == activity_world.demand_id
            )
            assert edge.response_status == "responded"
            assert edge.waiting_for_response is False
            assert edge.responded_at == old
        finally:
            await db.delete(reply)
            await db.commit()


@pytest.mark.asyncio
async def test_build_activity_excludes_mismatched_approval_target_type(activity_world):
    """Approval target IDs are scoped only with their target discriminator."""

    unrelated_approval = ApprovalRequest(
        target_type="release",
        target_id=activity_world.task_id,
        target_hash=uuid.uuid4().hex.ljust(64, "0"),
        approval_type="release_approval",
        policy_evaluation_id=activity_world.policy_evaluation_id,
        status="pending",
        requested_by_type="agent",
        requested_by_id=activity_world.agent_id,
        requested_by_name="Activity Worker",
        idempotency_key=f"activity-unrelated-approval-{uuid.uuid4()}",
    )
    async with AsyncSessionLocal() as db:
        db.add(unrelated_approval)
        await db.commit()

        try:
            view = await build_agent_activity(
                db,
                project_id=activity_world.project_id,
                window_minutes=60,
            )

            assert all(
                event.source_id != unrelated_approval.id for event in view.timeline
            )
            assert all(
                incident.source_id != unrelated_approval.id
                for incident in view.incidents
            )
        finally:
            await db.delete(unrelated_approval)
            await db.commit()


@pytest.mark.asyncio
async def test_build_activity_includes_prior_attempt_checkpoint_error(activity_world):
    """Prior attempts expose their own canonical checkpoint error code."""

    previous_execution = TaskExecution(
        task_id=activity_world.task_id,
        assignment_id=activity_world.assignment_id,
        attempt_number=1,
        executor_type="agent",
        runtime_type="codex",
        status="retried",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        outcome_summary="Retry after runtime failure",
    )
    async with AsyncSessionLocal() as db:
        current_execution = await db.get(TaskExecution, activity_world.execution_id)
        current_execution.attempt_number = 2
        db.add(previous_execution)
        await db.flush()
        checkpoint = ProgressCheckpoint(
            project_id=activity_world.project_id,
            task_id=activity_world.task_id,
            task_execution_id=previous_execution.id,
            sequence=1,
            checkpoint_type="failed",
            step_key="run-tests",
            step_label="Run focused tests",
            state_snapshot={},
            completed_requirement_keys=[],
            evidence_refs=[],
            last_confirmed_at=datetime.now(timezone.utc),
            error_code="EXEC_PREVIOUS_FAILURE",
            actor_type="agent",
            actor_id=activity_world.agent_id,
            actor_name="Activity Worker",
            idempotency_key=f"activity-prior-checkpoint-{uuid.uuid4()}",
        )
        db.add(checkpoint)
        await db.commit()

        try:
            view = await build_agent_activity(
                db,
                project_id=activity_world.project_id,
                window_minutes=60,
            )

            incident = next(
                item
                for item in view.incidents
                if item.execution_id == activity_world.execution_id
            )
            prior = next(
                item
                for item in incident.prior_attempts
                if item.execution_id == previous_execution.id
            )
            assert prior.error_code == "EXEC_PREVIOUS_FAILURE"
        finally:
            await db.delete(checkpoint)
            await db.delete(previous_execution)
            await db.commit()


def test_agent_activity_contract_rejects_incident_without_source_id():
    """A canonical incident must always identify the record that produced it."""
    from pydantic import ValidationError

    from app.api.schemas.agent_activity import ActivityIncidentOut

    with pytest.raises(ValidationError):
        ActivityIncidentOut(**(_incident_payload() | {"source_id": None}))

    missing_source_id = _incident_payload()
    del missing_source_id["source_id"]

    with pytest.raises(ValidationError):
        ActivityIncidentOut(**missing_source_id)


def test_agent_activity_contract_serializes_typed_prior_attempts():
    """Incident retry history accepts only explicit scalar API records."""
    from pydantic import ValidationError

    from app.api.schemas.agent_activity import (
        ActivityIncidentOut,
        ActivityPriorAttemptOut,
    )

    attempt_id = uuid.uuid4()
    execution_id = uuid.uuid4()
    started_at = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
    completed_at = datetime(2026, 8, 29, 12, 5, tzinfo=timezone.utc)
    attempt = ActivityPriorAttemptOut(
        id=attempt_id,
        execution_id=execution_id,
        attempt_number=2,
        started_at=started_at,
        completed_at=completed_at,
        outcome="failed",
        error_code="EXEC_RUNTIME_502",
        summary="Runner stopped before verification",
        canonical_path=f"/tasks/{execution_id}",
    )

    incident = ActivityIncidentOut(
        **(_incident_payload() | {"prior_attempts": [attempt]})
    )

    payload = incident.model_dump(mode="json")

    assert payload["prior_attempts"] == [
        {
            "id": str(attempt_id),
            "execution_id": str(execution_id),
            "attempt_number": 2,
            "started_at": "2026-08-29T12:00:00Z",
            "completed_at": "2026-08-29T12:05:00Z",
            "outcome": "failed",
            "error_code": "EXEC_RUNTIME_502",
            "summary": "Runner stopped before verification",
            "canonical_path": f"/tasks/{execution_id}",
            "related_records": [],
        }
    ]

    class DomainAttempt:
        pass

    unsafe_attempt = attempt.model_dump() | {"outcome": DomainAttempt()}
    with pytest.raises(ValidationError):
        ActivityIncidentOut(**(_incident_payload() | {"prior_attempts": [unsafe_attempt]}))


def test_agent_activity_contract_serializes_canonical_operational_records():
    """The read model preserves typed state and canonical paths without ORM objects."""
    from app.api.schemas.agent_activity import (
        ActivityAgentOut,
        ActivityCheckpointOut,
        ActivityCurrentWorkOut,
        ActivityMessageEdgeOut,
        ActivityProfileSummaryOut,
        ActivitySourceFreshnessOut,
        ActivityTimelineEventOut,
        AgentActivityOut,
    )

    agent_id = uuid.uuid4()
    project_id = uuid.uuid4()
    task_id = uuid.uuid4()
    execution_id = uuid.uuid4()
    checkpoint_id = uuid.uuid4()
    message_id = uuid.uuid4()
    approval_id = uuid.uuid4()
    observed_at = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)

    view = AgentActivityOut(
        generated_at=observed_at,
        project_id=project_id,
        agents=[
            ActivityAgentOut(
                id=agent_id,
                name="Aramis",
                profile_slug="aramis",
                runtime_type="codex",
                availability="available",
                canonical_path=f"/agents/{agent_id}",
                current_work=ActivityCurrentWorkOut(
                    project_id=project_id,
                    project_name="ForgeHub",
                    project_path=f"/projects/{project_id}",
                    task_id=task_id,
                    task_title="Define operational contract",
                    task_path=f"/tasks/{task_id}",
                    execution_id=execution_id,
                    execution_path=f"/tasks/{task_id}?execution={execution_id}",
                    action="Writing schema tests",
                    source_message_id=message_id,
                    source_message_path=f"/demands?message={message_id}",
                ),
                latest_checkpoint=ActivityCheckpointOut(
                    id=checkpoint_id,
                    execution_id=execution_id,
                    occurred_at=observed_at,
                    status="confirmed",
                    resume_from_step_key="implement-schema",
                    canonical_path=f"/tasks/{task_id}?checkpoint={checkpoint_id}",
                ),
                profile_summary=ActivityProfileSummaryOut(
                    status="healthy",
                    checked_at=observed_at,
                    runtime_native=True,
                    canonical_path=f"/agents/{agent_id}",
                ),
            )
        ],
        message_edges=[
            ActivityMessageEdgeOut(
                message_id=message_id,
                from_agent_id=agent_id,
                target_agent_id=agent_id,
                dispatch_status="sent",
                sent_at=observed_at,
                updated_at=observed_at,
                canonical_path=f"/demands?message={message_id}",
            )
        ],
        incidents=[],
        timeline=[
            ActivityTimelineEventOut(
                key=f"approval:{approval_id}",
                kind="approval_requested",
                occurred_at=observed_at,
                source_type="approval_request",
                source_id=approval_id,
                source_status="pending",
                lane="governance",
                title="Approval requested",
                canonical_path=f"/governance/{approval_id}",
                project_id=project_id,
                task_id=task_id,
                execution_id=execution_id,
                agent_id=agent_id,
            )
        ],
        source_freshness=[
            ActivitySourceFreshnessOut(
                name="postgres",
                status="fresh",
                checked_at=observed_at,
            )
        ],
    )

    payload = view.model_dump(mode="json")

    assert payload["contract_version"] == "forge-agent-activity/v1"
    assert payload["agents"][0]["current_work"]["task_path"] == f"/tasks/{task_id}"
    assert payload["message_edges"][0]["canonical_path"] == f"/demands?message={message_id}"
    assert payload["timeline"][0]["canonical_path"] == f"/governance/{approval_id}"


def test_agent_activity_contract_serializes_topology_objects():
    from app.api.schemas.agent_activity import (
        ActivityAgentOut,
        ActivityProfileSummaryOut,
        ActivityProjectOut,
        ActivityResourceOut,
        ActivityTopologyRelationOut,
        AgentActivityOut,
    )

    agent_id = uuid.uuid4()
    project_id = uuid.uuid4()
    observed_at = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
    view = AgentActivityOut(
        generated_at=observed_at,
        project_id=None,
        agents=[
            ActivityAgentOut(
                id=agent_id,
                name="Aramis",
                avatar_data_url="data:image/png;base64,AA==",
                runtime_type="codex",
                availability="available",
                canonical_path=f"/agents/{agent_id}",
                profile_summary=ActivityProfileSummaryOut(
                    status="healthy",
                    checked_at=observed_at,
                    runtime_native=True,
                    canonical_path=f"/agents/{agent_id}",
                ),
            )
        ],
        projects=[
            ActivityProjectOut(
                id=project_id,
                name="ForgeHub",
                status="active",
                canonical_path=f"/projects/{project_id}",
            )
        ],
        resources=[
            ActivityResourceOut(
                key="database:forgehub_postgres/company",
                kind="database",
                label="forgehub_postgres",
                detail="company",
                status="available",
            )
        ],
        topology_relations=[
            ActivityTopologyRelationOut(
                key=f"current-work:{agent_id}:{project_id}",
                kind="current_work",
                from_type="agent",
                from_id=str(agent_id),
                to_type="project",
                to_id=str(project_id),
                label="Working now",
            )
        ],
        message_edges=[],
        incidents=[],
        timeline=[],
        source_freshness=[],
    )

    payload = view.model_dump(mode="json")

    assert payload["agents"][0]["avatar_data_url"].startswith("data:image/png")
    assert payload["projects"][0]["id"] == str(project_id)
    assert payload["resources"][0]["key"] == "database:forgehub_postgres/company"
    assert payload["topology_relations"][0]["kind"] == "current_work"


async def _get_or_create_athos() -> tuple[Agent, bool]:
    async with AsyncSessionLocal() as db:
        athos = (
            await db.execute(select(Agent).where(Agent.profile_slug == "athos"))
        ).scalar_one_or_none()
        if athos is not None:
            return athos, False
        athos = Agent(
            name="Athos Activity Test",
            agent_type="coordinator",
            runtime_type="hermes",
            profile_slug="athos",
        )
        db.add(athos)
        await db.commit()
        await db.refresh(athos)
        return athos, True


async def _remove_monitoring_records(
    *,
    channel_ref: str | None = None,
    event_key: str | None = None,
    created_athos_id: uuid.UUID | None = None,
) -> None:
    async with AsyncSessionLocal() as db:
        if event_key:
            await db.execute(delete(Notification).where(Notification.event_key == event_key))
        if channel_ref:
            await db.execute(delete(AgentDemand).where(AgentDemand.channel_ref == channel_ref))
        if created_athos_id:
            await db.execute(delete(Agent).where(Agent.id == created_athos_id))
        await db.commit()


@pytest.mark.asyncio
async def test_request_athos_monitoring_is_idempotent_and_records_structured_context(
    activity_world,
    activity_client,
    activity_api_users,
):
    """A retry must reuse one monitoring Message and its mirrored notification."""
    athos, athos_created = await _get_or_create_athos()
    key = f"activity-monitor-{uuid.uuid4()}"
    channel_ref = f"agent-activity:{key}"
    event_key = f"agent-activity:athos-monitor:{key}"
    incident_key = f"execution_failed:{activity_world.execution_id}"
    try:
        first = await activity_client.post(
            f"/api/v1/agent-activity/incidents/{incident_key}:request-athos-monitoring",
            json={"execution_id": str(activity_world.execution_id), "idempotency_key": key},
        )
        second = await activity_client.post(
            f"/api/v1/agent-activity/incidents/{incident_key}:request-athos-monitoring",
            json={"execution_id": str(activity_world.execution_id), "idempotency_key": key},
        )

        assert first.status_code == second.status_code == 201
        assert first.json()["message_id"] == second.json()["message_id"]
        assert first.json()["notification_id"] == second.json()["notification_id"]
        assert first.json()["created"] is True
        assert second.json()["created"] is False

        async with AsyncSessionLocal() as db:
            demand = (
                await db.execute(
                    select(AgentDemand).where(AgentDemand.id == uuid.UUID(first.json()["message_id"]))
                )
            ).scalar_one()
            notification = (
                await db.execute(
                    select(Notification).where(Notification.id == uuid.UUID(first.json()["notification_id"]))
                )
            ).scalar_one()
            demands = list(
                (
                    await db.execute(
                        select(AgentDemand).where(AgentDemand.channel_ref == channel_ref)
                    )
                ).scalars()
            )
            notifications = list(
                (
                    await db.execute(
                        select(Notification).where(Notification.event_key == event_key)
                    )
                ).scalars()
            )

        assert demand.number == first.json()["message_number"]
        assert demand.target_agent_id == athos.id
        assert demand.channel == "agent"
        assert demand.channel_ref == channel_ref
        assert demand.requires_response is True
        assert demand.scheduled_at is None
        assert demand.dispatch_status is None
        assert json.loads(demand.body) == {
            "contract_version": "forge-agent-incident-monitor/v1",
            "execution_id": str(activity_world.execution_id),
            "incident_key": incident_key,
            "requested_by": activity_api_users["admin_username"],
            "task_id": str(activity_world.task_id),
        }
        assert notification.event_key == event_key
        assert len(demands) == len(notifications) == 1
    finally:
        await _remove_monitoring_records(
            channel_ref=channel_ref,
            event_key=event_key,
            created_athos_id=athos.id if athos_created else None,
        )


@pytest.mark.asyncio
async def test_agent_activity_get_requires_authority_and_returns_canonical_view(
    activity_world,
    activity_api_users,
):
    """Changing the route to skip authorization or aggregation breaks this boundary."""
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers=activity_api_users["limited"],
    ) as limited_client:
        denied = await limited_client.get("/api/v1/agent-activity")
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers=activity_api_users["reader"],
    ) as reader_client:
        read_allowed = await reader_client.get("/api/v1/agent-activity")
        write_denied = await reader_client.post(
            f"/api/v1/agent-activity/incidents/execution_failed:{activity_world.execution_id}:request-athos-monitoring",
            json={"execution_id": str(activity_world.execution_id), "idempotency_key": str(uuid.uuid4())},
        )
    async with AsyncClient(transport=transport, base_url="http://test") as anonymous_client:
        unauthenticated_get = await anonymous_client.get("/api/v1/agent-activity")
        unauthenticated_post = await anonymous_client.post(
            f"/api/v1/agent-activity/incidents/execution_failed:{activity_world.execution_id}:request-athos-monitoring",
            json={"execution_id": str(activity_world.execution_id), "idempotency_key": str(uuid.uuid4())},
        )
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers=activity_api_users["admin"],
    ) as admin_client:
        response = await admin_client.get(
            "/api/v1/agent-activity",
            params={"project_id": str(activity_world.project_id), "window_minutes": 60},
        )

    assert denied.status_code == 403
    assert read_allowed.status_code == 200
    assert write_denied.status_code == 403
    assert unauthenticated_get.status_code == unauthenticated_post.status_code == 401
    assert response.status_code == 200
    payload = response.json()
    assert payload["contract_version"] == "forge-agent-activity/v1"
    assert any(item["execution_id"] == str(activity_world.execution_id) for item in payload["incidents"])
    agent = next(item for item in payload["agents"] if item["id"] == str(activity_world.agent_id))
    assert agent["avatar_data_url"] == "data:image/png;base64,AA=="
    assert any(item["id"] == str(activity_world.project_id) for item in payload["projects"])
    assert any(r["key"] == "site:darckware" for r in payload["resources"])
    assert any(r["key"] == "platform:forgehub" for r in payload["resources"])
    assert any(r["key"] == "gateway:forgerouter" for r in payload["resources"])
    assert any(r["key"] == "vault:forgevault" for r in payload["resources"])
    assert any(
        relation["kind"] == "current_work"
        and relation["from_id"] == str(activity_world.agent_id)
        and relation["to_id"] == str(activity_world.project_id)
        for relation in payload["topology_relations"]
    )
    assert not any(
        relation["kind"] == "membership"
        and relation["from_id"] == str(activity_world.agent_id)
        and relation["to_id"] == str(activity_world.project_id)
        for relation in payload["topology_relations"]
    )


@pytest.mark.asyncio
async def test_athos_request_rejects_unknown_incident(activity_world, activity_client):
    response = await activity_client.post(
        "/api/v1/agent-activity/incidents/execution_failed:missing:request-athos-monitoring",
        json={"execution_id": str(activity_world.execution_id), "idempotency_key": str(uuid.uuid4())},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_athos_request_rejects_unknown_execution_after_incident_resolution(
    activity_world,
    activity_client,
    monkeypatch,
):
    from app.api.routes import agent_activity as agent_activity_routes

    unknown_execution_id = uuid.uuid4()
    real_build_activity = agent_activity_routes.build_agent_activity

    async def activity_with_unknown_execution(*args, **kwargs):
        view = await real_build_activity(*args, **kwargs)
        incident = next(
            item for item in view.incidents if item.execution_id == activity_world.execution_id
        )
        return view.model_copy(
            update={
                "incidents": [
                    incident.model_copy(
                        update={
                            "key": f"execution_failed:{unknown_execution_id}",
                            "execution_id": unknown_execution_id,
                        }
                    )
                ]
            }
        )

    monkeypatch.setattr(agent_activity_routes, "build_agent_activity", activity_with_unknown_execution)
    response = await activity_client.post(
        f"/api/v1/agent-activity/incidents/execution_failed:{unknown_execution_id}:request-athos-monitoring",
        json={"execution_id": str(unknown_execution_id), "idempotency_key": str(uuid.uuid4())},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_athos_request_returns_not_found_when_athos_is_unavailable(
    activity_world,
    activity_client,
    monkeypatch,
):
    from app.api.routes import agent_activity as agent_activity_routes

    async def no_athos(*_args, **_kwargs):
        return None

    monkeypatch.setattr(agent_activity_routes, "_find_athos", no_athos)
    response = await activity_client.post(
        f"/api/v1/agent-activity/incidents/execution_failed:{activity_world.execution_id}:request-athos-monitoring",
        json={"execution_id": str(activity_world.execution_id), "idempotency_key": str(uuid.uuid4())},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_athos_request_repairs_a_missing_notification_pair(
    activity_world,
    activity_client,
):
    athos, athos_created = await _get_or_create_athos()
    key = f"activity-repair-{uuid.uuid4()}"
    channel_ref = f"agent-activity:{key}"
    event_key = f"agent-activity:athos-monitor:{key}"
    incident_key = f"execution_failed:{activity_world.execution_id}"
    try:
        created = await activity_client.post(
            f"/api/v1/agent-activity/incidents/{incident_key}:request-athos-monitoring",
            json={"execution_id": str(activity_world.execution_id), "idempotency_key": key},
        )
        assert created.status_code == 201
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Notification).where(Notification.event_key == event_key))
            await db.commit()

        repaired = await activity_client.post(
            f"/api/v1/agent-activity/incidents/{incident_key}:request-athos-monitoring",
            json={"execution_id": str(activity_world.execution_id), "idempotency_key": key},
        )

        assert repaired.status_code == 201
        assert repaired.json()["message_id"] == created.json()["message_id"]
        assert repaired.json()["created"] is False
        async with AsyncSessionLocal() as db:
            notifications = list(
                (
                    await db.execute(
                        select(Notification).where(Notification.event_key == event_key)
                    )
                ).scalars()
            )
        assert len(notifications) == 1
    finally:
        await _remove_monitoring_records(
            channel_ref=channel_ref,
            event_key=event_key,
            created_athos_id=athos.id if athos_created else None,
        )


@pytest.mark.asyncio
async def test_athos_request_serializes_concurrent_retries_to_one_pair(
    activity_world,
    activity_api_users,
):
    """Removing the transaction lock must expose duplicate monitoring records."""
    athos, athos_created = await _get_or_create_athos()
    key = f"activity-concurrent-{uuid.uuid4()}"
    channel_ref = f"agent-activity:{key}"
    event_key = f"agent-activity:athos-monitor:{key}"
    incident_key = f"execution_failed:{activity_world.execution_id}"
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers=activity_api_users["admin"],
        ) as client:
            first, second = await asyncio.gather(
                *[
                    client.post(
                        f"/api/v1/agent-activity/incidents/{incident_key}:request-athos-monitoring",
                        json={
                            "execution_id": str(activity_world.execution_id),
                            "idempotency_key": key,
                        },
                    )
                    for _ in range(2)
                ]
            )

        assert first.status_code == second.status_code == 201
        assert first.json()["message_id"] == second.json()["message_id"]
        assert sorted([first.json()["created"], second.json()["created"]]) == [False, True]
        async with AsyncSessionLocal() as db:
            demands = list(
                (
                    await db.execute(
                        select(AgentDemand).where(AgentDemand.channel_ref == channel_ref)
                    )
                ).scalars()
            )
            notifications = list(
                (
                    await db.execute(
                        select(Notification).where(Notification.event_key == event_key)
                    )
                ).scalars()
            )
        assert len(demands) == len(notifications) == 1
    finally:
        await _remove_monitoring_records(
            channel_ref=channel_ref,
            event_key=event_key,
            created_athos_id=athos.id if athos_created else None,
        )


@pytest.mark.asyncio
async def test_athos_request_rejects_an_unrelated_demand_notification_collision(
    activity_world,
    activity_client,
):
    athos, athos_created = await _get_or_create_athos()
    key = f"activity-collision-{uuid.uuid4()}"
    channel_ref = f"agent-activity:{key}"
    event_key = f"agent-activity:athos-monitor:{key}"
    try:
        async with AsyncSessionLocal() as db:
            unrelated = AgentDemand(
                from_agent="unrelated",
                target_agent_id=athos.id,
                project_id=activity_world.project_id,
                subject="Unrelated demand",
                body="This is not the monitoring contract.",
                channel="agent",
                channel_ref=channel_ref,
                requires_response=True,
            )
            db.add(unrelated)
            await db.flush()
            db.add(
                Notification(
                    source="system",
                    severity="warning",
                    title="Unrelated notification",
                    message="This is not the monitoring contract.",
                    event_key=event_key,
                    occurred_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()

        response = await activity_client.post(
            f"/api/v1/agent-activity/incidents/execution_failed:{activity_world.execution_id}:request-athos-monitoring",
            json={"execution_id": str(activity_world.execution_id), "idempotency_key": key},
        )

        assert response.status_code == 409
    finally:
        await _remove_monitoring_records(
            channel_ref=channel_ref,
            event_key=event_key,
            created_athos_id=athos.id if athos_created else None,
        )


@pytest.mark.asyncio
async def test_athos_request_rejects_notification_mismatched_to_existing_demand(
    activity_world,
    activity_client,
):
    athos, athos_created = await _get_or_create_athos()
    key = f"activity-notification-collision-{uuid.uuid4()}"
    channel_ref = f"agent-activity:{key}"
    event_key = f"agent-activity:athos-monitor:{key}"
    incident_key = f"execution_failed:{activity_world.execution_id}"
    try:
        created = await activity_client.post(
            f"/api/v1/agent-activity/incidents/{incident_key}:request-athos-monitoring",
            json={"execution_id": str(activity_world.execution_id), "idempotency_key": key},
        )
        assert created.status_code == 201
        async with AsyncSessionLocal() as db:
            notification = (
                await db.execute(
                    select(Notification).where(Notification.event_key == event_key)
                )
            ).scalar_one()
            notification.title = "Not the Athos monitoring notification"
            await db.commit()

        collision = await activity_client.post(
            f"/api/v1/agent-activity/incidents/{incident_key}:request-athos-monitoring",
            json={"execution_id": str(activity_world.execution_id), "idempotency_key": key},
        )

        assert collision.status_code == 409
    finally:
        await _remove_monitoring_records(
            channel_ref=channel_ref,
            event_key=event_key,
            created_athos_id=athos.id if athos_created else None,
        )


@pytest.mark.asyncio
async def test_athos_request_rejects_orphan_monitoring_notification(
    activity_world,
    activity_client,
):
    key = f"activity-orphan-{uuid.uuid4()}"
    event_key = f"agent-activity:athos-monitor:{key}"
    try:
        async with AsyncSessionLocal() as db:
            db.add(
                Notification(
                    source="system",
                    severity="warning",
                    title="Orphan monitoring notification",
                    message="No corresponding demand exists.",
                    event_key=event_key,
                    occurred_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()

        response = await activity_client.post(
            f"/api/v1/agent-activity/incidents/execution_failed:{activity_world.execution_id}:request-athos-monitoring",
            json={"execution_id": str(activity_world.execution_id), "idempotency_key": key},
        )

        assert response.status_code == 409
    finally:
        await _remove_monitoring_records(event_key=event_key)


@pytest.mark.asyncio
async def test_build_activity_projects_pre_project_conception_context():
    """An active conception is visible without manufacturing a Project."""

    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        product = Product(name=f"Pre-project activity {suffix}", status="concept")
        db.add(product)
        await db.flush()
        request = DevelopmentRequest(
            product_id=product.id,
            request_type="new_product",
            title="Define the operational control plane",
            description="Canonical intake for a product still in conception.",
            status="accepted",
        )
        concept = ProductConcept(product_id=product.id, status="draft")
        db.add_all([request, concept])
        await db.flush()
        revision = ProductConceptRevision(
            concept_id=concept.id,
            revision=1,
            problem_statement="Operators need one continuous activity view.",
            working_directory_path="/root/project/pre-project",
            content_hash=uuid.uuid4().hex.ljust(64, "0"),
        )
        db.add(revision)
        await db.flush()
        concept.current_revision_id = revision.id
        await db.commit()
        ids = (product.id, request.id, concept.id, revision.id)

    try:
        async with AsyncSessionLocal() as db:
            result = await build_agent_activity(db, project_id=None, window_minutes=60)

        context = next(item for item in result.contexts if item.concept_id == ids[2])
        assert context.context_kind == "conception"
        assert context.context_id == ids[2]
        assert context.development_request_id == ids[1]
        assert context.concept_revision_id == ids[3]
        assert context.project_id is None
        assert context.canonical_path == f"/conception?request={ids[1]}"
        assert any(
            item.source_type == "product_concept"
            and item.source_id == ids[2]
            and item.context_id == ids[2]
            and item.stage == "planning"
            for item in result.flow_items
        )
        assert any(
            event.key == f"product-concept:{ids[2]}"
            and event.context_id == ids[2]
            and event.lane == "planning"
            for event in result.timeline
        )
    finally:
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE company.product_concepts SET current_revision_id = NULL WHERE id = :id"),
                {"id": ids[2]},
            )
            await conn.execute(text("DELETE FROM company.product_concept_revisions WHERE id = :id"), {"id": ids[3]})
            await conn.execute(text("DELETE FROM company.product_concepts WHERE id = :id"), {"id": ids[2]})
            await conn.execute(text("DELETE FROM company.development_requests WHERE id = :id"), {"id": ids[1]})
            await conn.execute(text("DELETE FROM company.products WHERE id = :id"), {"id": ids[0]})


@pytest.mark.asyncio
async def test_build_activity_preserves_conception_transition_to_multiple_projects():
    """Delivery projects retain the exact conception lineage without duplicating history."""

    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        product = Product(name=f"Transition activity {suffix}", status="active")
        db.add(product)
        await db.flush()
        request = DevelopmentRequest(
            product_id=product.id,
            request_type="feature",
            title="Authorize multi-project delivery",
            description="One conception creates two delivery projects.",
            status="converted",
        )
        concept = ProductConcept(product_id=product.id, status="approved")
        db.add_all([request, concept])
        await db.flush()
        concept_revision = ProductConceptRevision(
            concept_id=concept.id,
            revision=1,
            problem_statement="Delivery spans web and API projects.",
            content_hash=uuid.uuid4().hex.ljust(64, "0"),
        )
        db.add(concept_revision)
        await db.flush()
        concept.current_revision_id = concept_revision.id
        version = ProductVersion(product_id=product.id, version=f"0.1.{suffix}")
        blueprint = SystemBlueprint(product_id=product.id, name=f"Blueprint {suffix}")
        db.add_all([version, blueprint])
        await db.flush()
        blueprint_revision = SystemBlueprintRevision(
            blueprint_id=blueprint.id,
            revision=1,
            status="approved",
            concept_revision_id=concept_revision.id,
            product_version_id=version.id,
        )
        first_project = Project(
            name=f"Web delivery {suffix}",
            product_version_id=version.id,
            solution_type="web_app",
        )
        second_project = Project(
            name=f"API delivery {suffix}",
            product_version_id=version.id,
            solution_type="api_service",
        )
        db.add_all([blueprint_revision, first_project, second_project])
        await db.flush()
        blueprint.current_revision_id = blueprint_revision.id
        await db.commit()
        ids = {
            "product": product.id,
            "request": request.id,
            "concept": concept.id,
            "concept_revision": concept_revision.id,
            "version": version.id,
            "blueprint": blueprint.id,
            "blueprint_revision": blueprint_revision.id,
            "projects": {first_project.id, second_project.id},
        }

    try:
        async with AsyncSessionLocal() as db:
            result = await build_agent_activity(db, project_id=None, window_minutes=60)

        conception_contexts = [
            item for item in result.contexts if item.concept_id == ids["concept"] and item.context_kind == "conception"
        ]
        project_contexts = [
            item for item in result.contexts if item.project_id in ids["projects"]
        ]
        assert len(conception_contexts) == 1
        assert {item.project_id for item in project_contexts} == ids["projects"]
        assert {item.concept_id for item in project_contexts} == {ids["concept"]}
        assert {item.concept_revision_id for item in project_contexts} == {ids["concept_revision"]}
        assert len([event for event in result.timeline if event.key == f"product-concept:{ids['concept']}"]) == 1
        assert {
            (relation.from_type, relation.from_id, relation.to_type, relation.to_id)
            for relation in result.topology_relations
            if relation.kind == "transition" and relation.from_id == str(ids["concept"])
        } == {
            ("conception", str(ids["concept"]), "project", str(project_id))
            for project_id in ids["projects"]
        }
    finally:
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE company.system_blueprints SET current_revision_id = NULL WHERE id = :id"),
                {"id": ids["blueprint"]},
            )
            await conn.execute(
                text("UPDATE company.product_concepts SET current_revision_id = NULL WHERE id = :id"),
                {"id": ids["concept"]},
            )
            await conn.execute(text("DELETE FROM company.projects WHERE id = ANY(:ids)"), {"ids": list(ids["projects"])})
            await conn.execute(text("DELETE FROM company.system_blueprint_revisions WHERE id = :id"), {"id": ids["blueprint_revision"]})
            await conn.execute(text("DELETE FROM company.system_blueprints WHERE id = :id"), {"id": ids["blueprint"]})
            await conn.execute(text("DELETE FROM company.product_versions WHERE id = :id"), {"id": ids["version"]})
            await conn.execute(text("DELETE FROM company.product_concept_revisions WHERE id = :id"), {"id": ids["concept_revision"]})
            await conn.execute(text("DELETE FROM company.product_concepts WHERE id = :id"), {"id": ids["concept"]})
            await conn.execute(text("DELETE FROM company.development_requests WHERE id = :id"), {"id": ids["request"]})
            await conn.execute(text("DELETE FROM company.products WHERE id = :id"), {"id": ids["product"]})

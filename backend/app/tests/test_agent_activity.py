import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import pytest
import pytest_asyncio
import httpx
from sqlalchemy import text

from app.core.agent_activity import build_agent_activity
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
from app.db.models.project import Project
from app.db.models.task import ProjectTask, TaskAssignment, TaskExecution


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
        )
        db.add_all([task, agent])
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

import uuid
from datetime import datetime, timezone

import pytest


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

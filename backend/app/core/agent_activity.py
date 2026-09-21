"""Read-only aggregation for the canonical Agent Activity view.

The builders in this module copy structured state from existing domain
records.  Message prose is display-only: it is never parsed to infer identity,
ownership, execution state, checkpoints, or approvals.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.agent_activity import (
    ActivityAgentOut,
    ActivityCheckpointOut,
    ActivityContextOut,
    ActivityCurrentWorkOut,
    ActivityFlowItemOut,
    ActivityIncidentOut,
    ActivityMessageEdgeOut,
    ActivityPriorAttemptOut,
    ActivityProfileSummaryOut,
    ActivityProjectOut,
    ActivityRecordLinkOut,
    ActivityResourceOut,
    ActivitySourceFreshnessOut,
    ActivityTimelineEventOut,
    ActivityTopologyRelationOut,
    AgentActivityOut,
)
from app.core.forgerouter_sync import (
    ForgeRouterActivityEvent,
    read_recent_forgerouter_activity,
)
from app.db.models.agent import Agent
from app.db.models.backlog import PlanningItem
from app.db.models.demand import AgentDemand
from app.db.models.execution import ExecutionLease, ExecutionWorkPackage
from app.db.models.governance import ApprovalRequest
from app.db.models.notification import Notification
from app.db.models.orchestration import ProjectAgentMembership
from app.db.models.progress import ProgressCheckpoint
from app.db.models.project import ChangeRequest, Project
from app.db.models.task import ProjectTask, TaskAssignment, TaskExecution
from app.db.models.product import Product, ProductVersion
from app.db.models.system_scope import (
    DevelopmentRequest,
    ProductConcept,
    ProductConceptRevision,
    SystemBlueprintRevision,
)

ROW_LIMIT = 500
FORGEROUTER_LIMIT = 200
ACTIVE_EXECUTION_STATUSES = {"pending", "running", "reported"}

CONCEPT_FLOW_STAGE: dict[str, str] = {
    "draft": "planning",
    "in_review": "attention",
    "hold": "attention",
    "rework": "attention",
    "approved": "completed",
    "rejected": "archived",
    "superseded": "archived",
}

FLOW_STAGE_BY_SOURCE: dict[str, dict[str, str]] = {
    "agent_demand": {
        "new": "incoming",
        "read": "incoming",
        "incubating": "planning",
        "decision_pending": "attention",
        "promoted": "planning",
        "dropped": "archived",
        "dispatched": "queued",
        "running": "executing",
        "completed": "completed",
        "failed": "attention",
        "converted": "planning",
        "archived": "archived",
    },
    "project_task": {
        "planned": "planning",
        "ready": "queued",
        "assigned": "queued",
        "in_progress": "executing",
        "blocked": "attention",
        "done": "completed",
        "deployed": "completed",
        "cancelled": "archived",
    },
    "task_execution": {
        "pending": "queued",
        "running": "executing",
        "reported": "verifying",
        "verified": "verifying",
        "reconciling": "verifying",
        "recovering": "verifying",
        "completed": "completed",
        "failed": "attention",
        "blocked": "attention",
        "paused": "attention",
        "retried": "queued",
    },
    "approval_request": {
        "pending": "attention",
        "approved": "completed",
        "rejected": "attention",
    },
}


def classify_flow_stage(source_type: str, source_status: str) -> str:
    """Map a canonical domain status into the read-only operational display."""

    return FLOW_STAGE_BY_SOURCE.get(source_type, {}).get(source_status, "attention")


@dataclass(frozen=True)
class TaskActivityContext:
    """Task row plus its canonical project, resolved through PlanningItem."""

    task: ProjectTask
    project: Project | None


@dataclass(frozen=True)
class ExecutionActivityContext:
    """Structured records that describe one execution attempt."""

    execution: TaskExecution
    assignment: TaskAssignment | None
    work_package: ExecutionWorkPackage | None
    lease: ExecutionLease | None
    source_demand: AgentDemand | None

    @property
    def agent_id(self) -> uuid.UUID | None:
        return self.assignment.agent_id if self.assignment else None


def _task_context(value: TaskActivityContext | ProjectTask | None) -> TaskActivityContext | None:
    if value is None:
        return None
    if isinstance(value, TaskActivityContext):
        return value
    return TaskActivityContext(task=value, project=None)


def _execution_context(
    value: ExecutionActivityContext | TaskExecution,
) -> ExecutionActivityContext:
    if isinstance(value, ExecutionActivityContext):
        return value
    return ExecutionActivityContext(
        execution=value,
        assignment=None,
        work_package=None,
        lease=None,
        source_demand=None,
    )


def _checkpoint_out(
    checkpoint: ProgressCheckpoint,
    *,
    task_id: uuid.UUID | None,
) -> ActivityCheckpointOut:
    evidence_summary = ", ".join(str(item) for item in checkpoint.evidence_refs) or None
    verification = checkpoint.state_snapshot.get("verification_summary")
    return ActivityCheckpointOut(
        id=checkpoint.id,
        execution_id=checkpoint.task_execution_id,
        occurred_at=checkpoint.last_confirmed_at,
        status=checkpoint.checkpoint_type,
        resume_from_step_key=checkpoint.resume_from_step_key,
        summary=checkpoint.message,
        evidence_summary=evidence_summary,
        verification_summary=str(verification) if verification is not None else None,
        error_code=checkpoint.error_code,
        blocker_code=checkpoint.blocker_code,
        canonical_path=f"/tasks/{task_id}?checkpoint={checkpoint.id}",
    )


def _runtime_events_by_agent(
    forgerouter_state: Iterable[ForgeRouterActivityEvent],
) -> dict[str, ForgeRouterActivityEvent]:
    latest: dict[str, ForgeRouterActivityEvent] = {}
    for event in sorted(forgerouter_state, key=lambda item: item.created_at, reverse=True):
        if not event.agent_name:
            continue
        latest.setdefault(event.agent_name.casefold(), event)
    return latest


def build_activity_agents(
    *,
    agents: Iterable[Agent],
    tasks_by_id: dict[uuid.UUID, TaskActivityContext | ProjectTask],
    executions: Iterable[ExecutionActivityContext | TaskExecution],
    checkpoints_by_execution: dict[uuid.UUID, ProgressCheckpoint],
    forgerouter_state: Iterable[ForgeRouterActivityEvent],
) -> list[ActivityAgentOut]:
    """Build agent nodes from explicit assignments and runtime attribution."""

    contexts = [_execution_context(item) for item in executions]
    executions_by_agent: dict[uuid.UUID, list[ExecutionActivityContext]] = defaultdict(list)
    for context in contexts:
        if context.agent_id:
            executions_by_agent[context.agent_id].append(context)
    runtime_by_agent = _runtime_events_by_agent(forgerouter_state)

    result: list[ActivityAgentOut] = []
    seen_agent_names: set[str] = set()
    for agent in sorted(agents, key=lambda item: (item.name.casefold(), str(item.id))):
        base_name = agent.name.split("@")[0].strip().casefold()
        if base_name in seen_agent_names:
            continue
        seen_agent_names.add(base_name)
        agent_executions = sorted(
            executions_by_agent.get(agent.id, []),
            key=lambda item: (
                item.execution.updated_at,
                item.execution.started_at or item.execution.created_at,
            ),
            reverse=True,
        )
        current = agent_executions[0] if agent_executions else None
        current_work = None
        latest_checkpoint = None
        last_heartbeat_at = None
        if current:
            execution = current.execution
            task_context = _task_context(tasks_by_id.get(execution.task_id))
            task = task_context.task if task_context else None
            project = task_context.project if task_context else None
            demand = current.source_demand
            work_package = current.work_package
            payload = work_package.payload if work_package else {}
            current_work = ActivityCurrentWorkOut(
                project_id=project.id if project else None,
                project_name=project.name if project else None,
                project_path=f"/projects/{project.id}" if project else None,
                task_id=task.id if task else execution.task_id,
                task_title=task.title if task else None,
                task_path=f"/tasks/{execution.task_id}",
                assignment_id=execution.assignment_id,
                work_package_id=execution.work_package_id,
                execution_id=execution.id,
                execution_path=f"/tasks/{execution.task_id}?execution={execution.id}",
                action=execution.status,
                branch=payload.get("branch") if isinstance(payload, dict) else None,
                working_directory_path=project.working_directory_path if project else None,
                requested_by_agent_id=demand.from_agent_id if demand else None,
                source_message_id=demand.id if demand else None,
                source_message_path=f"/demands?message={demand.id}" if demand else None,
            )
            checkpoint = checkpoints_by_execution.get(execution.id)
            if checkpoint:
                latest_checkpoint = _checkpoint_out(checkpoint, task_id=execution.task_id)
            if current.lease:
                last_heartbeat_at = current.lease.heartbeat_at

        runtime_event = runtime_by_agent.get(agent.name.casefold())
        if runtime_event and (
            runtime_event.status.casefold() in {"pending", "routing", "running"}
        ):
            availability = "busy"
            reason = "Recent ForgeRouter activity"
        elif current and current.execution.status in ACTIVE_EXECUTION_STATUSES:
            availability = "busy"
            reason = f"Execution {current.execution.status}"
        elif current and current.execution.status == "failed":
            availability = "degraded"
            reason = "Latest execution failed"
        elif not agent.is_active or agent.status != "active":
            availability = "unavailable"
            reason = f"Agent status is {agent.status}"
        else:
            availability = "available"
            reason = None

        checked_at = datetime.now(timezone.utc)
        result.append(
            ActivityAgentOut(
                id=agent.id,
                name=agent.name,
                avatar_data_url=agent.avatar_data_url,
                profile_slug=agent.profile_slug,
                runtime_type=agent.runtime_type or "unknown",
                availability=availability,
                availability_reason=reason,
                last_heartbeat_at=last_heartbeat_at,
                canonical_path=f"/agents/{agent.id}",
                current_work=current_work,
                latest_checkpoint=latest_checkpoint,
                profile_summary=ActivityProfileSummaryOut(
                    status="healthy" if agent.has_profile else "warning",
                    checked_at=checked_at,
                    runtime_native=True,
                    canonical_path=f"/agents/{agent.id}",
                    profile_path=agent.effective_home_path,
                    last_heartbeat_at=last_heartbeat_at,
                    issues=[] if agent.has_profile else ["Profile metadata is not registered"],
                ),
            )
        )
    return result


def build_message_edges(
    *,
    demands: Iterable[AgentDemand],
    agents: Iterable[Agent],
    replies: Iterable[AgentDemand] = (),
    development_requests: Iterable[DevelopmentRequest] = (),
) -> list[ActivityMessageEdgeOut]:
    """Build communication edges exclusively from structured message fields."""

    rows = list(demands)
    names_by_id = {agent.id: agent.name for agent in agents}
    requests_by_id = {request.id: request for request in development_requests}
    parent_ids = {demand.id for demand in rows}
    replies_by_parent: dict[uuid.UUID, AgentDemand] = {}
    for reply in sorted(
        {reply.id: reply for reply in [*rows, *replies]}.values(),
        key=lambda item: (item.updated_at, item.created_at, str(item.id)),
        reverse=True,
    ):
        if reply.reply_to_id in parent_ids:
            replies_by_parent.setdefault(reply.reply_to_id, reply)
    edges: list[ActivityMessageEdgeOut] = []
    for demand in rows:
        reply = replies_by_parent.get(demand.id)
        waiting = bool(demand.requires_response and reply is None)
        development_request = requests_by_id.get(demand.development_request_id)
        edges.append(
            ActivityMessageEdgeOut(
                message_id=demand.id,
                from_agent_id=demand.from_agent_id,
                from_agent_name=names_by_id.get(demand.from_agent_id),
                target_agent_id=demand.target_agent_id,
                target_agent_name=names_by_id.get(demand.target_agent_id),
                reply_to_id=demand.reply_to_id,
                project_id=demand.project_id,
                development_request_id=demand.development_request_id,
                product_id=development_request.product_id if development_request else None,
                task_id=demand.origin_id if demand.origin_type == "task" else None,
                subject=demand.subject,
                dispatch_status=demand.dispatch_status or demand.status,
                requires_response=demand.requires_response,
                response_status="responded" if reply else None,
                waiting_for_response=waiting,
                waiting_on_agent_id=demand.target_agent_id if waiting else None,
                sent_at=demand.created_at,
                updated_at=demand.updated_at,
                responded_at=reply.created_at if reply else None,
                canonical_path=f"/demands?message={demand.id}",
                factory_context_path=(
                    f"/conception?request={demand.development_request_id}"
                    if demand.development_request_id
                    else (f"/projects/{demand.project_id}" if demand.project_id else None)
                ),
            )
        )
    return sorted(edges, key=lambda item: item.updated_at, reverse=True)


def classify_runtime_failure(
    error: str | None,
    existing_error_code: str | None = None,
) -> tuple[str, str | None]:
    """Classify only explicit runtime evidence; never interpret ownership prose."""

    evidence = (error or "").casefold()
    if any(marker in evidence for marker in ("quota", "rate limit", "usage limit")):
        return "runtime_limit", "RUNTIME_LIMIT"
    return "execution_failed", existing_error_code


def _prior_attempts(
    current: ExecutionActivityContext,
    executions: list[ExecutionActivityContext],
    checkpoints_by_execution: dict[uuid.UUID, ProgressCheckpoint],
) -> list[ActivityPriorAttemptOut]:
    rows: list[ActivityPriorAttemptOut] = []
    for context in executions:
        execution = context.execution
        if execution.task_id != current.execution.task_id or execution.id == current.execution.id:
            continue
        if execution.attempt_number >= current.execution.attempt_number:
            continue
        checkpoint = checkpoints_by_execution.get(execution.id)
        rows.append(
            ActivityPriorAttemptOut(
                id=execution.id,
                execution_id=execution.id,
                attempt_number=execution.attempt_number,
                started_at=execution.started_at or execution.created_at,
                completed_at=execution.finished_at,
                outcome=execution.status,
                error_code=checkpoint.error_code if checkpoint else None,
                summary=execution.outcome_summary,
                canonical_path=f"/tasks/{execution.task_id}?execution={execution.id}",
            )
        )
    return sorted(rows, key=lambda item: item.attempt_number, reverse=True)


def build_incidents(
    *,
    demands: Iterable[AgentDemand],
    executions: Iterable[ExecutionActivityContext | TaskExecution],
    checkpoints_by_execution: dict[uuid.UUID, ProgressCheckpoint],
    approvals: Iterable[ApprovalRequest],
    forgerouter_state: Iterable[ForgeRouterActivityEvent],
) -> list[ActivityIncidentOut]:
    """Derive incidents from explicit failure, checkpoint, and approval records."""

    del forgerouter_state  # Runtime events affect availability, not durable failure state.
    demand_by_execution = {
        demand.task_execution_id: demand
        for demand in demands
        if demand.task_execution_id is not None
    }
    contexts = [_execution_context(item) for item in executions]
    incidents: list[ActivityIncidentOut] = []
    covered_execution_ids: set[uuid.UUID] = set()

    for context in contexts:
        execution = context.execution
        checkpoint = checkpoints_by_execution.get(execution.id)
        demand = demand_by_execution.get(execution.id) or context.source_demand
        if execution.status != "failed" and not (
            checkpoint
            and checkpoint.checkpoint_type
            in {"blocked", "failed", "heartbeat_lost", "paused"}
        ):
            continue
        if checkpoint and checkpoint.checkpoint_type == "heartbeat_lost":
            kind = "heartbeat_lost"
            error_code = checkpoint.error_code
        elif checkpoint and checkpoint.checkpoint_type == "blocked":
            kind = "blocked"
            error_code = checkpoint.error_code
        else:
            kind, error_code = classify_runtime_failure(
                demand.dispatch_error if demand else None,
                checkpoint.error_code if checkpoint else None,
            )
        occurred_at = (
            checkpoint.last_confirmed_at
            if checkpoint
            else execution.finished_at or execution.updated_at
        )
        covered_execution_ids.add(execution.id)
        related_records = []
        if demand:
            related_records.append(
                ActivityRecordLinkOut(
                    source_type="agent_demand",
                    source_id=demand.id,
                    canonical_path=f"/demands?message={demand.id}",
                    label=demand.subject,
                )
            )
        incidents.append(
            ActivityIncidentOut(
                key=f"{kind}:{execution.id}",
                kind=kind,
                severity="error" if kind != "blocked" else "warning",
                title={
                    "heartbeat_lost": "Execution heartbeat lost",
                    "blocked": "Execution blocked",
                    "runtime_limit": "Runtime limit reached",
                }.get(kind, "Execution failed"),
                occurred_at=occurred_at,
                source_type="task_execution",
                source_id=execution.id,
                affected_agent_id=context.agent_id,
                task_id=execution.task_id,
                execution_id=execution.id,
                checkpoint_id=checkpoint.id if checkpoint else None,
                resume_from_step_key=checkpoint.resume_from_step_key if checkpoint else None,
                error_code=error_code,
                blocker_code=checkpoint.blocker_code if checkpoint else None,
                summary=(
                    checkpoint.message
                    if checkpoint and checkpoint.message
                    else execution.outcome_summary
                ),
                recommended_action="request_athos_monitoring",
                prior_attempts=_prior_attempts(
                    context,
                    contexts,
                    checkpoints_by_execution,
                ),
                last_observed_at=execution.updated_at,
                runtime_type=execution.runtime_type,
                current_owner_agent_id=context.agent_id,
                canonical_path=f"/tasks/{execution.task_id}?execution={execution.id}",
                related_records=related_records,
            )
        )

    for demand in demands:
        if demand.dispatch_status != "failed" or demand.task_execution_id in covered_execution_ids:
            continue
        kind, error_code = classify_runtime_failure(demand.dispatch_error)
        incidents.append(
            ActivityIncidentOut(
                key=f"{kind}:message:{demand.id}",
                kind=kind,
                severity="error",
                title="Runtime limit reached" if kind == "runtime_limit" else "Dispatch failed",
                occurred_at=demand.updated_at,
                source_type="agent_demand",
                source_id=demand.id,
                affected_agent_id=demand.target_agent_id,
                project_id=demand.project_id,
                task_id=demand.origin_id if demand.origin_type == "task" else None,
                execution_id=demand.task_execution_id,
                error_code=error_code,
                summary=demand.dispatch_error,
                recommended_action="request_athos_monitoring",
                last_observed_at=demand.updated_at,
                current_owner_agent_id=demand.target_agent_id,
                canonical_path=f"/demands?message={demand.id}",
            )
        )

    for approval in approvals:
        if approval.status != "pending":
            continue
        task_id = approval.target_id if approval.target_type == "project_task" else None
        incidents.append(
            ActivityIncidentOut(
                key=f"approval_pending:{approval.id}",
                kind="approval_pending",
                severity="warning",
                title="Approval pending",
                occurred_at=approval.created_at,
                source_type="approval_request",
                source_id=approval.id,
                affected_agent_id=(
                    approval.requested_by_id
                    if approval.requested_by_type == "agent"
                    else None
                ),
                task_id=task_id,
                summary=approval.approval_type,
                recommended_action="open_approval",
                last_observed_at=approval.updated_at,
                canonical_path=f"/governance/{approval.id}",
            )
        )

    return sorted(
        incidents,
        key=lambda item: (item.occurred_at, item.key),
        reverse=True,
    )


def _demand_flow_status(demand: AgentDemand) -> str:
    """Choose the demand state that best describes its current processing position."""

    if demand.dispatch_status in {"failed", "running", "dispatched"}:
        return demand.dispatch_status
    if demand.status == "archived":
        return "archived"
    if demand.dispatch_status == "completed":
        return "completed"
    if demand.origin_type == "incubation" and demand.incubation_state:
        return demand.incubation_state
    return demand.status


def build_flow_items(
    *,
    demands: Iterable[AgentDemand],
    tasks_by_id: dict[uuid.UUID, TaskActivityContext | ProjectTask],
    executions: Iterable[ExecutionActivityContext | TaskExecution],
    approvals: Iterable[ApprovalRequest],
) -> list[ActivityFlowItemOut]:
    """Project canonical records into mutually exclusive operational stages."""

    items: list[ActivityFlowItemOut] = []
    contexts = [_execution_context(item) for item in executions]
    latest_execution_by_task: dict[uuid.UUID, ExecutionActivityContext] = {}
    for context in sorted(
        contexts,
        key=lambda item: (item.execution.updated_at, str(item.execution.id)),
        reverse=True,
    ):
        latest_execution_by_task.setdefault(context.execution.task_id, context)

    for demand in demands:
        source_status = _demand_flow_status(demand)
        items.append(
            ActivityFlowItemOut(
                key=f"agent_demand:{demand.id}",
                stage=classify_flow_stage("agent_demand", source_status),
                source_type="agent_demand",
                source_id=demand.id,
                source_status=source_status,
                title=demand.subject,
                occurred_at=demand.created_at,
                updated_at=demand.updated_at,
                canonical_path=f"/demands?message={demand.id}",
                agent_id=demand.target_agent_id,
                project_id=demand.project_id,
                task_id=demand.origin_id if demand.origin_type == "task" else None,
                execution_id=demand.task_execution_id,
            )
        )

    for task_id, value in tasks_by_id.items():
        task_context = _task_context(value)
        if not task_context or task_id in latest_execution_by_task:
            continue
        task = task_context.task
        items.append(
            ActivityFlowItemOut(
                key=f"project_task:{task.id}",
                stage=classify_flow_stage("project_task", task.status),
                source_type="project_task",
                source_id=task.id,
                source_status=task.status,
                title=task.title,
                occurred_at=task.created_at,
                updated_at=task.updated_at,
                canonical_path=f"/tasks/{task.id}",
                project_id=task_context.project.id if task_context.project else None,
                task_id=task.id,
            )
        )

    for task_id, context in latest_execution_by_task.items():
        execution = context.execution
        task_context = _task_context(tasks_by_id.get(task_id))
        task = task_context.task if task_context else None
        items.append(
            ActivityFlowItemOut(
                key=f"task_execution:{execution.id}",
                stage=classify_flow_stage("task_execution", execution.status),
                source_type="task_execution",
                source_id=execution.id,
                source_status=execution.status,
                title=task.title if task else f"Execution {execution.attempt_number}",
                occurred_at=execution.started_at or execution.created_at,
                updated_at=execution.updated_at,
                canonical_path=f"/tasks/{execution.task_id}?execution={execution.id}",
                agent_id=context.agent_id,
                project_id=(
                    task_context.project.id
                    if task_context and task_context.project
                    else None
                ),
                task_id=execution.task_id,
                execution_id=execution.id,
            )
        )

    for approval in approvals:
        task_context = (
            _task_context(tasks_by_id.get(approval.target_id))
            if approval.target_type == "project_task"
            else None
        )
        items.append(
            ActivityFlowItemOut(
                key=f"approval_request:{approval.id}",
                stage=classify_flow_stage("approval_request", approval.status),
                source_type="approval_request",
                source_id=approval.id,
                source_status=approval.status,
                title=f"Approval: {approval.approval_type}",
                occurred_at=approval.created_at,
                updated_at=approval.updated_at,
                canonical_path=f"/governance/{approval.id}",
                agent_id=(
                    approval.requested_by_id
                    if approval.requested_by_type == "agent"
                    else None
                ),
                project_id=(
                    task_context.project.id
                    if task_context and task_context.project
                    else approval.target_id
                    if approval.target_type == "project"
                    else None
                ),
                task_id=(
                    approval.target_id
                    if approval.target_type == "project_task"
                    else None
                ),
            )
        )

    return sorted(items, key=lambda item: (item.updated_at, item.key), reverse=True)


def build_timeline(
    *,
    demands: Iterable[AgentDemand],
    executions: Iterable[ExecutionActivityContext | TaskExecution],
    checkpoints_by_execution: dict[uuid.UUID, ProgressCheckpoint],
    approvals: Iterable[ApprovalRequest],
    notifications: Iterable[Notification],
) -> list[ActivityTimelineEventOut]:
    """Create a stable timeline directly from canonical record timestamps."""

    events: list[ActivityTimelineEventOut] = []
    for demand in demands:
        events.append(
            ActivityTimelineEventOut(
                key=f"message:{demand.id}",
                kind="message_sent",
                occurred_at=demand.created_at,
                source_type="agent_demand",
                source_id=demand.id,
                source_status=demand.dispatch_status or demand.status,
                lane="communication",
                title=demand.subject,
                canonical_path=f"/demands?message={demand.id}",
                agent_id=demand.target_agent_id,
                project_id=demand.project_id,
                task_id=demand.origin_id if demand.origin_type == "task" else None,
                execution_id=demand.task_execution_id,
            )
        )
    for value in executions:
        context = _execution_context(value)
        execution = context.execution
        events.append(
            ActivityTimelineEventOut(
                key=f"execution:{execution.id}:{execution.status}",
                kind=f"execution_{execution.status}",
                occurred_at=execution.finished_at or execution.started_at or execution.created_at,
                source_type="task_execution",
                source_id=execution.id,
                source_status=execution.status,
                lane="execution",
                title=f"Execution {execution.status}",
                canonical_path=f"/tasks/{execution.task_id}?execution={execution.id}",
                summary=execution.outcome_summary,
                agent_id=context.agent_id,
                task_id=execution.task_id,
                execution_id=execution.id,
            )
        )
    for execution_id, checkpoint in checkpoints_by_execution.items():
        events.append(
            ActivityTimelineEventOut(
                key=f"checkpoint:{checkpoint.id}",
                kind=f"checkpoint_{checkpoint.checkpoint_type}",
                occurred_at=checkpoint.last_confirmed_at,
                source_type="progress_checkpoint",
                source_id=checkpoint.id,
                source_status=checkpoint.checkpoint_type,
                lane="checkpoint",
                title=checkpoint.step_label,
                canonical_path=f"/tasks/{checkpoint.task_id}?checkpoint={checkpoint.id}",
                summary=checkpoint.message,
                agent_id=checkpoint.actor_id if checkpoint.actor_type == "agent" else None,
                project_id=checkpoint.project_id,
                task_id=checkpoint.task_id,
                execution_id=execution_id,
                checkpoint_id=checkpoint.id,
            )
        )
    for approval in approvals:
        task_id = approval.target_id if approval.target_type == "project_task" else None
        events.append(
            ActivityTimelineEventOut(
                key=f"approval:{approval.id}:{approval.status}",
                kind=f"approval_{approval.status}",
                occurred_at=approval.updated_at,
                source_type="approval_request",
                source_id=approval.id,
                source_status=approval.status,
                lane="governance",
                title=f"Approval {approval.status}",
                canonical_path=f"/governance/{approval.id}",
                summary=approval.approval_type,
                agent_id=(
                    approval.requested_by_id
                    if approval.requested_by_type == "agent"
                    else None
                ),
                task_id=task_id,
                approval_id=approval.id,
            )
        )
    for notification in notifications:
        events.append(
            ActivityTimelineEventOut(
                key=f"notification:{notification.id}",
                kind="notification",
                occurred_at=notification.occurred_at,
                source_type="notification",
                source_id=notification.id,
                source_status=notification.severity,
                lane="communication",
                title=notification.title,
                canonical_path=f"/notifications/{notification.id}",
                summary=notification.summary or notification.message,
                notification_id=notification.id,
            )
        )
    return sorted(events, key=lambda item: (item.occurred_at, item.key), reverse=True)


async def _load_forgerouter_state(
    *,
    window_minutes: int,
) -> tuple[list[ForgeRouterActivityEvent], ActivitySourceFreshnessOut]:
    checked_at = datetime.now(timezone.utc)
    try:
        events = await read_recent_forgerouter_activity(
            since_seconds=window_minutes * 60,
            limit=FORGEROUTER_LIMIT,
        )
    except Exception:
        return [], ActivitySourceFreshnessOut(
            name="forgerouter",
            status="unavailable",
            checked_at=checked_at,
            detail="ForgeRouter activity is unavailable",
            error_code="FORGEROUTER_UNAVAILABLE",
        )
    observed_at = max((event.created_at for event in events), default=None)
    age_seconds = None
    if observed_at is not None:
        age_seconds = max(0, int((checked_at - observed_at).total_seconds()))
    return events, ActivitySourceFreshnessOut(
        name="forgerouter",
        status="fresh",
        checked_at=checked_at,
        observed_at=observed_at,
        age_seconds=age_seconds,
    )


async def build_agent_activity(
    db: AsyncSession,
    *,
    project_id: uuid.UUID | None,
    window_minutes: int,
) -> AgentActivityOut:
    """Aggregate bounded canonical state while tolerating optional telemetry loss."""

    generated_at = datetime.now(timezone.utc)
    since = generated_at - timedelta(minutes=window_minutes)

    demand_filters = [AgentDemand.updated_at >= since]
    if project_id is not None:
        demand_filters.append(AgentDemand.project_id == project_id)
    demands = list(
        (
            await db.execute(
                select(AgentDemand)
                .where(*demand_filters)
                .order_by(AgentDemand.updated_at.desc())
                .limit(ROW_LIMIT)
            )
        ).scalars()
    )
    development_request_ids = {
        demand.development_request_id
        for demand in demands
        if demand.development_request_id is not None
    }
    development_requests = (
        list(
            (
                await db.execute(
                    select(DevelopmentRequest)
                    .where(DevelopmentRequest.id.in_(development_request_ids))
                    .limit(ROW_LIMIT)
                )
            ).scalars()
        )
        if development_request_ids
        else []
    )
    recent_concepts = (
        list(
            (
                await db.execute(
                    select(ProductConcept)
                    .where(ProductConcept.updated_at >= since)
                    .order_by(ProductConcept.updated_at.desc())
                    .limit(ROW_LIMIT)
                )
            ).scalars()
        )
        if project_id is None
        else []
    )
    recent_concept_revision_ids = {
        concept.current_revision_id
        for concept in recent_concepts
        if concept.current_revision_id is not None
    }
    lineage_revisions = (
        list(
            (
                await db.execute(
                    select(SystemBlueprintRevision)
                    .where(
                        SystemBlueprintRevision.concept_revision_id.in_(
                            recent_concept_revision_ids
                        )
                    )
                    .order_by(SystemBlueprintRevision.updated_at.desc())
                    .limit(ROW_LIMIT)
                )
            ).scalars()
        )
        if recent_concept_revision_ids
        else []
    )
    lineage_version_ids = {
        revision.product_version_id
        for revision in lineage_revisions
        if revision.product_version_id is not None
    }

    execution_query = select(TaskExecution).join(
        ProjectTask, ProjectTask.id == TaskExecution.task_id
    ).where(TaskExecution.updated_at >= since)
    if project_id is not None:
        execution_query = execution_query.where(
            or_(
                ProjectTask.planning_item_id.in_(
                    select(PlanningItem.id).where(PlanningItem.project_id == project_id)
                ),
                ProjectTask.change_request_id.in_(
                    select(ChangeRequest.id).where(ChangeRequest.project_id == project_id)
                ),
            )
        )
    executions = list(
        (
            await db.execute(
                execution_query.order_by(TaskExecution.updated_at.desc()).limit(ROW_LIMIT)
            )
        ).scalars()
    )

    task_ids = {execution.task_id for execution in executions}
    task_ids.update(
        demand.origin_id
        for demand in demands
        if demand.origin_type == "task" and demand.origin_id is not None
    )
    task_recency_filter = ProjectTask.updated_at >= since
    task_query = select(ProjectTask).where(
        or_(ProjectTask.id.in_(task_ids), task_recency_filter)
        if task_ids
        else task_recency_filter
    )
    if project_id is not None:
        task_query = task_query.where(
            or_(
                ProjectTask.planning_item_id.in_(
                    select(PlanningItem.id).where(PlanningItem.project_id == project_id)
                ),
                ProjectTask.change_request_id.in_(
                    select(ChangeRequest.id).where(ChangeRequest.project_id == project_id)
                ),
            )
        )
    tasks = list(
        (
            await db.execute(
                task_query.order_by(ProjectTask.updated_at.desc()).limit(ROW_LIMIT)
            )
        ).scalars()
    )
    planning_item_ids = {
        task.planning_item_id for task in tasks if task.planning_item_id is not None
    }
    planning_items = (
        list(
            (
                await db.execute(
                    select(PlanningItem)
                    .where(PlanningItem.id.in_(planning_item_ids))
                    .limit(ROW_LIMIT)
                )
            ).scalars()
        )
        if planning_item_ids
        else []
    )
    planning_by_id = {item.id: item for item in planning_items}
    change_request_ids = {
        task.change_request_id for task in tasks if task.change_request_id is not None
    }
    change_requests = (
        list(
            (
                await db.execute(
                    select(ChangeRequest)
                    .where(ChangeRequest.id.in_(change_request_ids))
                    .limit(ROW_LIMIT)
                )
            ).scalars()
        )
        if change_request_ids
        else []
    )
    change_requests_by_id = {change_request.id: change_request for change_request in change_requests}
    membership_filters = [ProjectAgentMembership.status == "active"]
    if project_id is not None:
        membership_filters.append(ProjectAgentMembership.project_id == project_id)
    memberships = list(
        (
            await db.execute(
                select(ProjectAgentMembership)
                .where(*membership_filters)
                .order_by(ProjectAgentMembership.created_at.desc())
                .limit(ROW_LIMIT)
            )
        ).scalars()
    )
    project_ids = {
        item.project_id for item in planning_items if item.project_id is not None
    }
    project_ids.update(
        change_request.project_id for change_request in change_requests
    )
    project_ids.update(membership.project_id for membership in memberships)
    project_ids.update(
        demand.project_id for demand in demands if demand.project_id is not None
    )
    if lineage_version_ids:
        project_ids.update(
            (
                await db.execute(
                    select(Project.id).where(
                        Project.product_version_id.in_(lineage_version_ids)
                    )
                )
            ).scalars()
        )
    if project_id is not None:
        project_ids.add(project_id)
    projects = (
        list(
            (
                await db.execute(
                    select(Project).where(Project.id.in_(project_ids)).limit(ROW_LIMIT)
                )
            ).scalars()
        )
        if project_ids
        else []
    )
    projects_by_id = {project.id: project for project in projects}
    version_ids = {
        project.product_version_id
        for project in projects
        if project.product_version_id is not None
    }
    product_versions = (
        list(
            (
                await db.execute(
                    select(ProductVersion)
                    .where(ProductVersion.id.in_(version_ids))
                    .limit(ROW_LIMIT)
                )
            ).scalars()
        )
        if version_ids
        else []
    )
    versions_by_id = {version.id: version for version in product_versions}
    product_ids = {concept.product_id for concept in recent_concepts}
    product_ids.update(version.product_id for version in product_versions)
    products = (
        list(
            (
                await db.execute(
                    select(Product).where(Product.id.in_(product_ids)).limit(ROW_LIMIT)
                )
            ).scalars()
        )
        if product_ids
        else []
    )
    products_by_id = {product.id: product for product in products}

    concepts_by_id = {concept.id: concept for concept in recent_concepts}
    if product_ids:
        product_concepts = list(
            (
                await db.execute(
                    select(ProductConcept)
                    .where(ProductConcept.product_id.in_(product_ids))
                    .limit(ROW_LIMIT)
                )
            ).scalars()
        )
        concepts_by_id.update({concept.id: concept for concept in product_concepts})

    current_revision_ids = {
        concept.current_revision_id
        for concept in concepts_by_id.values()
        if concept.current_revision_id is not None
    }
    concept_revisions = (
        list(
            (
                await db.execute(
                    select(ProductConceptRevision)
                    .where(ProductConceptRevision.id.in_(current_revision_ids))
                    .limit(ROW_LIMIT)
                )
            ).scalars()
        )
        if current_revision_ids
        else []
    )
    concept_revisions_by_id = {
        revision.id: revision for revision in concept_revisions
    }

    lineage_by_id = {revision.id: revision for revision in lineage_revisions}
    if version_ids:
        project_lineage = list(
            (
                await db.execute(
                    select(SystemBlueprintRevision)
                    .where(SystemBlueprintRevision.product_version_id.in_(version_ids))
                    .order_by(SystemBlueprintRevision.updated_at.desc())
                    .limit(ROW_LIMIT)
                )
            ).scalars()
        )
        lineage_by_id.update({revision.id: revision for revision in project_lineage})
    missing_concept_revision_ids = {
        revision.concept_revision_id
        for revision in lineage_by_id.values()
        if revision.concept_revision_id is not None
        and revision.concept_revision_id not in concept_revisions_by_id
    }
    if missing_concept_revision_ids:
        missing_revisions = list(
            (
                await db.execute(
                    select(ProductConceptRevision)
                    .where(ProductConceptRevision.id.in_(missing_concept_revision_ids))
                    .limit(ROW_LIMIT)
                )
            ).scalars()
        )
        concept_revisions_by_id.update(
            {revision.id: revision for revision in missing_revisions}
        )
        missing_concept_ids = {
            revision.concept_id
            for revision in missing_revisions
            if revision.concept_id not in concepts_by_id
        }
        if missing_concept_ids:
            missing_concepts = list(
                (
                    await db.execute(
                        select(ProductConcept)
                        .where(ProductConcept.id.in_(missing_concept_ids))
                        .limit(ROW_LIMIT)
                    )
                ).scalars()
            )
            concepts_by_id.update(
                {concept.id: concept for concept in missing_concepts}
            )

    context_requests = (
        list(
            (
                await db.execute(
                    select(DevelopmentRequest)
                    .where(DevelopmentRequest.product_id.in_(product_ids))
                    .order_by(DevelopmentRequest.updated_at.desc())
                    .limit(ROW_LIMIT)
                )
            ).scalars()
        )
        if product_ids
        else []
    )
    requests_by_id = {
        request.id: request for request in [*development_requests, *context_requests]
    }
    latest_request_by_product: dict[uuid.UUID, DevelopmentRequest] = {}
    for request in sorted(
        requests_by_id.values(),
        key=lambda item: (item.updated_at, str(item.id)),
        reverse=True,
    ):
        latest_request_by_product.setdefault(request.product_id, request)

    lineage_by_version: dict[uuid.UUID, SystemBlueprintRevision] = {}
    for revision in sorted(
        lineage_by_id.values(),
        key=lambda item: (item.updated_at, item.revision, str(item.id)),
        reverse=True,
    ):
        if revision.product_version_id is not None:
            lineage_by_version.setdefault(revision.product_version_id, revision)

    contexts: list[ActivityContextOut] = []
    conception_context_by_id: dict[uuid.UUID, ActivityContextOut] = {}
    for concept in sorted(
        concepts_by_id.values(),
        key=lambda item: (item.updated_at, str(item.id)),
        reverse=True,
    ):
        if project_id is not None:
            continue
        product = products_by_id.get(concept.product_id)
        if product is None:
            continue
        request = latest_request_by_product.get(concept.product_id)
        revision = concept_revisions_by_id.get(concept.current_revision_id)
        context = ActivityContextOut(
            context_kind="conception",
            context_id=concept.id,
            product_id=product.id,
            product_name=product.name,
            development_request_id=request.id if request else None,
            concept_id=concept.id,
            concept_revision_id=revision.id if revision else None,
            working_directory_path=revision.working_directory_path if revision else None,
            title=request.title if request else product.name,
            status=concept.status,
            canonical_path=(
                f"/conception?request={request.id}" if request else "/conception"
            ),
            created_at=concept.created_at,
            updated_at=concept.updated_at,
        )
        contexts.append(context)
        conception_context_by_id[concept.id] = context

    project_context_by_id: dict[uuid.UUID, ActivityContextOut] = {}
    for project in sorted(projects, key=lambda item: (item.name.casefold(), str(item.id))):
        version = versions_by_id.get(project.product_version_id)
        product = products_by_id.get(version.product_id) if version else None
        if version is None or product is None:
            continue
        lineage = lineage_by_version.get(version.id)
        concept_revision = (
            concept_revisions_by_id.get(lineage.concept_revision_id)
            if lineage and lineage.concept_revision_id
            else None
        )
        concept = (
            concepts_by_id.get(concept_revision.concept_id)
            if concept_revision
            else next(
                (
                    candidate
                    for candidate in concepts_by_id.values()
                    if candidate.product_id == product.id
                ),
                None,
            )
        )
        request = latest_request_by_product.get(product.id)
        context = ActivityContextOut(
            context_kind="project",
            context_id=project.id,
            product_id=product.id,
            product_name=product.name,
            development_request_id=request.id if request else None,
            concept_id=concept.id if concept else None,
            concept_revision_id=(
                concept_revision.id
                if concept_revision
                else concept.current_revision_id
                if concept
                else None
            ),
            project_id=project.id,
            project_name=project.name,
            working_directory_path=project.working_directory_path,
            title=project.name,
            status=project.status,
            canonical_path=f"/projects/{project.id}",
            created_at=project.created_at,
            updated_at=project.updated_at,
        )
        contexts.append(context)
        project_context_by_id[project.id] = context

    tasks_by_id = {
        task.id: TaskActivityContext(
            task=task,
            project=projects_by_id.get(
                planning_by_id[task.planning_item_id].project_id
                if task.planning_item_id in planning_by_id
                else change_requests_by_id[task.change_request_id].project_id
                if task.change_request_id in change_requests_by_id
                else None
            ),
        )
        for task in tasks
    }

    assignment_ids = {
        execution.assignment_id for execution in executions if execution.assignment_id
    }
    assignments = (
        list(
            (
                await db.execute(
                    select(TaskAssignment)
                    .where(TaskAssignment.id.in_(assignment_ids))
                    .limit(ROW_LIMIT)
                )
            ).scalars()
        )
        if assignment_ids
        else []
    )
    assignments_by_id = {assignment.id: assignment for assignment in assignments}

    work_package_ids = {
        execution.work_package_id for execution in executions if execution.work_package_id
    }
    work_packages = (
        list(
            (
                await db.execute(
                    select(ExecutionWorkPackage)
                    .where(ExecutionWorkPackage.id.in_(work_package_ids))
                    .limit(ROW_LIMIT)
                )
            ).scalars()
        )
        if work_package_ids
        else []
    )
    work_packages_by_id = {item.id: item for item in work_packages}

    leases = (
        list(
            (
                await db.execute(
                    select(ExecutionLease)
                    .where(
                        ExecutionLease.updated_at >= since,
                        or_(
                            ExecutionLease.task_execution_id.in_(
                                [execution.id for execution in executions]
                            ),
                            ExecutionLease.work_package_id.in_(work_package_ids),
                        ),
                    )
                    .order_by(ExecutionLease.updated_at.desc())
                    .limit(ROW_LIMIT)
                )
            ).scalars()
        )
        if executions or work_package_ids
        else []
    )
    lease_by_execution = {
        lease.task_execution_id: lease
        for lease in leases
        if lease.task_execution_id is not None
    }
    lease_by_work_package = {lease.work_package_id: lease for lease in leases}

    checkpoint_filters = [ProgressCheckpoint.updated_at >= since]
    if project_id is not None:
        checkpoint_filters.append(ProgressCheckpoint.project_id == project_id)
    checkpoints = list(
        (
            await db.execute(
                select(ProgressCheckpoint)
                .where(*checkpoint_filters)
                .order_by(
                    ProgressCheckpoint.task_execution_id,
                    ProgressCheckpoint.sequence.desc(),
                )
                .limit(ROW_LIMIT)
            )
        ).scalars()
    )
    checkpoints_by_execution: dict[uuid.UUID, ProgressCheckpoint] = {}
    for checkpoint in checkpoints:
        if checkpoint.task_execution_id is not None:
            checkpoints_by_execution.setdefault(checkpoint.task_execution_id, checkpoint)

    parent_demand_ids = {demand.id for demand in demands}
    replies = (
        list(
            (
                await db.execute(
                    select(AgentDemand)
                    .where(AgentDemand.reply_to_id.in_(parent_demand_ids))
                    .order_by(AgentDemand.updated_at.desc())
                    .limit(ROW_LIMIT)
                )
            ).scalars()
        )
        if parent_demand_ids
        else []
    )

    source_demand_by_execution = {
        demand.task_execution_id: demand
        for demand in demands
        if demand.task_execution_id is not None
    }
    execution_contexts = [
        ExecutionActivityContext(
            execution=execution,
            assignment=assignments_by_id.get(execution.assignment_id),
            work_package=work_packages_by_id.get(execution.work_package_id),
            lease=lease_by_execution.get(execution.id)
            or lease_by_work_package.get(execution.work_package_id),
            source_demand=source_demand_by_execution.get(execution.id),
        )
        for execution in executions
    ]

    agent_ids = {
        identifier
        for demand in demands
        for identifier in (demand.from_agent_id, demand.target_agent_id)
        if identifier is not None
    }
    agent_ids.update(
        assignment.agent_id for assignment in assignments if assignment.agent_id is not None
    )
    agent_ids.update(
        membership.agent_id for membership in memberships if membership.agent_id is not None
    )
    agent_query = select(Agent).where(and_(Agent.is_active.is_(True), Agent.status == "active"))
    if project_id is not None:
        agent_query = agent_query.where(Agent.id.in_(agent_ids))
    agents = list(
        (
            await db.execute(agent_query.order_by(Agent.name).limit(ROW_LIMIT))
        ).scalars()
    )

    approval_filters = [ApprovalRequest.updated_at >= since]
    if project_id is not None:
        approval_filters.append(
            or_(
                and_(
                    ApprovalRequest.target_type == "project_task",
                    ApprovalRequest.target_id.in_(task_ids),
                ),
                and_(
                    ApprovalRequest.target_type == "project",
                    ApprovalRequest.target_id == project_id,
                ),
            )
        )
    approvals = list(
        (
            await db.execute(
                select(ApprovalRequest)
                .where(*approval_filters)
                .order_by(ApprovalRequest.updated_at.desc())
                .limit(ROW_LIMIT)
            )
        ).scalars()
    )
    notifications = list(
        (
            await db.execute(
                select(Notification)
                .where(Notification.occurred_at >= since)
                .order_by(Notification.occurred_at.desc())
                .limit(ROW_LIMIT)
            )
        ).scalars()
    ) if project_id is None else []

    forgerouter_state, forgerouter_freshness = await _load_forgerouter_state(
        window_minutes=window_minutes
    )
    activity_agents = build_activity_agents(
        agents=agents,
        tasks_by_id=tasks_by_id,
        executions=execution_contexts,
        checkpoints_by_execution=checkpoints_by_execution,
        forgerouter_state=forgerouter_state,
    )
    visible_agent_ids = {agent.id for agent in activity_agents}
    visible_project_ids = {project.id for project in projects}
    relation_by_pair: dict[
        tuple[uuid.UUID, uuid.UUID], ActivityTopologyRelationOut
    ] = {}
    for membership in memberships:
        if (
            membership.agent_id not in visible_agent_ids
            or membership.project_id not in visible_project_ids
        ):
            continue
        relation_by_pair[(membership.agent_id, membership.project_id)] = (
            ActivityTopologyRelationOut(
                key=f"membership:{membership.agent_id}:{membership.project_id}",
                kind="membership",
                from_type="agent",
                from_id=str(membership.agent_id),
                to_type="project",
                to_id=str(membership.project_id),
                label="Allocated",
            )
        )
    for agent in activity_agents:
        if not agent.current_work or not agent.current_work.project_id:
            continue
        current_project_id = agent.current_work.project_id
        if current_project_id not in visible_project_ids:
            continue
        relation_by_pair[(agent.id, current_project_id)] = ActivityTopologyRelationOut(
            key=f"current-work:{agent.id}:{current_project_id}",
            kind="current_work",
            from_type="agent",
            from_id=str(agent.id),
            to_type="project",
            to_id=str(current_project_id),
            label="Working now",
        )

    forgehub_key = "platform:forgehub"
    forgerouter_key = "gateway:forgerouter"
    forgevault_key = "vault:forgevault"
    darckware_key = "site:darckware"

    topology_relations = list(relation_by_pair.values())
    topology_relations.extend(
        ActivityTopologyRelationOut(
            key=f"portal_sync:{project.id}:{darckware_key}",
            kind="portal_sync",
            from_type="project",
            from_id=str(project.id),
            to_type="resource",
            to_id=darckware_key,
            label="Delivers to Darckware portal",
        )
        for project in projects
    )
    topology_relations.extend(
        ActivityTopologyRelationOut(
            key=f"orchestration:{agent.id}:{forgehub_key}",
            kind="orchestration",
            from_type="agent",
            from_id=str(agent.id),
            to_type="resource",
            to_id=forgehub_key,
            label="Orchestrated by ForgeHub",
        )
        for agent in activity_agents
    )
    topology_relations.extend(
        ActivityTopologyRelationOut(
            key=f"ai_routing:{agent.id}:{forgerouter_key}",
            kind="ai_routing",
            from_type="agent",
            from_id=str(agent.id),
            to_type="resource",
            to_id=forgerouter_key,
            label="Routes AI prompts",
        )
        for agent in activity_agents
    )
    topology_relations.extend(
        ActivityTopologyRelationOut(
            key=f"vault_sync:{agent.id}:{forgevault_key}",
            kind="vault_sync",
            from_type="agent",
            from_id=str(agent.id),
            to_type="resource",
            to_id=forgevault_key,
            label="Syncs knowledge & credentials",
        )
        for agent in activity_agents
    )
    topology_relations.extend(
        ActivityTopologyRelationOut(
            key=f"portal_sync:{agent.id}:{darckware_key}",
            kind="portal_sync",
            from_type="agent",
            from_id=str(agent.id),
            to_type="resource",
            to_id=darckware_key,
            label="Darckware web & client sync",
        )
        for agent in activity_agents
    )
    topology_relations.extend(
        ActivityTopologyRelationOut(
            key=f"transition:{context.concept_id}:{context.project_id}",
            kind="transition",
            from_type="conception",
            from_id=str(context.concept_id),
            to_type="project",
            to_id=str(context.project_id),
            label="Authorized delivery",
        )
        for context in project_context_by_id.values()
        if context.concept_id is not None
    )

    context_by_request_id = {
        context.development_request_id: context
        for context in contexts
        if context.development_request_id is not None
        and context.context_kind == "conception"
    }
    demands_by_id = {demand.id: demand for demand in demands}
    approvals_by_id = {approval.id: approval for approval in approvals}

    def attach_context(item, context: ActivityContextOut | None) -> None:
        if context is None:
            return
        item.context_kind = context.context_kind
        item.context_id = context.context_id
        item.development_request_id = context.development_request_id
        item.concept_id = context.concept_id
        item.concept_revision_id = context.concept_revision_id

    def resolve_item_context(item) -> ActivityContextOut | None:
        if item.project_id is not None:
            project_context = project_context_by_id.get(item.project_id)
            if project_context is not None:
                return project_context
        if item.source_type == "agent_demand":
            demand = demands_by_id.get(item.source_id)
            if demand and demand.development_request_id is not None:
                return context_by_request_id.get(demand.development_request_id)
        if item.source_type == "approval_request":
            approval = approvals_by_id.get(item.source_id)
            if approval and approval.target_type == "product_concept":
                return conception_context_by_id.get(approval.target_id)
        return None

    flow_items = build_flow_items(
        demands=demands,
        tasks_by_id=tasks_by_id,
        executions=execution_contexts,
        approvals=approvals,
    )
    timeline = build_timeline(
        demands=demands,
        executions=execution_contexts,
        checkpoints_by_execution=checkpoints_by_execution,
        approvals=approvals,
        notifications=notifications,
    )
    incidents = build_incidents(
        demands=demands,
        executions=execution_contexts,
        checkpoints_by_execution=checkpoints_by_execution,
        approvals=approvals,
        forgerouter_state=forgerouter_state,
    )
    for item in [*flow_items, *timeline, *incidents]:
        attach_context(item, resolve_item_context(item))
    for agent in activity_agents:
        if agent.current_work and agent.current_work.project_id:
            attach_context(
                agent.current_work,
                project_context_by_id.get(agent.current_work.project_id),
            )

    for context in conception_context_by_id.values():
        flow_items.append(
            ActivityFlowItemOut(
                key=f"product_concept:{context.concept_id}",
                stage=CONCEPT_FLOW_STAGE[context.status],
                source_type="product_concept",
                source_id=context.concept_id,
                source_status=context.status,
                title=context.title,
                occurred_at=context.created_at,
                updated_at=context.updated_at,
                canonical_path=context.canonical_path,
                context_kind=context.context_kind,
                context_id=context.context_id,
                development_request_id=context.development_request_id,
                concept_id=context.concept_id,
                concept_revision_id=context.concept_revision_id,
            )
        )
        timeline.append(
            ActivityTimelineEventOut(
                key=f"product-concept:{context.concept_id}",
                kind=f"product_concept_{context.status}",
                occurred_at=context.updated_at,
                source_type="product_concept",
                source_id=context.concept_id,
                source_status=context.status,
                lane="planning",
                title=context.title,
                canonical_path=context.canonical_path,
                context_kind=context.context_kind,
                context_id=context.context_id,
                development_request_id=context.development_request_id,
                concept_id=context.concept_id,
                concept_revision_id=context.concept_revision_id,
            )
        )

    return AgentActivityOut(
        generated_at=generated_at,
        project_id=project_id,
        agents=activity_agents,
        contexts=sorted(
            contexts,
            key=lambda item: (item.updated_at, item.context_kind, str(item.context_id)),
            reverse=True,
        ),
        projects=[
            ActivityProjectOut(
                id=project.id,
                name=project.name,
                status=project.status,
                canonical_path=f"/projects/{project.id}",
            )
            for project in sorted(projects, key=lambda item: (item.name.casefold(), str(item.id)))
        ],
        resources=[
            ActivityResourceOut(
                key=darckware_key,
                kind="portal",
                label="darckware",
                detail="portal_web",
                status="available",
            ),
            ActivityResourceOut(
                key=forgehub_key,
                kind="platform",
                label="forgehub",
                detail="orchestrator",
                status="available",
            ),
            ActivityResourceOut(
                key=forgerouter_key,
                kind="gateway",
                label="forgerouter",
                detail="ai_proxy",
                status="available" if forgerouter_freshness.status != "unavailable" else "degraded",
            ),
            ActivityResourceOut(
                key=forgevault_key,
                kind="vault",
                label="forgevault",
                detail="knowledge_vault",
                status="available",
            ),
        ],
        topology_relations=sorted(topology_relations, key=lambda item: item.key),
        flow_items=sorted(
            flow_items,
            key=lambda item: (item.updated_at, item.key),
            reverse=True,
        ),
        message_edges=build_message_edges(
            demands=demands,
            agents=agents,
            replies=replies,
            development_requests=development_requests,
        ),
        incidents=incidents,
        timeline=sorted(
            timeline,
            key=lambda item: (item.occurred_at, item.key),
            reverse=True,
        ),
        source_freshness=[
            ActivitySourceFreshnessOut(
                name="postgres",
                status="fresh",
                checked_at=generated_at,
            ),
            forgerouter_freshness,
        ],
    )

"""Authenticated Agent Activity read model and Athos monitoring command."""

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.demand import create_demand_and_notify
from app.api.schemas.agent_activity import (
    AgentActivityOut,
    RequestAthosMonitoringIn,
    RequestAthosMonitoringOut,
)
from app.api.schemas.demand import DemandSubmitIn
from app.core.agent_activity import build_agent_activity
from app.core.deps import ActorPrincipal, authorize_action, get_actor_principal
from app.db.base import get_db
from app.db.models.agent import Agent
from app.db.models.backlog import PlanningItem
from app.db.models.demand import AgentDemand
from app.db.models.notification import Notification
from app.db.models.project import ChangeRequest
from app.db.models.task import ProjectTask, TaskExecution

router = APIRouter(prefix="/api/v1/agent-activity", tags=["agent-activity"])


async def _find_athos(db: AsyncSession) -> Agent | None:
    return (
        await db.execute(select(Agent).where(Agent.profile_slug == "athos"))
    ).scalar_one_or_none()


async def _task_project_id(db: AsyncSession, task: ProjectTask) -> uuid.UUID:
    if task.planning_item_id is not None:
        item = await db.get(PlanningItem, task.planning_item_id)
        if item is not None and item.project_id is not None:
            return item.project_id
    if task.change_request_id is not None:
        change_request = await db.get(ChangeRequest, task.change_request_id)
        if change_request is not None:
            return change_request.project_id
    raise HTTPException(status_code=409, detail="Task cannot be resolved to a project")


def _monitoring_body(
    *,
    incident_key: str,
    execution_id: uuid.UUID,
    task_id: uuid.UUID,
    requested_by: str,
) -> str:
    return json.dumps(
        {
            "contract_version": "forge-agent-incident-monitor/v1",
            "incident_key": incident_key,
            "execution_id": str(execution_id),
            "task_id": str(task_id),
            "requested_by": requested_by,
        },
        sort_keys=True,
    )


def _monitoring_notification_title(subject: str) -> str:
    return f"Athos monitoring requested: {subject}"


def _is_matching_monitoring_demand(
    demand: AgentDemand,
    *,
    channel_ref: str,
    athos_id: uuid.UUID,
    project_id: uuid.UUID,
    subject: str,
    body: str,
    requested_by: str,
) -> bool:
    """Keys only identify a pair after its complete structured contract matches."""
    return (
        demand.from_agent == requested_by
        and demand.target_agent_id == athos_id
        and demand.project_id == project_id
        and demand.subject == subject
        and demand.body == body
        and demand.channel == "agent"
        and demand.channel_ref == channel_ref
        and demand.requires_response is True
        and demand.scheduled_at is None
        and demand.dispatch_status is None
        and demand.task_execution_id is None
        and demand.reply_to_id is None
    )


def _is_matching_monitoring_notification(
    notification: Notification,
    *,
    event_key: str,
    subject: str,
    body: str,
) -> bool:
    return (
        notification.source == "system"
        and notification.severity == "warning"
        and notification.title == _monitoring_notification_title(subject)
        and notification.message == body
        and notification.event_key == event_key
    )


async def _lock_monitoring_idempotency_key(
    db: AsyncSession,
    channel_ref: str,
) -> None:
    """Serialize all command writers for one deterministic idempotency key.

    `channel_ref` has no unique database constraint, so locking a missing row
    cannot protect the first insert. PostgreSQL transaction advisory locks do
    not need a row or migration and are released by the command's single
    commit/rollback.
    """
    await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(channel_ref))))


async def _commit_monitoring_pair(db: AsyncSession) -> None:
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Monitoring idempotency key conflicts with an existing record",
        ) from exc


async def _create_monitoring_notification(
    db: AsyncSession,
    *,
    subject: str,
    body: str,
    event_key: str,
) -> Notification:
    notification = Notification(
        source="system",
        severity="warning",
        title=_monitoring_notification_title(subject),
        message=body,
        event_key=event_key,
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(notification)
    await db.flush()
    return notification


@router.get("", response_model=AgentActivityOut)
async def get_agent_activity(
    project_id: uuid.UUID | None = None,
    window_minutes: int = Query(default=60, ge=1, le=24 * 60),
    db: AsyncSession = Depends(get_db),
    principal: ActorPrincipal = Depends(get_actor_principal),
) -> AgentActivityOut:
    await authorize_action(db, principal, "demands.view", project_id=project_id)
    return await build_agent_activity(
        db,
        project_id=project_id,
        window_minutes=window_minutes,
    )


@router.post(
    "/incidents/{incident_key}:request-athos-monitoring",
    response_model=RequestAthosMonitoringOut,
    status_code=status.HTTP_201_CREATED,
)
async def request_athos_monitoring(
    incident_key: str,
    payload: RequestAthosMonitoringIn,
    db: AsyncSession = Depends(get_db),
    principal: ActorPrincipal = Depends(get_actor_principal),
) -> RequestAthosMonitoringOut:
    view = await build_agent_activity(db, project_id=None, window_minutes=24 * 60)
    incident = next((item for item in view.incidents if item.key == incident_key), None)
    if incident is None or incident.execution_id != payload.execution_id:
        raise HTTPException(status_code=404, detail="Incident not found")

    execution = await db.get(TaskExecution, payload.execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Execution not found")
    task = await db.get(ProjectTask, execution.task_id)
    if task is None:
        raise HTTPException(status_code=409, detail="Execution task is missing")
    project_id = await _task_project_id(db, task)
    await authorize_action(db, principal, "planning.execution.manage", project_id=project_id)

    channel_ref = f"agent-activity:{payload.idempotency_key}"
    event_key = f"agent-activity:athos-monitor:{payload.idempotency_key}"
    subject = f"Monitor incident {incident_key}"
    body = _monitoring_body(
        incident_key=incident_key,
        execution_id=execution.id,
        task_id=task.id,
        requested_by=principal.display_name,
    )
    athos = await _find_athos(db)
    if athos is None:
        raise HTTPException(status_code=404, detail="Athos agent not found")

    await _lock_monitoring_idempotency_key(db, channel_ref)
    existing_demands = list(
        (
            await db.execute(
                select(AgentDemand).where(AgentDemand.channel_ref == channel_ref)
            )
        ).scalars()
    )
    existing_notification = (
        await db.execute(select(Notification).where(Notification.event_key == event_key))
    ).scalar_one_or_none()

    if len(existing_demands) > 1:
        raise HTTPException(
            status_code=409,
            detail="Monitoring idempotency key maps to multiple demands",
        )
    existing_demand = existing_demands[0] if existing_demands else None
    if existing_demand is None and existing_notification is not None:
        raise HTTPException(
            status_code=409,
            detail="Monitoring notification exists without its demand",
        )
    if existing_demand is not None:
        if not _is_matching_monitoring_demand(
            existing_demand,
            channel_ref=channel_ref,
            athos_id=athos.id,
            project_id=project_id,
            subject=subject,
            body=body,
            requested_by=principal.display_name,
        ):
            raise HTTPException(
                status_code=409,
                detail="Monitoring demand does not match this command",
            )
        if existing_notification is not None and not _is_matching_monitoring_notification(
            existing_notification,
            event_key=event_key,
            subject=subject,
            body=body,
        ):
            raise HTTPException(
                status_code=409,
                detail="Monitoring notification does not match this command",
            )
        notification = existing_notification
        if notification is None:
            notification = await _create_monitoring_notification(
                db,
                subject=subject,
                body=body,
                event_key=event_key,
            )
            await _commit_monitoring_pair(db)
            await db.refresh(notification)
        return RequestAthosMonitoringOut(
            message_id=existing_demand.id,
            message_number=existing_demand.number,
            notification_id=notification.id,
            created=False,
        )

    demand = await create_demand_and_notify(
        db,
        DemandSubmitIn(
            from_agent=principal.display_name,
            target_agent_id=athos.id,
            project_id=project_id,
            subject=subject,
            body=body,
            channel="agent",
            channel_ref=channel_ref,
            requires_response=True,
        ),
        commit=False,
    )
    helper_notification = (
        await db.execute(
            select(Notification).where(Notification.event_key == f"demand:{demand.id}")
        )
    ).scalar_one_or_none()
    if helper_notification is None:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Monitoring demand helper did not create its notification",
        )
    helper_notification.source = "system"
    helper_notification.severity = "warning"
    helper_notification.title = _monitoring_notification_title(subject)
    helper_notification.message = body
    helper_notification.event_key = event_key
    await _commit_monitoring_pair(db)
    await db.refresh(demand)
    await db.refresh(helper_notification)
    return RequestAthosMonitoringOut(
        message_id=demand.id,
        message_number=demand.number,
        notification_id=helper_notification.id,
        created=True,
    )

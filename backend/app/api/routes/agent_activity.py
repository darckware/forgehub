"""Authenticated Agent Activity read model and Athos monitoring command."""

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
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
from app.db.models.demand import AgentDemand
from app.db.models.notification import Notification
from app.db.models.project import ChangeRequest
from app.db.models.backlog import PlanningItem
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


async def _ensure_monitoring_notification(
    db: AsyncSession,
    *,
    demand: AgentDemand,
    event_key: str,
) -> Notification:
    """Repair the notification half of an interrupted demand-helper write."""
    notification = (
        await db.execute(select(Notification).where(Notification.event_key == event_key))
    ).scalar_one_or_none()
    if notification is not None:
        return notification

    helper_notification = (
        await db.execute(
            select(Notification).where(Notification.event_key == f"demand:{demand.id}")
        )
    ).scalar_one_or_none()
    if helper_notification is not None:
        helper_notification.event_key = event_key
        helper_notification.title = f"Athos monitoring requested: {demand.subject}"
        helper_notification.message = demand.body
        await db.commit()
        await db.refresh(helper_notification)
        return helper_notification

    notification = Notification(
        source="system",
        severity="warning",
        title=f"Athos monitoring requested: {demand.subject}",
        message=demand.body,
        event_key=event_key,
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(notification)
    await db.commit()
    await db.refresh(notification)
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
    await authorize_action(db, principal, "demands.view", project_id=project_id)

    channel_ref = f"agent-activity:{payload.idempotency_key}"
    event_key = f"agent-activity:athos-monitor:{payload.idempotency_key}"
    existing_demand = (
        await db.execute(
            select(AgentDemand).where(AgentDemand.channel_ref == channel_ref)
        )
    ).scalar_one_or_none()
    existing_notification = (
        await db.execute(select(Notification).where(Notification.event_key == event_key))
    ).scalar_one_or_none()

    if existing_demand is None and existing_notification is not None:
        raise HTTPException(
            status_code=409,
            detail="Monitoring notification exists without its demand",
        )
    if existing_demand is not None:
        notification = existing_notification or await _ensure_monitoring_notification(
            db,
            demand=existing_demand,
            event_key=event_key,
        )
        return RequestAthosMonitoringOut(
            message_id=existing_demand.id,
            message_number=existing_demand.number,
            notification_id=notification.id,
            created=False,
        )

    athos = await _find_athos(db)
    if athos is None:
        raise HTTPException(status_code=404, detail="Athos agent not found")

    demand = await create_demand_and_notify(
        db,
        DemandSubmitIn(
            from_agent=principal.display_name,
            target_agent_id=athos.id,
            project_id=project_id,
            subject=f"Monitor incident {incident_key}",
            body=json.dumps(
                {
                    "contract_version": "forge-agent-incident-monitor/v1",
                    "incident_key": incident_key,
                    "execution_id": str(execution.id),
                    "task_id": str(task.id),
                    "requested_by": principal.display_name,
                },
                sort_keys=True,
            ),
            channel="agent",
            channel_ref=channel_ref,
            requires_response=True,
        ),
    )
    notification = await _ensure_monitoring_notification(
        db,
        demand=demand,
        event_key=event_key,
    )
    return RequestAthosMonitoringOut(
        message_id=demand.id,
        message_number=demand.number,
        notification_id=notification.id,
        created=True,
    )

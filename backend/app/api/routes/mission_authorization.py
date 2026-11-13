"""The orchestrator asks Marcelo's authorization; one inbox for his mission
decisions (2026-11-13, Marcelo: "o agente orquestrador é o responsável pela
administração do sistema e da continuidade da execução. Quando desejar minha
autorização envia para a aprovação no Pessoal / Tarefas dos agentes").

- ``POST /api/v1/missions/{id}/approval-requests``  admin or the orchestrator
  (``mission.orchestrate``). Files a Messages Task from the orchestrator to
  itself, ``requires_approval`` and ``approval_status='pending'``, with no
  ``scheduled_at``: nothing runs it until Marcelo approves it in Pessoal →
  Tarefas dos agentes (``POST /demands/{id}/decision`` approve, which hashes
  the content and queues it). The runner boundary refuses it before that
  (``demand_workflow.assert_execution_allowed``), whatever path reaches it.
  A rejection leaves it unexecuted and back in the orchestrator's inbox.
- ``GET /api/v1/missions/pending-decisions``         admin only. Pending
  mission plan approvals (governed ``ApprovalRequest`` ``project_plan``) and
  phases ``awaiting_approval``, so Pessoal → Tarefas dos agentes shows every
  decision that is Marcelo's. Deciding stays on the owning routes
  (``/governed/approval-requests/{id}:decide``, ``/phases/{id}:approve|:return``).

This router is included before ``mission.router`` so ``/pending-decisions``
is not read as ``/{project_id}``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select

from app.api.routes.mission import _audit_payload, _authorize_conduct, _load
from app.api.routes.mission_phase import _assert_not_terminal, _begin, _notify, _respond
from app.api.schemas.mission_authorization import (
    AuthorizationRequestIn,
    AuthorizationRequestOut,
    PendingMissionDecision,
)
from app.core.command_receipts import limit_command_body, record_command
from app.core.deps import ActorPrincipal, get_actor_principal
from app.core.mission import mission_error
from app.db.base import get_db
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand
from app.db.models.governance import ApprovalRequest, AuditEvent
from app.db.models.mission import MissionPlanSubmission, MissionProjectLink, ProjectMission
from app.db.models.project import Project, ProjectPlan

router = APIRouter(prefix="/api/v1/missions", tags=["missions"])

AUTHORIZATION_SUBJECT_PREFIX = "[Autorização] "
TERMINAL_STATES = ("completed", "cancelled")


def authorization_body(mission_name: str, action: str, justification: str, instructions: str) -> str:
    return "\n\n".join([
        f"# Pedido de autorização — missão {mission_name}",
        f"## Ação\n{action}",
        f"## Justificativa\n{justification}",
        "## Instruções (executadas pelo orquestrador somente após a aprovação de Marcelo)\n" + instructions,
    ])


@router.get("/pending-decisions", response_model=list[PendingMissionDecision])
async def pending_decisions(
    principal: ActorPrincipal = Depends(get_actor_principal),
    db=Depends(get_db),
) -> list[PendingMissionDecision]:
    """Every mission decision waiting for Marcelo, oldest first. An expired
    plan request and anything of a completed/cancelled mission is left out
    (nothing left to decide there)."""
    if principal.principal_type != "user" or not principal.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrators only")
    out: list[PendingMissionDecision] = []
    now = datetime.now(timezone.utc)
    plans = (await db.execute(
        select(ApprovalRequest, MissionPlanSubmission, ProjectPlan, Project)
        .join(MissionPlanSubmission, MissionPlanSubmission.approval_request_id == ApprovalRequest.id)
        .join(ProjectPlan, ProjectPlan.id == MissionPlanSubmission.project_plan_id)
        .join(Project, Project.id == MissionPlanSubmission.mission_project_id)
        .join(ProjectMission, ProjectMission.project_id == Project.id)
        .where(ApprovalRequest.target_type == "project_plan", ApprovalRequest.status == "pending",
               or_(ApprovalRequest.expires_at.is_(None), ApprovalRequest.expires_at > now),
               ProjectMission.state.notin_(TERMINAL_STATES))
    )).all()
    for request, submission, plan, mission in plans:
        count = len(submission.task_ids or [])
        out.append(PendingMissionDecision(
            kind="plan_approval", mission_project_id=mission.id, mission_name=mission.name,
            title=f"Plano: {plan.name}", summary=f"{plan.name} · {count} tarefa(s)",
            requested_at=request.created_at, requested_by=request.requested_by_name,
            approval_request_id=request.id, project_plan_id=plan.id, task_count=count,
            link=f"/missions/{mission.id}",
        ))
    phases = (await db.execute(
        select(MissionProjectLink, Project)
        .join(Project, Project.id == MissionProjectLink.mission_project_id)
        .join(ProjectMission, ProjectMission.project_id == Project.id)
        .where(MissionProjectLink.is_phase.is_(True), MissionProjectLink.phase_status == "awaiting_approval",
               ProjectMission.state.notin_(TERMINAL_STATES))
    )).all()
    for phase, mission in phases:
        out.append(PendingMissionDecision(
            kind="phase_approval", mission_project_id=mission.id, mission_name=mission.name,
            title=f"Fase {phase.position} · {phase.name}", summary=phase.homologation_summary,
            requested_at=phase.homologated_at or phase.updated_at,
            phase_id=phase.id, phase_position=phase.position, phase_name=phase.name,
            homologation_evidence=[e for e in (phase.homologation_evidence or "").split("\n") if e.strip()],
            link=f"/missions/{mission.id}",
        ))
    out.sort(key=lambda d: (d.requested_at is None, d.requested_at))
    return out


@router.post("/{project_id}/approval-requests", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(limit_command_body)])
async def request_authorization(
    project_id: uuid.UUID,
    payload: AuthorizationRequestIn,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db=Depends(get_db),
):
    """The orchestrator asks Marcelo to authorize something outside its
    mandate. Creates the pending task (from the orchestrator to itself), a
    warning notification and the audit; dispatches nothing."""
    command = "mission.authorization.request"
    body: dict[str, Any] = {"project_id": str(project_id), **payload.model_dump(mode="json")}
    mission_project, mission = await _load(db, project_id, lock=True)
    source, delegation, role = await _authorize_conduct(db, principal, mission)
    body_hash, replay = await _begin(db, principal, payload.idempotency_key, command, body)
    if replay is not None:
        return replay
    _assert_not_terminal(mission)
    action = payload.action.strip()
    justification = payload.justification.strip()
    instructions = payload.instructions.strip()
    if not (action and justification and instructions):
        raise mission_error(422, "AUTHORIZATION_FIELDS_REQUIRED",
                            "action, justification and instructions cannot be blank")
    working_path = (mission_project.working_directory_path or "").strip()
    if not working_path.startswith("/"):
        raise mission_error(422, "WORKING_DIRECTORY_REQUIRED",
                            "The mission needs an absolute working directory before asking for an authorization")
    orchestrator = await db.get(Agent, mission.orchestrator_agent_id)
    if orchestrator is None:
        raise mission_error(409, "ORCHESTRATOR_REQUIRED", "The mission has no orchestrator")
    demand = AgentDemand(
        from_agent=orchestrator.profile_slug or orchestrator.name, from_agent_id=orchestrator.id,
        target_agent_id=orchestrator.id,
        subject=f"{AUTHORIZATION_SUBJECT_PREFIX}{action}"[:255],
        body=authorization_body(mission_project.name, action, justification, instructions),
        status="new", origin_type="task", requires_approval=True, approval_status="pending",
        fixed_agent=True, project_id=mission.project_id, working_path=working_path,
        context_area=f"mission:{mission.project_id}", channel="factory", channel_ref=str(mission.project_id),
        requires_response=False, scheduled_at=None,
    )
    db.add(demand)
    await db.flush()
    await db.refresh(demand)  # The number comes from the database.
    _notify(db, f"Autorização pedida por {orchestrator.name}: {action}"[:255],
            f"Missão {mission_project.name}.\nJustificativa: {justification}\n"
            f"Aprove ou recuse em Pessoal → Tarefas dos agentes (#{demand.number}).",
            f"mission-authorization:{demand.id}")
    db.add(AuditEvent(
        entity_type="mission", entity_id=mission.project_id, event_type="mission_authorization_requested",
        actor=principal.display_name,
        payload=_audit_payload(principal, source, delegation, idempotency_key=payload.idempotency_key, role=role,
                               demand_id=str(demand.id), demand_number=demand.number, action=action),
    ))
    out = AuthorizationRequestOut(
        mission_project_id=mission.project_id, demand_id=demand.id, demand_number=demand.number,
        approval_status="pending", link=f"/personal?tab=agent-work&workSearch=%23{demand.number}",
    ).model_dump(mode="json")
    if payload.idempotency_key:
        record_command(db, principal, payload.idempotency_key, command, body_hash, 201, out,
                       target_type="agent_demand", target_id=demand.id)
    await db.commit()
    return _respond(201, out)

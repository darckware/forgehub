"""Mission domain routes (Plano Integrado M0.0).

Contract: docs/architecture/MCP_MISSION_TOOLS_SPEC.md §2, §3, §3.1, §6.1.
A mission is a Project (``project_type='mission'``) plus its
``project_missions`` row. Endpoints:

- ``POST /api/v1/missions``                              create (the only way; POST /projects never does)
- ``GET /api/v1/missions/{project_id}``                  read
- ``PATCH /api/v1/missions/{project_id}``                planning fields (risk/layers locked after P1)
- ``POST /api/v1/missions/{project_id}:transition``      the only writer of state (+ Project.status projection)
- ``POST /api/v1/missions/{project_id}/planning:advance`` the planning pipeline, strictly in order

Authorization (§0.2): a human must be admin (Marcelo); an agent calls with
its own ``agt_`` and needs an ``AuthorityDelegation`` (``mission.manage`` to
create/edit, ``mission.orchestrate`` to conduct) and, to conduct, must be the
mission's orchestrator. Errors use the object form ``{code, message, ...}``
(§0.3). ``autonomy_level`` other than N0 is refused in Onda 1.
"""
import hashlib
import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.mission import (
    REVIEW_LAYER_SET,
    MissionCreate,
    MissionOut,
    MissionTransitionIn,
    MissionUpdate,
    PlanningAdvanceIn,
    PlanningAdvanceOut,
)
from app.core.deps import ActorPrincipal, authorize_action, get_actor_principal
from app.core.mission import (
    ALLOWED_TRANSITIONS,
    REASON_REQUIRED_SOURCES,
    REASON_REQUIRED_TARGETS,
    apply_mission_state,
    executor_project_ids,
    failed_criterion_verifiers,
    mission_error,
    mission_tasks,
    next_planning_stages,
    planning_exit_conditions,
    transition_preconditions,
    utcnow,
)
from app.db.base import get_db
from app.db.models.agent import Agent
from app.db.models.artifact import Artifact
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent
from app.db.models.mission import (
    MISSION_STATUS_PROJECTION,
    MissionDecision,
    MissionProjectLink,
    ProjectMission,
)
from app.db.models.orchestration import ProjectAgentMembership
from app.db.models.product import ProductVersion
from app.db.models.project import Project

router = APIRouter(prefix="/api/v1/missions", tags=["missions"])


def _assert_n0(level: str | None) -> None:
    if level is not None and level != "N0":
        raise mission_error(422, "AUTONOMY_LEVEL_NOT_ALLOWED", "Onda 1 operates missions at autonomy N0 only",
                            autonomy_level=level)


def _audit_payload(principal: ActorPrincipal, source: str, delegation, **extra: Any) -> dict[str, Any]:
    return {
        "principal_type": principal.principal_type,
        "principal_id": str(principal.principal_id),
        "authority_source": source,
        "delegation_id": str(delegation.id) if delegation is not None else None,
        **extra,
    }


async def _load(db: AsyncSession, project_id: uuid.UUID, *, lock: bool = False) -> tuple[Project, ProjectMission]:
    project = await db.get(Project, project_id)
    stmt = select(ProjectMission).where(ProjectMission.project_id == project_id)
    if lock:
        stmt = stmt.with_for_update()
    mission = (await db.execute(stmt)).scalar_one_or_none()
    if project is None or mission is None or project.project_type != "mission":
        raise mission_error(404, "MISSION_NOT_FOUND", "Mission not found")
    return project, mission


async def _out(db: AsyncSession, project: Project, mission: ProjectMission) -> MissionOut:
    return MissionOut(
        project_id=project.id,
        name=project.name,
        project_type=project.project_type,
        project_status=project.status,
        state=mission.state,
        paused_from_state=mission.paused_from_state,
        planning_stage=mission.planning_stage,
        risk_level=mission.risk_level,
        required_review_layers=list(mission.required_review_layers or []),
        priority=mission.priority,
        orchestrator_agent_id=mission.orchestrator_agent_id,
        autonomy_level=mission.autonomy_level,
        brief_artifact_id=mission.brief_artifact_id,
        current_baseline_id=mission.current_baseline_id,
        deadline_at=mission.deadline_at,
        budget_limit=mission.budget_limit,
        paused_seconds=mission.paused_seconds,
        state_changed_at=mission.state_changed_at,
        state_reason=mission.state_reason,
        row_version=mission.row_version,
        executor_project_ids=await executor_project_ids(db, project.id),
    )


async def _authorize_conduct(
    db: AsyncSession, principal: ActorPrincipal, mission: ProjectMission, allowed: frozenset[str] | None = None,
) -> tuple[str, Any, str]:
    """Return (authority_source, delegation, role) for marcelo/orchestrator/verifier."""
    allowed = allowed or frozenset({"marcelo", "orchestrator"})
    if principal.principal_type == "user":
        if not principal.is_admin:
            raise mission_error(403, "MISSION_ADMIN_ONLY", "Only an administrator acts on a mission in M0")
        if "marcelo" not in allowed:
            raise mission_error(403, "MISSION_ACTOR_NOT_ALLOWED", "This action is not taken by a person")
        return "admin", None, "marcelo"
    if "orchestrator" in allowed and principal.principal_id == mission.orchestrator_agent_id:
        source, delegation = await authorize_action(
            db, principal, "mission.orchestrate", project_id=mission.project_id
        )
        return source, delegation, "orchestrator"
    if "verifier" in allowed and principal.principal_id in await failed_criterion_verifiers(db, mission.project_id):
        return "criterion_verifier", None, "verifier"
    raise mission_error(403, "MISSION_ACTOR_NOT_ALLOWED", "This agent may not take this action on the mission",
                        allowed=sorted(allowed))


def _check_row_version(mission: ProjectMission, expected: int | None) -> None:
    if expected is not None and expected != mission.row_version:
        raise mission_error(409, "ROW_VERSION_CONFLICT", "The mission changed; re-read it before acting",
                            row_version=mission.row_version)


# ---------------------------------------------------------------------------
# Create / read / update
# ---------------------------------------------------------------------------
@router.post("", response_model=MissionOut, status_code=status.HTTP_201_CREATED)
async def create_mission(
    payload: MissionCreate,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
) -> MissionOut:
    _assert_n0(payload.autonomy_level)
    version = await db.get(ProductVersion, payload.product_version_id)
    if version is None:
        raise mission_error(404, "PRODUCT_VERSION_NOT_FOUND", "Product version not found")
    if principal.principal_type == "user" and not principal.is_admin:
        raise mission_error(403, "MISSION_ADMIN_ONLY", "Only an administrator creates a mission in M0")
    source, delegation = await authorize_action(db, principal, "mission.manage", product_id=version.product_id)

    orchestrator = await db.get(Agent, payload.orchestrator_agent_id)
    if orchestrator is None or not orchestrator.is_active or orchestrator.status != "active":
        raise mission_error(422, "ORCHESTRATOR_INVALID", "The orchestrator must be an active agent")
    if payload.brief_artifact_id is not None and await db.get(Artifact, payload.brief_artifact_id) is None:
        raise mission_error(422, "BRIEF_NOT_FOUND", "brief_artifact_id is not an artifact")
    if payload.working_directory_path is not None and not payload.working_directory_path.startswith("/"):
        raise mission_error(422, "PATH_NOT_ABSOLUTE", "working_directory_path must be absolute")
    executors = list(dict.fromkeys(payload.executor_project_ids))
    for executor_id in executors:
        executor = await db.get(Project, executor_id)
        if executor is None:
            raise mission_error(422, "EXECUTOR_PROJECT_NOT_FOUND", "Executor project not found",
                                project_id=str(executor_id))
        if executor.project_type == "mission":
            raise mission_error(422, "EXECUTOR_IS_MISSION", "A mission cannot be an executor project (no nesting)",
                                project_id=str(executor_id))

    project = Project(
        name=payload.name,
        description=payload.description,
        product_version_id=payload.product_version_id,
        owner=principal.display_name,
        project_type="mission",
        status=MISSION_STATUS_PROJECTION["draft"],
        working_directory_path=payload.working_directory_path,
    )
    db.add(project)
    await db.flush()
    mission = ProjectMission(
        project_id=project.id,
        state="draft",
        priority=payload.priority,
        orchestrator_agent_id=orchestrator.id,
        autonomy_level="N0",
        brief_artifact_id=payload.brief_artifact_id,
        deadline_at=payload.deadline_at,
        budget_limit=payload.budget_limit,
        state_changed_at=utcnow(),
    )
    db.add(mission)
    # Exactly one orchestrator, and it is the mission's active coordinator.
    db.add(ProjectAgentMembership(
        project_id=project.id, agent_id=orchestrator.id, role="coordinator", status="active",
        responsibilities="Mission orchestrator",
    ))
    for executor_id in executors:
        db.add(MissionProjectLink(
            mission_project_id=project.id, executor_project_id=executor_id, linked_by=principal.display_name,
        ))
    db.add(AuditEvent(
        entity_type="mission", entity_id=project.id, event_type="mission_created", actor=principal.display_name,
        payload=_audit_payload(principal, source, delegation, orchestrator_agent_id=str(orchestrator.id),
                               executor_project_ids=[str(e) for e in executors]),
    ))
    await db.commit()
    project, mission = await _load(db, project.id)
    return await _out(db, project, mission)


@router.get("/{project_id}", response_model=MissionOut)
async def get_mission(
    project_id: uuid.UUID,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
) -> MissionOut:
    project, mission = await _load(db, project_id)
    return await _out(db, project, mission)


@router.patch("/{project_id}", response_model=MissionOut)
async def update_mission(
    project_id: uuid.UUID,
    payload: MissionUpdate,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
) -> MissionOut:
    """Edit planning fields. risk_level and required_review_layers are fixed
    in P1 (§3.1): editable in `draft` and in `planning`/`draft_plan` only."""
    project, mission = await _load(db, project_id, lock=True)
    if principal.principal_type == "user" and not principal.is_admin:
        raise mission_error(403, "MISSION_ADMIN_ONLY", "Only an administrator edits a mission in M0")
    source, delegation = await authorize_action(db, principal, "mission.manage", project_id=project_id)
    _check_row_version(mission, payload.expected_row_version)
    data = payload.model_dump(exclude_unset=True, exclude={"expected_row_version", "reason"})
    _assert_n0(data.get("autonomy_level"))
    if mission.state in ("completed", "cancelled"):
        raise mission_error(409, "MISSION_TERMINAL", "A completed or cancelled mission is read-only")
    if {"risk_level", "required_review_layers"} & data.keys():
        if not (mission.state == "draft" or (mission.state == "planning" and mission.planning_stage == "draft_plan")):
            raise mission_error(409, "PLANNING_FIXED_AFTER_P1",
                                "risk_level and required_review_layers are fixed after P1; use a change request")
    if data.get("required_review_layers") is not None:
        layers = list(dict.fromkeys(data["required_review_layers"]))
        unknown = [layer for layer in layers if layer not in REVIEW_LAYER_SET]
        if unknown:
            raise mission_error(422, "UNKNOWN_REVIEW_LAYER", "Unknown review layer", layers=unknown)
        data["required_review_layers"] = layers
    if "brief_artifact_id" in data and data["brief_artifact_id"] is not None:
        if await db.get(Artifact, data["brief_artifact_id"]) is None:
            raise mission_error(422, "BRIEF_NOT_FOUND", "brief_artifact_id is not an artifact")
    if not data:
        return await _out(db, project, mission)
    before = {k: getattr(mission, k) for k in data}
    for field, value in data.items():
        setattr(mission, field, value)
    mission.row_version += 1
    db.add(AuditEvent(
        entity_type="mission", entity_id=project_id, event_type="mission_updated", actor=principal.display_name,
        payload=_audit_payload(principal, source, delegation, reason=payload.reason,
                               changes={k: [str(before[k]), str(v)] for k, v in data.items()}),
    ))
    await db.commit()
    project, mission = await _load(db, project_id)
    return await _out(db, project, mission)


# ---------------------------------------------------------------------------
# State machine (§3)
# ---------------------------------------------------------------------------
@router.post("/{project_id}:transition", response_model=MissionOut)
async def transition_mission(
    project_id: uuid.UUID,
    payload: MissionTransitionIn,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
) -> MissionOut:
    project, mission = await _load(db, project_id, lock=True)
    from_state, to_state = mission.state, payload.to
    allowed = ALLOWED_TRANSITIONS.get((from_state, to_state))
    if from_state == "paused" and to_state != "cancelled":
        allowed = frozenset({"marcelo"}) if to_state == mission.paused_from_state else None
    if allowed is None:
        detail = (
            "Only the acceptance decision completes a mission"
            if to_state == "completed" else f"{from_state} -> {to_state} is not an allowed transition"
        )
        raise mission_error(409, "MISSION_TRANSITION_NOT_ALLOWED", detail, from_state=from_state, to=to_state)
    source, delegation, role = await _authorize_conduct(db, principal, mission, allowed)
    _check_row_version(mission, payload.expected_row_version)

    reason = (payload.reason or "").strip() or None
    if reason is None and (to_state in REASON_REQUIRED_TARGETS or from_state in REASON_REQUIRED_SOURCES):
        raise mission_error(422, "REASON_REQUIRED", "This transition requires a reason")
    if to_state == "paused" and role == "orchestrator" and not reason.startswith("blocked:"):
        raise mission_error(403, "ORCHESTRATOR_PAUSE_ONLY_WHEN_BLOCKED",
                            "The orchestrator pauses a mission only when blocked (reason 'blocked:...')")

    unmet = await transition_preconditions(db, mission, to_state)
    if unmet:
        raise mission_error(409, "MISSION_PRECONDITIONS_UNMET", "The transition's preconditions are not met",
                            from_state=from_state, to=to_state, unmet=unmet)

    now = utcnow()
    apply_mission_state(project, mission, to_state, reason, now)
    if (from_state, to_state) == ("draft", "planning"):
        mission.planning_stage = "draft_plan"
    elif (from_state, to_state) == ("planning", "ready"):
        mission.planning_stage = None
    db.add(AuditEvent(
        entity_type="mission", entity_id=project_id, event_type=f"mission_{from_state}_to_{to_state}",
        actor=principal.display_name,
        payload=_audit_payload(principal, source, delegation, reason=reason, from_state=from_state,
                               to=to_state, project_status=project.status, role=role),
    ))
    await db.commit()

    if to_state == "cancelled":
        await _archive_queued_mission_demands(db, project_id, principal.display_name, reason or "")
    project, mission = await _load(db, project_id)
    return await _out(db, project, mission)


async def _archive_queued_mission_demands(
    db: AsyncSession, project_id: uuid.UUID, actor: str, reason: str
) -> None:
    """§3: a cancelled mission's queued work is archived through the operator
    decision path; runs already in flight are not killed (they follow the
    uncertain/confirm_inactive path), and decide_demand refuses them."""
    from app.api.schemas.demand import DemandDecisionIn
    from app.core.demand_workflow import WorkflowBlocked, decide_demand

    task_ids = [t.id for t in await mission_tasks(db, project_id)]
    if not task_ids:
        return
    demands = list((await db.execute(select(AgentDemand).where(
        AgentDemand.origin_type == "task",
        AgentDemand.origin_id.in_(task_ids),
        AgentDemand.status != "archived",
        AgentDemand.dispatch_status.is_(None),
        AgentDemand.agent_run_id.is_(None),
    ))).scalars())
    for demand in demands:
        try:
            await decide_demand(
                db, demand, DemandDecisionIn(action="archive", reason=f"Mission cancelled: {reason}"), actor=actor,
            )
        except WorkflowBlocked:
            await db.rollback()


# ---------------------------------------------------------------------------
# Planning pipeline (§3.1)
# ---------------------------------------------------------------------------
def _request_hash(project_id: uuid.UUID, payload: PlanningAdvanceIn) -> str:
    body = {"project_id": str(project_id), "to": payload.to, "reason": payload.reason,
            "expected_row_version": payload.expected_row_version}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


@router.post("/{project_id}/planning:advance", response_model=PlanningAdvanceOut)
async def advance_planning(
    project_id: uuid.UUID,
    payload: PlanningAdvanceIn,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
) -> PlanningAdvanceOut:
    project, mission = await _load(db, project_id, lock=True)
    source, delegation, _role = await _authorize_conduct(db, principal, mission)
    request_hash = _request_hash(project_id, payload)

    previous = (await db.execute(select(MissionDecision).where(
        MissionDecision.actor_type == principal.principal_type,
        MissionDecision.actor_id == principal.principal_id,
        MissionDecision.idempotency_key == payload.idempotency_key,
    ))).scalar_one_or_none()
    if previous is not None:
        if (previous.facts or {}).get("request_hash") != request_hash:
            raise mission_error(409, "IDEMPOTENCY_KEY_REUSED", "This idempotency key was used for another request")
        if previous.status == "refused":
            raise HTTPException(409, detail={**previous.facts["refusal"], "replayed": True})
        return PlanningAdvanceOut(mission=await _out(db, project, mission), decision_id=previous.id, replayed=True,
                                  not_evaluated=previous.facts.get("not_evaluated", []))

    if mission.state != "planning":
        raise mission_error(409, "MISSION_NOT_PLANNING", "The planning pipeline runs only while planning",
                            state=mission.state)
    _check_row_version(mission, payload.expected_row_version)

    from_stage = mission.planning_stage
    refusal: dict[str, Any] | None = None
    not_evaluated: list[dict] = []
    allowed_next = next_planning_stages(mission)
    if payload.to not in allowed_next:
        refusal = {"code": "PLANNING_STAGE_OUT_OF_ORDER",
                   "message": "Planning stages advance only to the next one, in order",
                   "from_stage": from_stage, "to": payload.to, "allowed": list(allowed_next)}
    else:
        unmet, not_evaluated = await planning_exit_conditions(db, mission)
        if unmet:
            refusal = {"code": "PLANNING_EXIT_CONDITIONS_UNMET",
                       "message": f"Stage {from_stage} cannot be left yet",
                       "from_stage": from_stage, "to": payload.to, "unmet": unmet,
                       "not_evaluated": not_evaluated}

    skipped_cross_review = payload.to == "decisions" and from_stage == "consolidation"
    decision = MissionDecision(
        mission_project_id=project_id,
        action="advance_planning",
        reason=payload.reason,
        facts={"request_hash": request_hash, "from_stage": from_stage, "to": payload.to,
               "risk_level": mission.risk_level, "row_version": mission.row_version,
               "cross_review_skipped": skipped_cross_review and refusal is None,
               "not_evaluated": not_evaluated, **({"refusal": refusal} if refusal else {})},
        autonomy_level=mission.autonomy_level,
        actor_type=principal.principal_type,
        actor_id=principal.principal_id,
        actor_name=principal.display_name,
        authority_source=source,
        delegation_id=delegation.id if delegation is not None else None,
        status="refused" if refusal else "applied",
        refusal_code=refusal["code"] if refusal else None,
        idempotency_key=payload.idempotency_key,
    )
    db.add(decision)
    if refusal is None:
        mission.planning_stage = payload.to
        mission.row_version += 1
    await db.flush()
    db.add(AuditEvent(
        entity_type="mission", entity_id=project_id, event_type="mission_decision_advance_planning",
        actor=principal.display_name,
        payload=_audit_payload(principal, source, delegation, decision_id=str(decision.id),
                               idempotency_key=payload.idempotency_key, reason=payload.reason,
                               from_stage=from_stage, to=payload.to, status=decision.status,
                               refusal_code=decision.refusal_code),
    ))
    await db.commit()
    if refusal is not None:
        raise HTTPException(409, detail=refusal)
    project, mission = await _load(db, project_id)
    return PlanningAdvanceOut(mission=await _out(db, project, mission), decision_id=decision.id,
                              not_evaluated=not_evaluated)

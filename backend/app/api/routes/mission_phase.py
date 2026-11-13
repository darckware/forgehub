"""Mission phases (docs/architecture/MISSION_PHASES_PLAN.md, 2026-11-12).

A phase is a ``mission_project_links`` row (core/mission_phases.py). Endpoints
(router prefix ``/api/v1/missions``):

- ``GET    /{id}/phases``                                       phases, planning items and tasks in order
- ``POST   /{id}/phases``                                       create (also creates the phase's project)
- ``PATCH  /{id}/phases/{phase_id}``                            rename / objective
- ``DELETE /{id}/phases/{phase_id}``                            only an empty phase
- ``POST   /{id}/phases:reorder``                               {phase_ids}
- ``POST   /{id}/phases/{phase_id}/plannings:reorder``          {planning_item_ids}
- ``POST   /{id}/plannings/{planning_item_id}/tasks:sequence``  {task_ids}: positions + finish_to_start chain
- ``POST   /{id}/phases/{phase_id}:request-homologation``       admin or orchestrator
- ``POST   /{id}/phases/{phase_id}:report-homologation``        only the phase's homologator (agt_)
- ``POST   /{id}/phases/{phase_id}:approve`` / ``:return``      Marcelo (admin JWT) only

Edits: an administrator or the mission's orchestrator (``_authorize_conduct``,
``mission.orchestrate``). Phases are part of the plan: they change only while
the mission is draft/planning with no baseline (409 MISSION_PHASES_FROZEN).
An agent's write needs ``MISSION_TOOLS_ENABLED`` and an ``idempotency_key``
(the §0.4 receipt); a person's key is optional. Errors use the §0.3 object
form.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import delete, func, select

from app.api.routes.mission import (
    CODE_RUNTIMES,
    _assert_can_read,
    _assert_name_free_in_version,
    _audit_payload,
    _authorize_conduct,
    _load,
)
from app.api.routes.project import _clear_project_dependencies, build_project
from app.api.schemas.mission_phase import (
    HomologationReportIn,
    HomologationRequestIn,
    PhaseApproveIn,
    PhaseCreateIn,
    PhaseReturnIn,
    PhasesReorderIn,
    PhaseUpdateIn,
    PlanningsReorderIn,
    TasksSequenceIn,
)
from app.api.schemas.project import ProjectCreate
from app.core.command_receipts import (
    begin_command,
    enforce_command_limits,
    limit_command_body,
    record_command,
    request_hash,
)
from app.core.deps import ActorPrincipal, get_actor_principal
from app.core.dispatch_signal import wake_scheduled_dispatch
from app.core.mission import _find_cycle, mission_error
from app.core.mission_phases import (
    TASK_DONE_STATUSES,
    item_tasks,
    mission_phases,
    phase_participants,
    phase_tasks,
    phases_frozen,
    phases_view,
    project_planning_items,
)
from app.core.mission_plan import current_baseline_of_task, mission_scope_tasks
from app.db.base import get_db
from app.db.models.agent import Agent
from app.db.models.backlog import PlanningItem
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent
from app.db.models.mission import MissionProjectLink, ProjectMission
from app.db.models.notification import Notification
from app.db.models.orchestration import ProjectAgentMembership
from app.db.models.project import ChangeRequest, Project
from app.db.models.task import ProjectTask, TaskDependency, TaskExecution

router = APIRouter(prefix="/api/v1/missions", tags=["missions"])

WRITE_DEPENDENCIES = [Depends(limit_command_body)]
REQUESTABLE_STATUSES = ("planned", "in_progress", "returned")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
async def _begin(
    db, principal: ActorPrincipal, key: str | None, command: str, body: dict[str, Any],
) -> tuple[str, JSONResponse | None]:
    """Agents: switch, rate limit and a mandatory key. Anyone sending a key
    gets the receipt (same key + body replays, another body is 409)."""
    if principal.principal_type == "agent":
        enforce_command_limits(principal)
        if not key:
            raise mission_error(422, "IDEMPOTENCY_KEY_REQUIRED", "idempotency_key is required")
    body_hash = request_hash(command, body)
    if key:
        return body_hash, await begin_command(db, principal, key, command, body_hash)
    return body_hash, None


def _finish(db, principal, key, command, body_hash, status_code, out, target_id) -> None:
    if key:
        record_command(db, principal, key, command, body_hash, status_code, out,
                       target_type="mission_phase", target_id=target_id)


def _assert_editable(mission: ProjectMission) -> None:
    if phases_frozen(mission):
        raise mission_error(409, "MISSION_PHASES_FROZEN",
                            "Phases change only while the mission is draft or planning and has no baseline",
                            state=mission.state,
                            current_baseline_id=str(mission.current_baseline_id) if mission.current_baseline_id
                            else None)


def _assert_not_terminal(mission: ProjectMission) -> None:
    if mission.state in ("completed", "cancelled"):
        raise mission_error(409, "MISSION_TERMINAL", "A completed or cancelled mission is read-only")


async def _phase(db, mission: ProjectMission, phase_id: uuid.UUID) -> MissionProjectLink:
    phase = (await db.execute(
        select(MissionProjectLink).where(MissionProjectLink.id == phase_id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if phase is None or phase.mission_project_id != mission.project_id or not phase.is_phase:
        raise mission_error(404, "PHASE_NOT_FOUND", "Phase not found in this mission")
    return phase


def _assert_phase_status(phase: MissionProjectLink, allowed: tuple[str, ...], expected: str | None = None) -> None:
    if (expected is not None and expected != phase.phase_status) or phase.phase_status not in allowed:
        raise mission_error(409, "PHASE_STATE_CHANGED", f"The phase is {phase.phase_status}",
                            phase_status=phase.phase_status, allowed=list(allowed))


def _project_name(mission_name: str, position: int, name: str) -> str:
    return f"{mission_name} · Fase {position} · {name}"[:255]


async def _sync_project_names(db, mission_project: Project, phases: list[MissionProjectLink]) -> None:
    """Keep each phase project's name in step with its phase (position, name).
    A new name must be free in the product version among projects other than
    the ones being renamed here (409 PROJECT_NAME_EXISTS_IN_VERSION)."""
    renames: dict[uuid.UUID, str] = {}
    for phase in phases:
        project = await db.get(Project, phase.executor_project_id)
        if project is None:
            continue
        name = _project_name(mission_project.name, phase.position, phase.name)
        if project.name != name:
            renames[project.id] = name
    if not renames:
        return
    await db.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(
        f"project-names:{mission_project.product_version_id}", 0))))
    clash = (await db.execute(select(Project.id, Project.name).where(
        Project.product_version_id == mission_project.product_version_id,
        Project.id.notin_(list(renames)),
        func.lower(func.btrim(Project.name)).in_([n.strip().lower() for n in renames.values()]),
    ).limit(1))).first()
    if clash is not None:
        raise mission_error(409, "PROJECT_NAME_EXISTS_IN_VERSION",
                            "A project with this name already exists in this product version",
                            project_id=str(clash.id), name=clash.name)
    for project_id, name in renames.items():
        (await db.get(Project, project_id)).name = name


async def _out(db, mission: ProjectMission, **extra: Any) -> dict[str, Any]:
    return {"mission_project_id": str(mission.project_id), "editable": not phases_frozen(mission),
            "phases": await phases_view(db, mission), **extra}


def _audit(db, principal, source, delegation, mission, event_type, key=None, **payload) -> None:
    db.add(AuditEvent(
        entity_type="mission", entity_id=mission.project_id, event_type=event_type, actor=principal.display_name,
        payload=_audit_payload(principal, source, delegation, idempotency_key=key, **payload),
    ))


def _respond(status_code: int, body: dict[str, Any]) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=body)


async def _orchestrator_task(
    db, mission: ProjectMission, mission_project: Project, phase: MissionProjectLink, subject: str, body: str,
    *, from_agent: Agent | None = None,
) -> AgentDemand:
    """A Messages Task to the orchestrator about a phase (from the given agent,
    else self-addressed): queued now, so the orchestrator acts on it."""
    orchestrator = await db.get(Agent, mission.orchestrator_agent_id)
    sender = from_agent or orchestrator
    demand = AgentDemand(
        from_agent=sender.name if sender else "forgehub", from_agent_id=sender.id if sender else None,
        subject=subject[:255], body=body, status="new", target_agent_id=mission.orchestrator_agent_id,
        project_id=mission.project_id, working_path=mission_project.working_directory_path,
        origin_type="task", channel="factory", channel_ref=str(phase.id), requires_response=False,
        scheduled_at=_now(), fixed_agent=True,
    )
    db.add(demand)
    await db.flush()
    return demand


def _notify(db, title: str, message: str, event_key: str, severity: str = "warning") -> None:
    db.add(Notification(source="system", severity=severity, title=title[:255], message=message,
                        event_key=event_key[:512], occurred_at=_now()))


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------
@router.get("/{project_id}/phases")
async def list_phases(
    project_id: uuid.UUID,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db=Depends(get_db),
) -> dict[str, Any]:
    """Phases in order, each with its status, homologation record, executor
    project, planning items in order and their tasks in order. Admins and
    active members of the mission only (anyone else: the same 404)."""
    _project, mission = await _load(db, project_id)
    await _assert_can_read(db, principal, project_id)
    return await _out(db, mission)


# ---------------------------------------------------------------------------
# Create / update / delete / reorder
# ---------------------------------------------------------------------------
@router.post("/{project_id}/phases", status_code=status.HTTP_201_CREATED, dependencies=WRITE_DEPENDENCIES)
async def create_phase(
    project_id: uuid.UUID,
    payload: PhaseCreateIn,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db=Depends(get_db),
):
    """Add a phase at the end. Creates its executor project in the same
    transaction (same product version and working directory as the mission,
    named "<mission> · Fase N · <name>"), with the orchestrator as its
    coordinator so it can staff it (manage_project_members)."""
    command = "mission.phase.create"
    body = {"project_id": str(project_id), **payload.model_dump(mode="json")}
    mission_project, mission = await _load(db, project_id, lock=True)
    source, delegation, role = await _authorize_conduct(db, principal, mission)
    body_hash, replay = await _begin(db, principal, payload.idempotency_key, command, body)
    if replay is not None:
        return replay
    _assert_editable(mission)
    name = payload.name.strip()
    if not name:
        raise mission_error(422, "PHASE_NAME_REQUIRED", "The phase name cannot be blank")
    phases = await mission_phases(db, mission.project_id, lock=True)
    position = max((p.position for p in phases), default=0) + 1
    project_name = _project_name(mission_project.name, position, name)
    await _assert_name_free_in_version(db, mission_project.product_version_id, project_name)
    executor = await build_project(db, ProjectCreate(
        name=project_name, product_version_id=mission_project.product_version_id,
        description=(payload.objective or "").strip() or None, owner=principal.display_name,
        working_directory_path=mission_project.working_directory_path,
    ), project_type="creation")
    db.add(ProjectAgentMembership(
        project_id=executor.id, agent_id=mission.orchestrator_agent_id, role="coordinator", status="active",
        responsibilities=f"Mission orchestrator (phase {position})",
    ))
    phase = MissionProjectLink(
        mission_project_id=mission.project_id, executor_project_id=executor.id, linked_by=principal.display_name,
        position=position, name=name, objective=(payload.objective or "").strip() or None, is_phase=True,
    )
    db.add(phase)
    await db.flush()
    _audit(db, principal, source, delegation, mission, "mission_phase_created", payload.idempotency_key,
           role=role, phase_id=str(phase.id), position=position, name=name,
           executor_project_id=str(executor.id))
    out = await _out(db, mission, phase_id=str(phase.id))
    _finish(db, principal, payload.idempotency_key, command, body_hash, 201, out, phase.id)
    await db.commit()
    return _respond(201, out)


@router.patch("/{project_id}/phases/{phase_id}", dependencies=WRITE_DEPENDENCIES)
async def update_phase(
    project_id: uuid.UUID,
    phase_id: uuid.UUID,
    payload: PhaseUpdateIn,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db=Depends(get_db),
):
    command = "mission.phase.update"
    body = {"project_id": str(project_id), "phase_id": str(phase_id), **payload.model_dump(mode="json")}
    mission_project, mission = await _load(db, project_id, lock=True)
    source, delegation, role = await _authorize_conduct(db, principal, mission)
    body_hash, replay = await _begin(db, principal, payload.idempotency_key, command, body)
    if replay is not None:
        return replay
    _assert_editable(mission)
    phase = await _phase(db, mission, phase_id)
    changes: dict[str, list[Any]] = {}
    fields = payload.model_fields_set - {"idempotency_key"}
    if "name" in fields and payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise mission_error(422, "PHASE_NAME_REQUIRED", "The phase name cannot be blank")
        if name != phase.name:
            changes["name"] = [phase.name, name]
            phase.name = name
            await _sync_project_names(db, mission_project, [phase])
    if "objective" in fields:
        objective = (payload.objective or "").strip() or None
        if objective != phase.objective:
            changes["objective"] = [phase.objective, objective]
            phase.objective = objective
    if changes:
        _audit(db, principal, source, delegation, mission, "mission_phase_updated", payload.idempotency_key,
               role=role, phase_id=str(phase.id), changes=changes)
    await db.flush()
    out = await _out(db, mission, phase_id=str(phase.id))
    _finish(db, principal, payload.idempotency_key, command, body_hash, 200, out, phase.id)
    await db.commit()
    return _respond(200, out)


@router.delete("/{project_id}/phases/{phase_id}", dependencies=WRITE_DEPENDENCIES)
async def delete_phase(
    project_id: uuid.UUID,
    phase_id: uuid.UUID,
    idempotency_key: str | None = Query(default=None, min_length=1, max_length=150),
    principal: ActorPrincipal = Depends(get_actor_principal),
    db=Depends(get_db),
):
    """Remove an empty phase (no planning item, no task) and its project; the
    following phases move up one position."""
    command = "mission.phase.delete"
    body = {"project_id": str(project_id), "phase_id": str(phase_id)}
    mission_project, mission = await _load(db, project_id, lock=True)
    source, delegation, role = await _authorize_conduct(db, principal, mission)
    body_hash, replay = await _begin(db, principal, idempotency_key, command, body)
    if replay is not None:
        return replay
    _assert_editable(mission)
    phase = await _phase(db, mission, phase_id)
    executor_id = phase.executor_project_id
    items = await db.scalar(select(func.count(PlanningItem.id)).where(PlanningItem.project_id == executor_id))
    change_requests = select(ChangeRequest.id).where(ChangeRequest.project_id == executor_id)
    cr_tasks = await db.scalar(select(func.count(ProjectTask.id)).where(
        ProjectTask.change_request_id.in_(change_requests)))
    if items or cr_tasks:
        raise mission_error(409, "PHASE_NOT_EMPTY", "Only a phase with no planning item and no task is removed",
                            planning_items=items, change_request_tasks=cr_tasks)
    other_missions = await db.scalar(select(func.count(MissionProjectLink.id)).where(
        MissionProjectLink.executor_project_id == executor_id, MissionProjectLink.id != phase.id))
    removed = {"phase_id": str(phase.id), "position": phase.position, "name": phase.name,
               "executor_project_id": str(executor_id)}
    await db.delete(phase)
    await db.flush()
    if not other_missions:
        await db.execute(delete(ProjectAgentMembership).where(ProjectAgentMembership.project_id == executor_id))
        await _clear_project_dependencies(db, executor_id)
        project = await db.get(Project, executor_id)
        if project is not None:
            await db.delete(project)
    remaining = await mission_phases(db, mission.project_id, lock=True)
    for position, other in enumerate(remaining, start=1):
        other.position = position
    await _sync_project_names(db, mission_project, remaining)
    _audit(db, principal, source, delegation, mission, "mission_phase_deleted", idempotency_key, role=role,
           project_removed=not other_missions, **removed)
    await db.flush()
    out = await _out(db, mission)
    _finish(db, principal, idempotency_key, command, body_hash, 200, out, phase_id)
    await db.commit()
    return _respond(200, out)


@router.post("/{project_id}/phases:reorder", dependencies=WRITE_DEPENDENCIES)
async def reorder_phases(
    project_id: uuid.UUID,
    payload: PhasesReorderIn,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db=Depends(get_db),
):
    """``phase_ids`` lists every phase of the mission exactly once, in the new order."""
    command = "mission.phase.reorder"
    body = {"project_id": str(project_id), **payload.model_dump(mode="json")}
    mission_project, mission = await _load(db, project_id, lock=True)
    source, delegation, role = await _authorize_conduct(db, principal, mission)
    body_hash, replay = await _begin(db, principal, payload.idempotency_key, command, body)
    if replay is not None:
        return replay
    _assert_editable(mission)
    phases = {p.id: p for p in await mission_phases(db, mission.project_id, lock=True)}
    if len(payload.phase_ids) != len(set(payload.phase_ids)) or set(payload.phase_ids) != set(phases):
        raise mission_error(422, "PHASE_SET_MISMATCH", "phase_ids must list every phase of the mission once",
                            expected=sorted(str(p) for p in phases))
    before = {str(p.id): p.position for p in phases.values()}
    for position, phase_id in enumerate(payload.phase_ids, start=1):
        phases[phase_id].position = position
    ordered = [phases[p] for p in payload.phase_ids]
    await _sync_project_names(db, mission_project, ordered)
    _audit(db, principal, source, delegation, mission, "mission_phases_reordered", payload.idempotency_key,
           role=role, before=before, after={str(p.id): p.position for p in ordered})
    await db.flush()
    out = await _out(db, mission)
    _finish(db, principal, payload.idempotency_key, command, body_hash, 200, out, mission.project_id)
    await db.commit()
    return _respond(200, out)


@router.post("/{project_id}/phases/{phase_id}/plannings:reorder", dependencies=WRITE_DEPENDENCIES)
async def reorder_plannings(
    project_id: uuid.UUID,
    phase_id: uuid.UUID,
    payload: PlanningsReorderIn,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db=Depends(get_db),
):
    """Order the phase's planning items (they may still run in parallel; the
    order is how the plan reads). Lists every planning item once."""
    command = "mission.phase.plannings_reorder"
    body = {"project_id": str(project_id), "phase_id": str(phase_id), **payload.model_dump(mode="json")}
    _mission_project, mission = await _load(db, project_id, lock=True)
    source, delegation, role = await _authorize_conduct(db, principal, mission)
    body_hash, replay = await _begin(db, principal, payload.idempotency_key, command, body)
    if replay is not None:
        return replay
    _assert_editable(mission)
    phase = await _phase(db, mission, phase_id)
    items = {i.id: i for i in await project_planning_items(db, phase.executor_project_id)}
    wanted = payload.planning_item_ids
    if len(wanted) != len(set(wanted)) or set(wanted) != set(items):
        raise mission_error(422, "PLANNING_SET_MISMATCH",
                            "planning_item_ids must list every planning item of the phase once",
                            expected=sorted(str(i) for i in items))
    for position, item_id in enumerate(wanted, start=1):
        items[item_id].position = position
    _audit(db, principal, source, delegation, mission, "mission_phase_plannings_reordered", payload.idempotency_key,
           role=role, phase_id=str(phase.id), planning_item_ids=[str(i) for i in wanted])
    await db.flush()
    out = await _out(db, mission)
    _finish(db, principal, payload.idempotency_key, command, body_hash, 200, out, phase.id)
    await db.commit()
    return _respond(200, out)


@router.post("/{project_id}/plannings/{planning_item_id}/tasks:sequence", dependencies=WRITE_DEPENDENCIES)
async def sequence_tasks(
    project_id: uuid.UUID,
    planning_item_id: uuid.UUID,
    payload: TasksSequenceIn,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db=Depends(get_db),
):
    """Run a planning item's tasks in this order: ``task_ids`` lists exactly
    its non-cancelled tasks; positions become 1..n and the dependencies
    between those tasks are replaced by the chain t1 <- t2 <- ... <- tn
    (finish_to_start). Dependencies on tasks outside the item are kept.
    Refused when a task is frozen in a current baseline (TASK_IN_BASELINE)
    or the result would form a cycle (DEPENDENCY_CYCLE)."""
    command = "mission.phase.tasks_sequence"
    body = {"project_id": str(project_id), "planning_item_id": str(planning_item_id),
            **payload.model_dump(mode="json")}
    _mission_project, mission = await _load(db, project_id, lock=True)
    source, delegation, role = await _authorize_conduct(db, principal, mission)
    body_hash, replay = await _begin(db, principal, payload.idempotency_key, command, body)
    if replay is not None:
        return replay
    _assert_not_terminal(mission)
    item = await db.get(PlanningItem, planning_item_id)
    scope_projects = {mission.project_id, *[p.executor_project_id for p in await mission_phases(db, mission.project_id)]}
    if item is None or item.project_id not in scope_projects:
        raise mission_error(404, "PLANNING_ITEM_NOT_FOUND", "Planning item not found in this mission")
    tasks = [t for t in (await item_tasks(db, [item.id]))[item.id] if t.status != "cancelled"]
    by_id = {t.id: t for t in tasks}
    wanted = payload.task_ids
    if len(wanted) != len(set(wanted)) or set(wanted) != set(by_id):
        raise mission_error(422, "TASK_SET_MISMATCH",
                            "task_ids must list every non-cancelled task of the planning item once",
                            expected=sorted(t.number for t in tasks))
    frozen = [by_id[t].number for t in wanted if await current_baseline_of_task(db, t) is not None]
    if frozen:
        raise mission_error(409, "TASK_IN_BASELINE",
                            "A task frozen in a current baseline changes only through a change request",
                            task_numbers=frozen)
    ids = list(by_id)
    await db.execute(delete(TaskDependency).where(
        TaskDependency.task_id.in_(ids), TaskDependency.depends_on_task_id.in_(ids)))
    for position, task_id in enumerate(wanted, start=1):
        by_id[task_id].position = position
        if position > 1:
            db.add(TaskDependency(task_id=task_id, depends_on_task_id=wanted[position - 2],
                                  dependency_type="finish_to_start"))
    await db.flush()
    scope = await mission_scope_tasks(db, mission.project_id)
    edges = [(d.task_id, d.depends_on_task_id) for d in (await db.execute(
        select(TaskDependency).where(TaskDependency.task_id.in_(list(scope))))).scalars()]
    cycle = _find_cycle(edges)
    if cycle:
        raise mission_error(409, "DEPENDENCY_CYCLE", "The sequence would form a dependency cycle",
                            task_ids=[str(t) for t in cycle])
    _audit(db, principal, source, delegation, mission, "mission_tasks_sequenced", payload.idempotency_key,
           role=role, planning_item_id=str(item.id), task_numbers=[by_id[t].number for t in wanted])
    out = await _out(db, mission)
    _finish(db, principal, payload.idempotency_key, command, body_hash, 200, out, item.id)
    await db.commit()
    return _respond(200, out)


# ---------------------------------------------------------------------------
# Homologation
# ---------------------------------------------------------------------------
async def _latest_evidence(db, task_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    evidence: dict[uuid.UUID, str] = {}
    if not task_ids:
        return evidence
    for task_id, ref in (await db.execute(
        select(TaskExecution.task_id, TaskExecution.evidence_ref)
        .where(TaskExecution.task_id.in_(task_ids), TaskExecution.evidence_ref.is_not(None))
        .order_by(TaskExecution.created_at.desc())
    )).all():
        evidence.setdefault(task_id, ref)
    return evidence


async def _homologation_body(db, mission_project: Project, phase: MissionProjectLink) -> str:
    items = await project_planning_items(db, phase.executor_project_id)
    tasks_by_item = await item_tasks(db, [i.id for i in items])
    evidence = await _latest_evidence(db, [t.id for ts in tasks_by_item.values() for t in ts])
    header = [
        f"Homologação da Fase {phase.position} — {phase.name} (missão {mission_project.name}).",
        f"Objetivo da fase (o que ela entrega e o que deixa de fora):\n{phase.objective or '(sem objetivo)'}",
        "Fora do escopo: tudo o que o objetivo acima não inclui. Não reprove a fase por algo que ela "
        "declaradamente deixa para outra fase.",
    ]
    delivered = ["Planejamentos e tarefas entregues:"]
    for item in items:
        delivered.append(f"- {item.title}")
        for task in tasks_by_item[item.id]:
            if task.status == "cancelled":
                continue
            delivered.append(f"  {task.position or '-'}. Task #{task.number}: {task.title} "
                             f"[{task.status}] evidência: {evidence.get(task.id, '(nenhuma)')}")
    footer = [
        f"Diretório de trabalho: {mission_project.working_directory_path or '(não informado)'}",
        "Teste a entrega contra o objetivo da fase (rode, navegue, confira o que foi pedido) — não basta "
        "ler o código. Você é independente: não executou nem revisou nenhuma tarefa desta fase.",
        "Responda SOMENTE pela ferramenta MCP report_phase_homologation("
        f"project_id=\"{mission_project.id}\", phase={phase.position}, verdict=\"approved\"|\"rejected\", "
        "summary=..., evidence=[git:/file:/url ...]). Aprovar envia a fase para a decisão do Marcelo; "
        "reprovar devolve a fase ao orquestrador com os seus achados.",
    ]
    return "\n\n".join([*header, "\n".join(delivered), *footer])


def _demand_in_flight(demand: AgentDemand) -> bool:
    """Started, reserved, or of unknown outcome (as reserve_dispatch reads it)."""
    from app.core.demand_workflow import requires_reconciliation

    return (demand.dispatch_status in ("dispatched", "running")
            or (demand.dispatch_status is None and demand.agent_run_id is not None)
            or requires_reconciliation(demand))


async def _withdraw_homologation(db, phase: MissionProjectLink) -> dict[str, Any]:
    """Replacing a homologation: the previous task is archived when it never
    started; a run in flight (or of unknown outcome) refuses
    (409 HOMOLOGATION_RUN_IN_FLIGHT); a finished one is left as history."""
    demand = await db.get(AgentDemand, phase.homologation_demand_id) if phase.homologation_demand_id else None
    withdrawn = False
    if demand is not None:
        if _demand_in_flight(demand):
            raise mission_error(409, "HOMOLOGATION_RUN_IN_FLIGHT",
                                "The current homologation run is in flight or of unknown outcome",
                                demand_id=str(demand.id), dispatch_status=demand.dispatch_status)
        if demand.dispatch_status is None and demand.status != "archived":
            demand.status = "archived"
            demand.scheduled_at = None
            withdrawn = True
    return {"previous_homologator_agent_id": str(phase.homologator_agent_id) if phase.homologator_agent_id else None,
            "previous_demand_id": str(demand.id) if demand else None, "previous_demand_archived": withdrawn}


@router.post("/{project_id}/phases/{phase_id}:request-homologation", dependencies=WRITE_DEPENDENCIES)
async def request_homologation(
    project_id: uuid.UUID,
    phase_id: uuid.UUID,
    payload: HomologationRequestIn,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db=Depends(get_db),
):
    """Send a phase whose tasks are all done to an external, independent
    homologator: an active claude/codex/agy agent with an active
    ``homologation`` membership in the mission that neither executed nor
    reviewed any task of the phase. It receives one Messages Task (from the
    orchestrator, fixed agent, in the mission's working directory) and
    answers with report_phase_homologation. With ``replace: true`` a phase
    already homologating is re-sent (same or another homologator): the
    previous task is archived if it never started, a run in flight refuses
    (409 HOMOLOGATION_RUN_IN_FLIGHT), and the audit keeps the previous
    homologator."""
    from app.api.routes.mission import _active_membership

    command = "mission.phase.request_homologation"
    body = {"project_id": str(project_id), "phase_id": str(phase_id), **payload.model_dump(mode="json")}
    mission_project, mission = await _load(db, project_id, lock=True)
    source, delegation, role = await _authorize_conduct(db, principal, mission)
    body_hash, replay = await _begin(db, principal, payload.idempotency_key, command, body)
    if replay is not None:
        return replay
    _assert_not_terminal(mission)
    phase = await _phase(db, mission, phase_id)
    allowed = REQUESTABLE_STATUSES + (("homologating",) if payload.replace else ())
    _assert_phase_status(phase, allowed, payload.expected_phase_status)
    replaced: dict[str, Any] | None = None
    if phase.phase_status == "homologating":
        replaced = await _withdraw_homologation(db, phase)
    tasks = [t for t in await phase_tasks(db, phase) if t.status != "cancelled"]
    if not tasks:
        raise mission_error(409, "PHASE_EMPTY", "The phase has no task to homologate")
    open_tasks = [t for t in tasks if t.status not in TASK_DONE_STATUSES]
    if open_tasks:
        raise mission_error(409, "PHASE_TASKS_OPEN", "Every task of the phase must be done first",
                            tasks=[{"task_id": str(t.id), "number": t.number, "title": t.title,
                                    "status": t.status} for t in open_tasks])
    agent = await db.get(Agent, payload.homologator_agent_id)
    if agent is None or not agent.is_active or agent.status != "active":
        raise mission_error(422, "HOMOLOGATOR_NOT_ELIGIBLE", "The homologator must be an active agent")
    if agent.runtime_type not in CODE_RUNTIMES:
        raise mission_error(422, "HOMOLOGATOR_NOT_EXTERNAL",
                            "The homologator must be an external agent (claude/codex/agy)",
                            runtime_type=agent.runtime_type)
    membership = await _active_membership(db, mission.project_id, agent.id)
    if membership is None or membership.role != "homologation":
        raise mission_error(409, "HOMOLOGATOR_NOT_MEMBER",
                            "The homologator needs an active homologation membership in the mission",
                            role=membership.role if membership else None)
    executors, reviewers = await phase_participants(db, tasks)
    if agent.id in executors or agent.id in reviewers:
        raise mission_error(409, "HOMOLOGATOR_NOT_INDEPENDENT",
                            "The homologator executed or reviewed a task of this phase",
                            as_executor=agent.id in executors, as_reviewer=agent.id in reviewers)

    orchestrator = await db.get(Agent, mission.orchestrator_agent_id)
    demand = AgentDemand(
        from_agent=orchestrator.name if orchestrator else "forgehub",
        from_agent_id=orchestrator.id if orchestrator else None,
        subject=f"Homologação: Fase {phase.position} — {phase.name} ({mission_project.name})"[:255],
        body=await _homologation_body(db, mission_project, phase),
        status="new", target_agent_id=agent.id, project_id=phase.executor_project_id,
        working_path=mission_project.working_directory_path,
        # No origin_id: the run tests the whole phase, not one task, and must
        # not be held by the phase gate it is closing.
        origin_type="task", channel="factory", channel_ref=str(phase.id),
        requires_response=False, scheduled_at=_now(), fixed_agent=True,
    )
    db.add(demand)
    await db.flush()
    previous = phase.phase_status
    phase.phase_status = "homologating"
    phase.homologator_agent_id = agent.id
    phase.homologation_demand_id = demand.id
    phase.homologation_verdict = phase.homologation_summary = phase.homologation_evidence = None
    phase.homologated_at = None
    phase.decided_by = phase.decided_at = phase.decision_reason = None
    _audit(db, principal, source, delegation, mission, "mission_phase_homologation_requested",
           payload.idempotency_key, role=role, phase_id=str(phase.id), position=phase.position,
           previous_status=previous, homologator_agent_id=str(agent.id), demand_id=str(demand.id),
           replaced=replaced)
    await db.flush()
    out = await _out(db, mission, phase_id=str(phase.id), demand_id=str(demand.id), demand_number=demand.number)
    _finish(db, principal, payload.idempotency_key, command, body_hash, 200, out, phase.id)
    await db.commit()
    wake_scheduled_dispatch()
    return _respond(200, out)


@router.post("/{project_id}/phases/{phase_id}:report-homologation", dependencies=WRITE_DEPENDENCIES)
async def report_homologation(
    project_id: uuid.UUID,
    phase_id: uuid.UUID,
    payload: HomologationReportIn,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db=Depends(get_db),
):
    """The homologator's verdict, with its own agt_ only. ``approved`` sends
    the phase to Marcelo (awaiting_approval + a notification); ``rejected``
    returns it (returned + a notification + a Messages Task to the
    orchestrator with the findings)."""
    command = "mission.phase.report_homologation"
    body = {"project_id": str(project_id), "phase_id": str(phase_id), **payload.model_dump(mode="json")}
    mission_project, mission = await _load(db, project_id, lock=True)
    phase = await _phase(db, mission, phase_id)
    if principal.principal_type != "agent" or principal.principal_id != phase.homologator_agent_id:
        raise mission_error(403, "HOMOLOGATOR_ONLY", "Only the phase's homologator reports its homologation")
    body_hash, replay = await _begin(db, principal, payload.idempotency_key, command, body)
    if replay is not None:
        return replay
    _assert_not_terminal(mission)
    _assert_phase_status(phase, ("homologating",))
    from app.api.routes.mission import _active_membership

    membership = await _active_membership(db, mission.project_id, principal.principal_id)
    if membership is None or membership.role != "homologation":
        raise mission_error(409, "HOMOLOGATOR_NOT_MEMBER",
                            "The homologator no longer has an active homologation membership in the mission")
    evidence = [e.strip() for e in payload.evidence if e and e.strip()]
    if payload.verdict == "approved" and not evidence:
        raise mission_error(422, "EVIDENCE_REQUIRED", "An approved homologation lists its evidence")
    now = _now()
    phase.homologation_verdict = payload.verdict
    phase.homologation_summary = payload.summary.strip()
    phase.homologation_evidence = "\n".join(evidence) or None
    phase.homologated_at = now
    homologator = await db.get(Agent, principal.principal_id)
    link = f"/missions/{mission.project_id}"
    demand = None
    if payload.verdict == "approved":
        phase.phase_status = "awaiting_approval"
        _notify(db, f"Fase {phase.position} de {mission_project.name} homologada, aguardando sua aprovação",
                f"{homologator.name if homologator else 'O homologador'} aprovou a fase \"{phase.name}\". "
                f"Resumo: {phase.homologation_summary}\nAbra a missão para aprovar ou devolver: {link}",
                f"mission-phase:{phase.id}:homologated:{now.isoformat()}")
    else:
        phase.phase_status = "returned"
        _notify(db, f"Fase {phase.position} de {mission_project.name} reprovada na homologação",
                f"{homologator.name if homologator else 'O homologador'} reprovou a fase \"{phase.name}\". "
                f"Achados: {phase.homologation_summary}\nA fase voltou ao orquestrador: {link}",
                f"mission-phase:{phase.id}:rejected:{now.isoformat()}")
        demand = await _orchestrator_task(
            db, mission, mission_project, phase,
            f"Fase {phase.position} reprovada na homologação — {phase.name}",
            "\n\n".join([
                f"A homologação da Fase {phase.position} ({phase.name}) da missão {mission_project.name} "
                f"foi reprovada por {homologator.name if homologator else 'o homologador'}.",
                f"Achados:\n{phase.homologation_summary}",
                f"Evidências:\n{phase.homologation_evidence or '(nenhuma)'}",
                "Planeje as correções (novas tarefas ou devolução das tarefas afetadas), execute-as e peça "
                "uma nova homologação com request_phase_homologation.",
            ]),
            from_agent=homologator,
        )
    _audit(db, principal, "homologator", None, mission, "mission_phase_homologation_reported",
           payload.idempotency_key, phase_id=str(phase.id), position=phase.position, verdict=payload.verdict,
           evidence=evidence, demand_id=str(demand.id) if demand else None)
    await db.flush()
    out = await _out(db, mission, phase_id=str(phase.id),
                     demand_id=str(demand.id) if demand else None)
    _finish(db, principal, payload.idempotency_key, command, body_hash, 200, out, phase.id)
    await db.commit()
    if demand is not None:
        wake_scheduled_dispatch()
    return _respond(200, out)


# ---------------------------------------------------------------------------
# Marcelo's decision
# ---------------------------------------------------------------------------
def _assert_marcelo(principal: ActorPrincipal) -> None:
    if principal.principal_type != "user" or not principal.is_admin:
        raise mission_error(403, "PHASE_DECISION_HUMAN_ONLY",
                            "A phase is approved or returned only by Marcelo (an administrator, by JWT)")


@router.post("/{project_id}/phases/{phase_id}:approve", dependencies=WRITE_DEPENDENCIES)
async def approve_phase(
    project_id: uuid.UUID,
    phase_id: uuid.UUID,
    payload: PhaseApproveIn,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db=Depends(get_db),
):
    """Approve a homologated phase. The orchestrator gets a Messages Task:
    the next phase is unlocked, or, after the last one, the mission can go
    to verifying."""
    _assert_marcelo(principal)
    command = "mission.phase.approve"
    body = {"project_id": str(project_id), "phase_id": str(phase_id), **payload.model_dump(mode="json")}
    mission_project, mission = await _load(db, project_id, lock=True)
    body_hash, replay = await _begin(db, principal, payload.idempotency_key, command, body)
    if replay is not None:
        return replay
    phase = await _phase(db, mission, phase_id)
    _assert_phase_status(phase, ("awaiting_approval",), payload.expected_phase_status)
    now = _now()
    phase.phase_status = "approved"
    phase.decided_by = principal.display_name
    phase.decided_at = now
    phase.decision_reason = (payload.reason or "").strip() or None
    following = [p for p in await mission_phases(db, mission.project_id) if p.position > phase.position]
    if following:
        nxt = following[0]
        subject = f"Fase {nxt.position} liberada — {nxt.name}"
        text = (f"Marcelo aprovou a Fase {phase.position} ({phase.name}) da missão {mission_project.name}. "
                f"A Fase {nxt.position} ({nxt.name}) está liberada: despache as tarefas dela.")
    else:
        subject = f"Todas as fases aprovadas — {mission_project.name}"
        text = (f"Marcelo aprovou a Fase {phase.position} ({phase.name}), a última da missão "
                f"{mission_project.name}. A missão pode seguir para verifying quando os critérios estiverem "
                "provados.")
    demand = await _orchestrator_task(db, mission, mission_project, phase, subject, text)
    _audit(db, principal, "admin", None, mission, "mission_phase_approved", payload.idempotency_key,
           phase_id=str(phase.id), position=phase.position, reason=phase.decision_reason,
           demand_id=str(demand.id), last_phase=not following)
    await db.flush()
    out = await _out(db, mission, phase_id=str(phase.id), demand_id=str(demand.id))
    _finish(db, principal, payload.idempotency_key, command, body_hash, 200, out, phase.id)
    await db.commit()
    wake_scheduled_dispatch()
    return _respond(200, out)


@router.post("/{project_id}/phases/{phase_id}:return", dependencies=WRITE_DEPENDENCIES)
async def return_phase(
    project_id: uuid.UUID,
    phase_id: uuid.UUID,
    payload: PhaseReturnIn,
    principal: ActorPrincipal = Depends(get_actor_principal),
    db=Depends(get_db),
):
    """Return a homologated phase with a reason; the orchestrator gets a
    Messages Task with it."""
    _assert_marcelo(principal)
    command = "mission.phase.return"
    body = {"project_id": str(project_id), "phase_id": str(phase_id), **payload.model_dump(mode="json")}
    mission_project, mission = await _load(db, project_id, lock=True)
    body_hash, replay = await _begin(db, principal, payload.idempotency_key, command, body)
    if replay is not None:
        return replay
    phase = await _phase(db, mission, phase_id)
    _assert_phase_status(phase, ("awaiting_approval",), payload.expected_phase_status)
    reason = payload.reason.strip()
    if not reason:
        raise mission_error(422, "REASON_REQUIRED", "Returning a phase requires a reason")
    phase.phase_status = "returned"
    phase.decided_by = principal.display_name
    phase.decided_at = _now()
    phase.decision_reason = reason
    demand = await _orchestrator_task(
        db, mission, mission_project, phase, f"Fase {phase.position} devolvida por Marcelo — {phase.name}",
        f"Marcelo devolveu a Fase {phase.position} ({phase.name}) da missão {mission_project.name}.\n\n"
        f"Motivo:\n{reason}\n\nPlaneje e execute as correções e peça uma nova homologação "
        "(request_phase_homologation).",
    )
    _audit(db, principal, "admin", None, mission, "mission_phase_returned", payload.idempotency_key,
           phase_id=str(phase.id), position=phase.position, reason=reason, demand_id=str(demand.id))
    await db.flush()
    out = await _out(db, mission, phase_id=str(phase.id), demand_id=str(demand.id))
    _finish(db, principal, payload.idempotency_key, command, body_hash, 200, out, phase.id)
    await db.commit()
    wake_scheduled_dispatch()
    return _respond(200, out)


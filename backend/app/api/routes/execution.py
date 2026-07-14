"""Governed ExecutionWave, Work Package and durable CLI runner commands."""
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.execution import (
    DispatchOut, ExecutionRuntimeOut, ExecutionWaveCreate, ExecutionWaveOut,
    ReworkCreate, RunnerOut, WaveDetailOut, WavePreflightOut, WaveTaskOut, WorkPackageCreate,
    WorkPackageOut,
)
from app.core.config import settings
from app.core.deps import ActorPrincipal, authorize_action, get_actor_principal
from app.core.secrets import decrypt_secret
from app.db.base import get_db
from app.db.models.agent import Agent, SubAgent
from app.db.models.backlog import PlanningItem
from app.db.models.execution import (
    ExecutionEvent, ExecutionLease, ExecutionResult, ExecutionRunner, ExecutionWave,
    ExecutionWaveTask, ExecutionWorkPackage,
)
from app.db.models.governance import AuditEvent
from app.db.models.orchestration import AgentRuntimeProfile, ProjectAgentMembership
from app.db.models.pipeline import PipelineStage, ProjectPipeline
from app.db.models.progress import ProgressCheckpoint
from app.db.models.project import ChangeRequest, PlanBaseline, Project, ProjectForgeRouterConfig, ProjectPlan
from app.db.models.task import ProjectTask, TaskAssignment, TaskDependency, TaskExecution

router = APIRouter(prefix="/api/v1", tags=["execution-runtime"])
ACTIVE_EXECUTION_STATES = ("pending", "running", "recovering", "reconciling")


def _canonical(value: dict | list) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _hash(value: dict | list) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


async def _task_project_id(db: AsyncSession, task: ProjectTask) -> uuid.UUID:
    if task.planning_item_id:
        item = await db.get(PlanningItem, task.planning_item_id)
        if item and item.project_id:
            return item.project_id
    if task.change_request_id:
        change = await db.get(ChangeRequest, task.change_request_id)
        if change:
            return change.project_id
    raise HTTPException(409, "Task cannot be resolved to a project")


async def _wave(db: AsyncSession, wave_id: uuid.UUID) -> ExecutionWave:
    wave = await db.get(ExecutionWave, wave_id)
    if not wave:
        raise HTTPException(404, "Execution wave not found")
    return wave


async def _package(db: AsyncSession, package_id: uuid.UUID) -> ExecutionWorkPackage:
    package = await db.get(ExecutionWorkPackage, package_id)
    if not package:
        raise HTTPException(404, "Work package not found")
    return package


async def _audit(db: AsyncSession, entity_type: str, entity_id: uuid.UUID, event: str, principal: ActorPrincipal, payload: dict | None = None) -> None:
    db.add(AuditEvent(entity_type=entity_type, entity_id=entity_id, event_type=event, actor=principal.display_name, payload=payload or {}))


async def _event(db: AsyncSession, execution_id: uuid.UUID, event_type: str, payload: dict, key: str) -> ExecutionEvent:
    existing = (await db.execute(select(ExecutionEvent).where(ExecutionEvent.idempotency_key == key))).scalar_one_or_none()
    if existing:
        return existing
    sequence = int(await db.scalar(select(func.coalesce(func.max(ExecutionEvent.sequence), 0)).where(ExecutionEvent.task_execution_id == execution_id)) or 0) + 1
    event = ExecutionEvent(task_execution_id=execution_id, sequence=sequence, event_type=event_type, payload=payload, idempotency_key=key)
    db.add(event)
    await db.flush()
    return event


async def _checkpoint(db: AsyncSession, principal: ActorPrincipal, wave: ExecutionWave, execution: TaskExecution, checkpoint_type: str, step: str, message: str, key: str, snapshot: dict | None = None) -> None:
    if await db.scalar(select(ProgressCheckpoint.id).where(ProgressCheckpoint.idempotency_key == key)):
        return
    sequence = int(await db.scalar(select(func.coalesce(func.max(ProgressCheckpoint.sequence), 0)).where(ProgressCheckpoint.task_execution_id == execution.id)) or 0) + 1
    db.add(ProgressCheckpoint(
        project_id=wave.project_id, pipeline_stage_id=wave.pipeline_stage_id,
        task_id=execution.task_id, task_execution_id=execution.id, sequence=sequence,
        checkpoint_type=checkpoint_type, step_key=step, step_label=step.replace("_", " ").title(),
        state_snapshot=snapshot or {"execution_status": execution.status}, completed_requirement_keys=[], evidence_refs=[],
        last_confirmed_at=datetime.now(timezone.utc), resume_from_step_key=step if checkpoint_type in {"blocked", "failed", "heartbeat_lost", "paused"} else None,
        message=message, actor_type=principal.principal_type, actor_id=principal.principal_id,
        actor_name=principal.display_name, idempotency_key=key,
    ))


async def _wave_tasks(db: AsyncSession, wave_id: uuid.UUID) -> list[ExecutionWaveTask]:
    return list((await db.execute(select(ExecutionWaveTask).where(ExecutionWaveTask.execution_wave_id == wave_id).order_by(ExecutionWaveTask.release_order))).scalars())


async def _preflight(db: AsyncSession, wave: ExecutionWave) -> dict:
    rows = []
    for link in await _wave_tasks(db, wave.id):
        task = await db.get(ProjectTask, link.task_id)
        reasons: list[str] = []
        if not task:
            reasons.append("task_not_found")
        else:
            if await _task_project_id(db, task) != wave.project_id:
                reasons.append("different_project")
            if task.status not in {"planned", "assigned"}:
                reasons.append(f"task_status_{task.status}")
            if not task.description or not task.description.strip():
                reasons.append("description_missing")
            dependencies = list((await db.execute(select(TaskDependency).where(TaskDependency.task_id == task.id))).scalars())
            for dependency in dependencies:
                predecessor = await db.get(ProjectTask, dependency.depends_on_task_id)
                if not predecessor or predecessor.status not in {"done", "deployed"}:
                    reasons.append(f"dependency_incomplete:{dependency.depends_on_task_id}")
            assignment = (await db.execute(select(TaskAssignment).where(TaskAssignment.task_id == task.id, TaskAssignment.status == "active", TaskAssignment.membership_id.is_not(None)).limit(1))).scalar_one_or_none()
            if not assignment:
                reasons.append("active_assignment_missing")
        rows.append({"task_id": str(link.task_id), "eligible": not reasons, "reasons": reasons})
    snapshot = {"wave_id": str(wave.id), "baseline_id": str(wave.baseline_id), "stage_id": str(wave.pipeline_stage_id) if wave.pipeline_stage_id else None, "tasks": rows}
    snapshot["input_hash"] = _hash(snapshot)
    snapshot["eligible"] = bool(rows) and all(row["eligible"] for row in rows)
    return snapshot


@router.post("/projects/{project_id}/execution-waves", response_model=WaveDetailOut, status_code=201)
async def create_wave(project_id: uuid.UUID, payload: ExecutionWaveCreate, principal: ActorPrincipal = Depends(get_actor_principal), db: AsyncSession = Depends(get_db)) -> WaveDetailOut:
    await authorize_action(db, principal, "planning.execution.manage", project_id=project_id)
    if not await db.get(Project, project_id):
        raise HTTPException(404, "Project not found")
    baseline = await db.get(PlanBaseline, payload.baseline_id)
    if not baseline:
        raise HTTPException(404, "Plan baseline not found")
    plan = await db.get(ProjectPlan, baseline.project_plan_id)
    if not plan or plan.project_id != project_id:
        raise HTTPException(422, "Baseline belongs to another project")
    if payload.pipeline_stage_id:
        stage = await db.get(PipelineStage, payload.pipeline_stage_id)
        pipeline = await db.get(ProjectPipeline, stage.pipeline_id) if stage else None
        if not pipeline or pipeline.project_id != project_id:
            raise HTTPException(422, "Pipeline stage belongs to another project")
    existing = (await db.execute(select(ExecutionWave).where(ExecutionWave.project_id == project_id, ExecutionWave.idempotency_key == payload.idempotency_key))).scalar_one_or_none()
    if existing:
        links = await _wave_tasks(db, existing.id)
        data = ExecutionWaveOut.model_validate(existing).model_dump()
        data["tasks"] = [WaveTaskOut.model_validate(x) for x in links]
        return WaveDetailOut(**data)
    task_ids = list(dict.fromkeys(payload.task_ids))
    wave = ExecutionWave(project_id=project_id, baseline_id=payload.baseline_id, pipeline_stage_id=payload.pipeline_stage_id, name=payload.name, wip_limit=payload.wip_limit, budget_limit=payload.budget_limit, expires_at=payload.expires_at, idempotency_key=payload.idempotency_key)
    db.add(wave); await db.flush()
    for index, task_id in enumerate(task_ids, 1):
        task = await db.get(ProjectTask, task_id)
        if not task or await _task_project_id(db, task) != project_id:
            raise HTTPException(422, f"Task {task_id} does not belong to this project")
        active = (await db.execute(select(ExecutionWaveTask).join(ExecutionWave, ExecutionWave.id == ExecutionWaveTask.execution_wave_id).where(ExecutionWaveTask.task_id == task_id, ExecutionWave.status.in_(["approved", "active", "paused"])))).scalar_one_or_none()
        if active:
            raise HTTPException(409, f"Task {task_id} already belongs to an open wave")
        db.add(ExecutionWaveTask(execution_wave_id=wave.id, task_id=task_id, release_order=index))
    await _audit(db, "execution_wave", wave.id, "execution_wave_created", principal, {"task_count": len(task_ids)})
    await db.commit(); await db.refresh(wave)
    links = await _wave_tasks(db, wave.id)
    data = ExecutionWaveOut.model_validate(wave).model_dump(); data["tasks"] = [WaveTaskOut.model_validate(x) for x in links]
    return WaveDetailOut(**data)


@router.get("/projects/{project_id}/execution-waves", response_model=list[ExecutionWaveOut])
async def list_waves(project_id: uuid.UUID, principal: ActorPrincipal = Depends(get_actor_principal), db: AsyncSession = Depends(get_db)) -> list[ExecutionWave]:
    await authorize_action(db, principal, "planning.execution.view", project_id=project_id)
    return list((await db.execute(select(ExecutionWave).where(ExecutionWave.project_id == project_id).order_by(ExecutionWave.created_at.desc()))).scalars())


@router.get("/execution-waves/{wave_id}", response_model=WaveDetailOut)
async def get_wave(wave_id: uuid.UUID, principal: ActorPrincipal = Depends(get_actor_principal), db: AsyncSession = Depends(get_db)) -> WaveDetailOut:
    wave = await _wave(db, wave_id); await authorize_action(db, principal, "planning.execution.view", project_id=wave.project_id)
    data = ExecutionWaveOut.model_validate(wave).model_dump(); data["tasks"] = [WaveTaskOut.model_validate(x) for x in await _wave_tasks(db, wave.id)]
    return WaveDetailOut(**data)


@router.post("/execution-waves/{wave_id}:preflight", response_model=WavePreflightOut)
async def preflight_wave(wave_id: uuid.UUID, principal: ActorPrincipal = Depends(get_actor_principal), db: AsyncSession = Depends(get_db)) -> WavePreflightOut:
    wave = await _wave(db, wave_id); await authorize_action(db, principal, "planning.execution.manage", project_id=wave.project_id)
    if wave.status not in {"draft", "approved"}:
        raise HTTPException(409, "Only draft or approved waves can be preflighted")
    result = await _preflight(db, wave); wave.preflight_snapshot = result; wave.preflight_hash = result["input_hash"]
    await _audit(db, "execution_wave", wave.id, "execution_wave_preflighted", principal, {"eligible": result["eligible"], "input_hash": result["input_hash"]})
    await db.commit()
    return WavePreflightOut(wave_id=wave.id, eligible=result["eligible"], input_hash=result["input_hash"], tasks=result["tasks"])


async def _transition_wave(db: AsyncSession, wave: ExecutionWave, principal: ActorPrincipal, target: str) -> None:
    allowed = {"approved": {"draft"}, "active": {"approved", "paused"}, "paused": {"active"}, "cancelled": {"draft", "approved", "active", "paused"}}
    if wave.status not in allowed[target]:
        raise HTTPException(409, f"Cannot transition wave from {wave.status} to {target}")
    wave.status = target
    now = datetime.now(timezone.utc)
    if target == "active": wave.starts_at = wave.starts_at or now; wave.paused_at = None
    if target == "paused": wave.paused_at = now
    await _audit(db, "execution_wave", wave.id, f"execution_wave_{target}", principal)


@router.post("/execution-waves/{wave_id}:approve", response_model=ExecutionWaveOut)
async def approve_wave(wave_id: uuid.UUID, principal: ActorPrincipal = Depends(get_actor_principal), db: AsyncSession = Depends(get_db)) -> ExecutionWave:
    wave = await _wave(db, wave_id); source, delegation = await authorize_action(db, principal, "planning.execution.release", project_id=wave.project_id, action_cost=float(wave.budget_limit) if wave.budget_limit is not None else None)
    result = await _preflight(db, wave)
    if not result["eligible"]: raise HTTPException(409, {"code": "wave_preflight_failed", "tasks": result["tasks"]})
    wave.preflight_snapshot = result; wave.preflight_hash = result["input_hash"]
    await _transition_wave(db, wave, principal, "approved")
    wave.authorized_by_type = principal.principal_type; wave.authorized_by_id = principal.principal_id
    wave.delegation_id = delegation.id if delegation else None
    await db.commit(); await db.refresh(wave); return wave


@router.post("/execution-waves/{wave_id}:activate", response_model=ExecutionWaveOut)
async def activate_wave(wave_id: uuid.UUID, principal: ActorPrincipal = Depends(get_actor_principal), db: AsyncSession = Depends(get_db)) -> ExecutionWave:
    wave = await _wave(db, wave_id); await authorize_action(db, principal, "planning.execution.manage", project_id=wave.project_id)
    result = await _preflight(db, wave)
    if wave.preflight_hash != result["input_hash"] or not result["eligible"]: raise HTTPException(409, "Preflight is stale or no longer eligible")
    await _transition_wave(db, wave, principal, "active")
    now = datetime.now(timezone.utc)
    for link in await _wave_tasks(db, wave.id):
        task = await db.get(ProjectTask, link.task_id); task.status = "ready"; link.released_at = now
    await db.commit(); await db.refresh(wave); return wave


@router.post("/execution-waves/{wave_id}:pause", response_model=ExecutionWaveOut)
async def pause_wave(wave_id: uuid.UUID, principal: ActorPrincipal = Depends(get_actor_principal), db: AsyncSession = Depends(get_db)) -> ExecutionWave:
    wave = await _wave(db, wave_id); await authorize_action(db, principal, "planning.execution.manage", project_id=wave.project_id)
    await _transition_wave(db, wave, principal, "paused"); await db.commit(); await db.refresh(wave); return wave


@router.post("/execution-waves/{wave_id}:resume", response_model=ExecutionWaveOut)
async def resume_wave(wave_id: uuid.UUID, principal: ActorPrincipal = Depends(get_actor_principal), db: AsyncSession = Depends(get_db)) -> ExecutionWave:
    wave = await _wave(db, wave_id); await authorize_action(db, principal, "planning.execution.manage", project_id=wave.project_id)
    await _transition_wave(db, wave, principal, "active"); await db.commit(); await db.refresh(wave); return wave


@router.post("/execution-waves/{wave_id}:complete", response_model=ExecutionWaveOut)
async def complete_wave(wave_id: uuid.UUID, principal: ActorPrincipal = Depends(get_actor_principal), db: AsyncSession = Depends(get_db)) -> ExecutionWave:
    wave = await _wave(db, wave_id); await authorize_action(db, principal, "planning.execution.manage", project_id=wave.project_id)
    if wave.status not in {"active", "paused"}: raise HTTPException(409, "Wave is not active")
    tasks = [await db.get(ProjectTask, link.task_id) for link in await _wave_tasks(db, wave.id)]
    if any(task.status not in {"done", "deployed", "cancelled"} for task in tasks): raise HTTPException(409, "All wave tasks must be terminal")
    wave.status = "completed"; wave.completed_at = datetime.now(timezone.utc)
    await _audit(db, "execution_wave", wave.id, "execution_wave_completed", principal); await db.commit(); await db.refresh(wave); return wave


def _safe_paths(values: list[str]) -> bool:
    return all(value and not PurePosixPath(value).is_absolute() and ".." not in PurePosixPath(value).parts for value in values)


@router.post("/execution-waves/{wave_id}/tasks/{task_id}/work-packages", response_model=WorkPackageOut, status_code=201)
async def build_work_package(wave_id: uuid.UUID, task_id: uuid.UUID, payload: WorkPackageCreate, principal: ActorPrincipal = Depends(get_actor_principal), db: AsyncSession = Depends(get_db)) -> ExecutionWorkPackage:
    wave = await _wave(db, wave_id); await authorize_action(db, principal, "planning.execution.manage", project_id=wave.project_id)
    if wave.status != "active": raise HTTPException(409, "Execution wave must be active")
    if not await db.scalar(select(ExecutionWaveTask.id).where(ExecutionWaveTask.execution_wave_id == wave.id, ExecutionWaveTask.task_id == task_id)): raise HTTPException(404, "Task is not part of this wave")
    task = await db.get(ProjectTask, task_id)
    if not task or task.status != "ready": raise HTTPException(409, "Task must be ready")
    assignment = await db.get(TaskAssignment, payload.assignment_id); profile = await db.get(AgentRuntimeProfile, payload.runtime_profile_id)
    if not assignment or assignment.task_id != task_id or assignment.status != "active" or not assignment.membership_id: raise HTTPException(422, "Active project assignment is required")
    membership = await db.get(ProjectAgentMembership, assignment.membership_id)
    if not membership or membership.project_id != wave.project_id or membership.status != "active": raise HTTPException(422, "Assignment membership is not active")
    if not profile or not profile.is_active or not ((profile.agent_id and profile.agent_id == membership.agent_id) or (profile.sub_agent_id and profile.sub_agent_id == membership.sub_agent_id)): raise HTTPException(422, "Runtime profile does not belong to assigned member")
    if not _safe_paths(payload.allowed_paths + payload.denied_paths): raise HTTPException(422, "Paths must be safe workspace-relative paths")
    existing = (await db.execute(select(ExecutionWorkPackage).where(ExecutionWorkPackage.idempotency_key == payload.idempotency_key))).scalar_one_or_none()
    if existing: return existing
    project = await db.get(Project, wave.project_id)
    runtime = "agy" if profile.runtime_type == "antigravity" else profile.runtime_type
    package_payload = {
        "contract_version": "forge-engineering-work-package/v1", "product": {},
        "project": {"id": str(project.id), "name": project.name, "working_directory_path": project.working_directory_path},
        "baseline_id": str(wave.baseline_id), "execution_wave_id": str(wave.id), "pipeline_stage_id": str(wave.pipeline_stage_id) if wave.pipeline_stage_id else None,
        "task": {"id": str(task.id), "title": task.title, "description": task.description, "priority": task.priority, "acceptance_criteria": payload.acceptance_criteria, "definition_of_done": payload.definition_of_done},
        "assignment": {"id": str(assignment.id), "membership_id": str(membership.id)},
        "runtime": {"type": runtime, "profile_id": str(profile.id), "model_ref": profile.model_ref, "routing_group": profile.routing_group},
        "constraints": {"allowed_paths": payload.allowed_paths, "denied_paths": payload.denied_paths, "max_seconds": payload.max_seconds},
        "inputs": {"artifact_ids": [str(x) for x in payload.input_artifact_ids]},
        "verification": {"commands": payload.verification_commands}, "prompt_addendum": payload.prompt_addendum,
    }
    errors = []
    if not project.working_directory_path: errors.append("project_working_directory_missing")
    if not payload.acceptance_criteria: errors.append("acceptance_criteria_missing")
    if not payload.definition_of_done: errors.append("definition_of_done_missing")
    if not payload.allowed_paths: errors.append("allowed_paths_missing")
    revision = int(await db.scalar(select(func.coalesce(func.max(ExecutionWorkPackage.revision), 0)).where(ExecutionWorkPackage.task_id == task_id)) or 0) + 1
    package = ExecutionWorkPackage(task_id=task_id, assignment_id=assignment.id, runtime_profile_id=profile.id, execution_wave_id=wave.id, baseline_id=wave.baseline_id, revision=revision, contract_version="forge-engineering-work-package/v1", payload=package_payload, payload_hash=_hash(package_payload), idempotency_key=payload.idempotency_key, status="validated" if not errors else "draft", validation_errors=errors)
    db.add(package); await db.flush(); await _audit(db, "execution_work_package", package.id, "work_package_built", principal, {"validation_errors": errors}); await db.commit(); await db.refresh(package); return package


@router.get("/execution-waves/{wave_id}/work-packages", response_model=list[WorkPackageOut])
async def list_work_packages(wave_id: uuid.UUID, principal: ActorPrincipal = Depends(get_actor_principal), db: AsyncSession = Depends(get_db)) -> list[ExecutionWorkPackage]:
    wave = await _wave(db, wave_id); await authorize_action(db, principal, "planning.execution.view", project_id=wave.project_id)
    return list((await db.execute(select(ExecutionWorkPackage).where(ExecutionWorkPackage.execution_wave_id == wave.id).order_by(ExecutionWorkPackage.created_at.desc()))).scalars())


@router.post("/work-packages/{package_id}:issue", response_model=WorkPackageOut)
async def issue_work_package(package_id: uuid.UUID, principal: ActorPrincipal = Depends(get_actor_principal), db: AsyncSession = Depends(get_db)) -> ExecutionWorkPackage:
    package = await _package(db, package_id); wave = await _wave(db, package.execution_wave_id); await authorize_action(db, principal, "planning.execution.dispatch", project_id=wave.project_id)
    if wave.status != "active" or package.status != "validated" or package.validation_errors: raise HTTPException(409, "Only a valid package in an active wave can be issued")
    if package.payload_hash != _hash(package.payload): raise HTTPException(409, "Work package payload hash mismatch")
    package.status = "issued"; package.issued_at = datetime.now(timezone.utc)
    await _audit(db, "execution_work_package", package.id, "work_package_issued", principal); await db.commit(); await db.refresh(package); return package


@router.post("/executions/{execution_id}:request-rework", response_model=WorkPackageOut, status_code=201)
async def request_rework(execution_id: uuid.UUID, payload: ReworkCreate, principal: ActorPrincipal = Depends(get_actor_principal), db: AsyncSession = Depends(get_db)) -> ExecutionWorkPackage:
    execution = await db.get(TaskExecution, execution_id)
    if not execution or not execution.work_package_id:
        raise HTTPException(404, "Governed execution not found")
    previous = await _package(db, execution.work_package_id); wave = await _wave(db, previous.execution_wave_id)
    await authorize_action(db, principal, "planning.execution.manage", project_id=wave.project_id)
    if execution.status not in {"completed", "failed", "blocked"}:
        raise HTTPException(409, "Execution must be terminal before rework")
    existing = (await db.execute(select(ExecutionWorkPackage).where(ExecutionWorkPackage.idempotency_key == payload.idempotency_key))).scalar_one_or_none()
    if existing:
        return existing
    package_payload = json.loads(json.dumps(previous.payload))
    package_payload["rework"] = {"parent_execution_id": str(execution.id), "feedback": payload.feedback}
    revision = int(await db.scalar(select(func.coalesce(func.max(ExecutionWorkPackage.revision), 0)).where(ExecutionWorkPackage.task_id == previous.task_id)) or 0) + 1
    package = ExecutionWorkPackage(task_id=previous.task_id, assignment_id=previous.assignment_id, runtime_profile_id=previous.runtime_profile_id, execution_wave_id=previous.execution_wave_id, baseline_id=previous.baseline_id, revision=revision, contract_version=previous.contract_version, payload=package_payload, payload_hash=_hash(package_payload), idempotency_key=payload.idempotency_key, status="validated", validation_errors=[])
    db.add(package); await db.flush(); previous.status = "superseded"
    task = await db.get(ProjectTask, previous.task_id); task.status = "ready"
    await _audit(db, "execution_work_package", package.id, "work_package_rework_created", principal, {"parent_execution_id": str(execution.id)}); await db.commit(); await db.refresh(package); return package


async def _runner(db: AsyncSession) -> ExecutionRunner:
    runner = (await db.execute(select(ExecutionRunner).where(ExecutionRunner.runner_key == "host-bridge-primary"))).scalar_one_or_none()
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{settings.CHAT_BRIDGE_URL}/v1/agent-runs/health", headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN}); response.raise_for_status(); health = response.json()
        status = "online"
    except (httpx.HTTPError, ValueError):
        health = {}; status = "offline"
    if not runner:
        runner = ExecutionRunner(runner_key="host-bridge-primary", status=status, adapter_version=health.get("adapter_version"), capabilities=health.get("capabilities", {})); db.add(runner); await db.flush()
    else:
        runner.status = "disabled" if runner.disabled else status; runner.adapter_version = health.get("adapter_version", runner.adapter_version); runner.capabilities = health.get("capabilities", runner.capabilities)
    runner.last_heartbeat_at = datetime.now(timezone.utc) if status == "online" else runner.last_heartbeat_at
    return runner


def _prompt(package: ExecutionWorkPackage) -> str:
    payload = package.payload
    return "Execute this immutable ForgeHub Work Package. Read AGENTS.md first. Do not expand scope, deploy, or approve gates.\n\n" + json.dumps(payload, indent=2) + "\n\nReturn a JSON object matching forge-engineering-result/v1 with status, summary, changed_files, artifacts, verification, decisions_proposed, scope_impacts_discovered, residual_risks and follow_up_items."


@router.post("/work-packages/{package_id}:dispatch", response_model=DispatchOut, status_code=202)
async def dispatch_package(package_id: uuid.UUID, principal: ActorPrincipal = Depends(get_actor_principal), db: AsyncSession = Depends(get_db)) -> DispatchOut:
    package = await _package(db, package_id); wave = await _wave(db, package.execution_wave_id); await authorize_action(db, principal, "planning.execution.dispatch", project_id=wave.project_id)
    if package.status != "issued" or wave.status != "active": raise HTTPException(409, "Issued package and active wave are required")
    running = int(await db.scalar(select(func.count(TaskExecution.id)).join(ExecutionWorkPackage, ExecutionWorkPackage.id == TaskExecution.work_package_id).where(ExecutionWorkPackage.execution_wave_id == wave.id, TaskExecution.status.in_(ACTIVE_EXECUTION_STATES))) or 0)
    if running >= wave.wip_limit: raise HTTPException(409, "Wave WIP limit reached")
    if await db.scalar(select(TaskExecution.id).where(TaskExecution.work_package_id == package.id, TaskExecution.status.in_(ACTIVE_EXECUTION_STATES))): raise HTTPException(409, "Work package already has an active execution")
    assignment = await db.get(TaskAssignment, package.assignment_id); membership = await db.get(ProjectAgentMembership, assignment.membership_id); profile = await db.get(AgentRuntimeProfile, package.runtime_profile_id)
    credential_agent_id = membership.agent_id
    if credential_agent_id is None:
        sub = await db.get(SubAgent, membership.sub_agent_id); credential_agent_id = sub.agent_id
    agent = await db.get(Agent, credential_agent_id)
    if not agent or not agent.forgerouter_api_key_encrypted: raise HTTPException(409, "Assigned agent has no ForgeRouter credential")
    api_key = decrypt_secret(agent.forgerouter_api_key_encrypted)
    config = (await db.execute(select(ProjectForgeRouterConfig).where(ProjectForgeRouterConfig.project_id == wave.project_id))).scalar_one_or_none()
    config_field = "antigravity_enabled" if profile.runtime_type in {"antigravity", "agy"} else f"{profile.runtime_type}_enabled"
    if not config or not getattr(config, config_field, False): raise HTTPException(409, "Runtime is not enabled for this project")
    runner = await _runner(db)
    if runner.status != "online" or runner.disabled: raise HTTPException(503, "No healthy execution runner is available")
    runtime_key = "agy" if profile.runtime_type == "antigravity" else profile.runtime_type
    adapter = (runner.capabilities.get("adapters") or {}).get(runtime_key, {})
    if not adapter.get("available"):
        raise HTTPException(503, f"The {runtime_key} adapter is not available on this runner")
    max_attempt = int(await db.scalar(select(func.coalesce(func.max(TaskExecution.attempt_number), 0)).where(TaskExecution.task_id == package.task_id)) or 0)
    execution = TaskExecution(task_id=package.task_id, assignment_id=package.assignment_id, runtime_profile_id=package.runtime_profile_id, work_package_id=package.id, attempt_number=max_attempt + 1, executor_type="sub_agent" if membership.sub_agent_id else "agent", runtime_type="agy" if profile.runtime_type == "antigravity" else profile.runtime_type, status="pending")
    db.add(execution); await db.flush()
    now = datetime.now(timezone.utc); lease = ExecutionLease(work_package_id=package.id, runner_id=runner.id, task_execution_id=execution.id, status="claimed", leased_at=now, expires_at=now + timedelta(seconds=int(package.payload["constraints"]["max_seconds"]) + 120), heartbeat_at=now)
    db.add(lease); await db.flush(); await _event(db, execution.id, "claimed", {"lease_id": str(lease.id)}, f"{execution.id}:claimed"); await db.commit()
    project = await db.get(Project, wave.project_id)
    body = {"run_id": str(execution.id), "runtime_type": execution.runtime_type, "project_path": project.working_directory_path, "prompt": _prompt(package), "model_ref": profile.model_ref, "routing_group": profile.routing_group, "api_key": api_key, "mode": "execute", "max_seconds": package.payload["constraints"]["max_seconds"], "max_budget_usd": float(profile.max_budget_usd) if profile.max_budget_usd is not None else None, "work_package_hash": package.payload_hash}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(f"{settings.CHAT_BRIDGE_URL}/v1/agent-runs", json=body, headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN}); response.raise_for_status(); run = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        execution.status = "failed"; execution.finished_at = datetime.now(timezone.utc); execution.outcome_summary = f"Runner dispatch failed: {exc}"; lease.status = "released"; lease.released_at = datetime.now(timezone.utc)
        await _event(db, execution.id, "failed", {"error": str(exc)}, f"{execution.id}:dispatch-failed"); await _checkpoint(db, principal, wave, execution, "failed", "dispatch", str(exc), f"runner:{execution.id}:dispatch-failed"); await db.commit()
        raise HTTPException(502, f"CLI runner dispatch failed: {exc}") from exc
    execution.status = "running"; execution.started_at = datetime.now(timezone.utc); execution.runtime_session_ref = run["run_id"]; execution.process_ref = str(run.get("pid") or run["run_id"]); execution.adapter_version = runner.adapter_version
    lease.status = "running"; task = await db.get(ProjectTask, execution.task_id); task.status = "in_progress"
    await _event(db, execution.id, "started", {"run_id": run["run_id"], "runtime": execution.runtime_type}, f"{execution.id}:started"); await _checkpoint(db, principal, wave, execution, "started", "cli_execution", "CLI process started", f"runner:{execution.id}:started"); await _audit(db, "task_execution", execution.id, "execution_dispatched", principal, {"work_package_id": str(package.id), "runtime_type": execution.runtime_type}); await db.commit()
    return DispatchOut(execution_id=execution.id, work_package_id=package.id, lease_id=lease.id, run_id=run["run_id"], status=execution.status, runtime_type=execution.runtime_type)


def _contract_candidate(value) -> dict | None:
    if isinstance(value, dict) and "status" in value and "summary" in value:
        return value
    if isinstance(value, dict):
        for key in ("result", "text", "content", "message", "output"):
            nested = value.get(key)
            candidate = _contract_candidate(nested)
            if candidate:
                return candidate
    if isinstance(value, list):
        for item in reversed(value):
            candidate = _contract_candidate(item)
            if candidate:
                return candidate
    if isinstance(value, str):
        text = value.strip().removeprefix("```json").removesuffix("```").strip()
        try:
            return _contract_candidate(json.loads(text))
        except json.JSONDecodeError:
            start, end = text.rfind("{"), text.rfind("}")
            while start >= 0 and end > start:
                try:
                    candidate = _contract_candidate(json.loads(text[start:end + 1]))
                    if candidate:
                        return candidate
                except json.JSONDecodeError:
                    pass
                start = text.rfind("{", 0, start)
    return None


def _result_payload(run: dict) -> tuple[dict, list[str]]:
    output = (run.get("output") or "").strip(); errors = []
    parsed = _contract_candidate(output)
    for line in reversed(output.splitlines()):
        if parsed is not None:
            break
        try:
            candidate = json.loads(line)
            parsed = _contract_candidate(candidate)
        except json.JSONDecodeError:
            continue
    if parsed is None:
        errors.append("structured_result_missing")
        parsed = {"status": "completed" if run.get("status") == "completed" else "failed", "summary": output[-4000:] or run.get("error") or "CLI run ended", "changed_files": [], "artifacts": [], "verification": [], "decisions_proposed": [], "scope_impacts_discovered": [], "residual_risks": [], "follow_up_items": []}
    required = {"status", "summary", "changed_files", "artifacts", "verification", "residual_risks", "follow_up_items"}
    errors.extend(f"missing:{key}" for key in sorted(required - set(parsed)))
    if parsed.get("status") not in {"completed", "failed", "blocked"}:
        errors.append("invalid:status")
    for verification in parsed.get("verification", []):
        if verification.get("status") not in {"passed", "success", "skipped"}:
            errors.append(f"verification_failed:{verification.get('command_id') or verification.get('command') or 'unknown'}")
    return parsed, errors


@router.post("/executions/{execution_id}:refresh-runtime", response_model=ExecutionRuntimeOut)
async def refresh_runtime(execution_id: uuid.UUID, principal: ActorPrincipal = Depends(get_actor_principal), db: AsyncSession = Depends(get_db)) -> ExecutionRuntimeOut:
    execution = await db.get(TaskExecution, execution_id)
    if not execution or not execution.work_package_id: raise HTTPException(404, "Governed execution not found")
    package = await _package(db, execution.work_package_id); wave = await _wave(db, package.execution_wave_id); await authorize_action(db, principal, "planning.execution.view", project_id=wave.project_id)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(f"{settings.CHAT_BRIDGE_URL}/v1/agent-runs/{execution.runtime_session_ref}", headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN}); response.raise_for_status(); run = response.json()
    except httpx.HTTPError as exc:
        execution.status = "reconciling"; await _event(db, execution.id, "heartbeat_lost", {"error": str(exc)}, f"{execution.id}:heartbeat-lost"); await _checkpoint(db, principal, wave, execution, "heartbeat_lost", "runtime_reconcile", str(exc), f"runner:{execution.id}:heartbeat-lost"); await db.commit(); raise HTTPException(502, "Runner unavailable; execution marked for reconciliation") from exc
    lease = (await db.execute(select(ExecutionLease).where(ExecutionLease.task_execution_id == execution.id))).scalar_one_or_none()
    if lease: lease.heartbeat_at = datetime.now(timezone.utc)
    if run.get("status") == "running":
        await _event(db, execution.id, "heartbeat", {"pid": run.get("pid")}, f"{execution.id}:heartbeat:{run.get('heartbeat_at') or run.get('updated_at')}")
        await db.commit(); return ExecutionRuntimeOut(execution_id=execution.id, status=execution.status, run=run)
    payload, errors = _result_payload(run); existing = (await db.execute(select(ExecutionResult).where(ExecutionResult.task_execution_id == execution.id))).scalar_one_or_none()
    if not existing:
        existing = ExecutionResult(task_execution_id=execution.id, contract_version="forge-engineering-result/v1", result_payload=payload, result_hash=_hash(payload), validation_errors=errors, is_stale=package.payload_hash != _hash(package.payload)); db.add(existing)
    terminal = "completed" if run.get("status") == "completed" and not errors and not existing.is_stale else "failed"
    execution.status = terminal; execution.finished_at = datetime.now(timezone.utc); execution.exit_code = run.get("exit_code"); execution.outcome_summary = str(payload.get("summary", ""))[-4000:]; execution.evidence_ref = f"forgehub://execution-results/{execution.id}"
    if lease: lease.status = "released"; lease.released_at = datetime.now(timezone.utc)
    await _event(db, execution.id, terminal, {"result_hash": existing.result_hash, "validation_errors": errors}, f"{execution.id}:{terminal}"); await _checkpoint(db, principal, wave, execution, "completed" if terminal == "completed" else "failed", "result_ingested", execution.outcome_summary or terminal, f"runner:{execution.id}:{terminal}", {"result_hash": existing.result_hash, "validation_errors": errors})
    await db.commit(); return ExecutionRuntimeOut(execution_id=execution.id, status=execution.status, run=run, result=payload)


@router.post("/executions/{execution_id}:cancel-runtime", response_model=ExecutionRuntimeOut)
async def cancel_runtime(execution_id: uuid.UUID, principal: ActorPrincipal = Depends(get_actor_principal), db: AsyncSession = Depends(get_db)) -> ExecutionRuntimeOut:
    execution = await db.get(TaskExecution, execution_id)
    if not execution or not execution.work_package_id: raise HTTPException(404, "Governed execution not found")
    package = await _package(db, execution.work_package_id); wave = await _wave(db, package.execution_wave_id); await authorize_action(db, principal, "planning.execution.cancel", project_id=wave.project_id)
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(f"{settings.CHAT_BRIDGE_URL}/v1/agent-runs/{execution.runtime_session_ref}/cancel", headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN}); response.raise_for_status(); run = response.json()
    execution.status = "failed"; execution.finished_at = datetime.now(timezone.utc); execution.outcome_summary = "Execution cancelled by authorized operator"
    lease = (await db.execute(select(ExecutionLease).where(ExecutionLease.task_execution_id == execution.id))).scalar_one_or_none()
    if lease: lease.status = "cancelled"; lease.released_at = datetime.now(timezone.utc)
    await _event(db, execution.id, "cancelled", {}, f"{execution.id}:cancelled"); await _checkpoint(db, principal, wave, execution, "failed", "cancelled", execution.outcome_summary, f"runner:{execution.id}:cancelled"); await db.commit()
    return ExecutionRuntimeOut(execution_id=execution.id, status=execution.status, run=run)


@router.get("/execution-runners", response_model=list[RunnerOut])
async def list_runners(project_id: uuid.UUID, principal: ActorPrincipal = Depends(get_actor_principal), db: AsyncSession = Depends(get_db)) -> list[ExecutionRunner]:
    await authorize_action(db, principal, "planning.execution.view", project_id=project_id)
    await _runner(db); await db.commit()
    return list((await db.execute(select(ExecutionRunner).order_by(ExecutionRunner.runner_key))).scalars())

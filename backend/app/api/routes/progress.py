"""Governed progress checkpoints, recovery commands, and stage completion."""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.schemas.progress import (
    CompleteStageIn, CompleteStageOut, ExecutionActionIn, ExecutionActionOut,
    ProgressCheckpointCreate, ProgressCheckpointOut, ProjectProgressOut,
    StageCompletionAssessmentOut,
)
from app.core.deps import ActorPrincipal, authorize_action, get_actor_principal
from app.core.governed_approval import canonical_hash
from app.db.base import AsyncSessionLocal, get_db
from app.db.models.backlog import PlanningItem
from app.db.models.governance import AuditEvent
from app.db.models.notification import Notification
from app.db.models.pipeline import PipelineStage, ProjectPipeline
from app.db.models.progress import ProgressCheckpoint, StageCompletionAssessment
from app.db.models.project import ChangeRequest, PlanBaseline, Project, ProjectPlan
from app.db.models.task import ProjectTask, TaskExecution

router = APIRouter(tags=["progress"])
logger = logging.getLogger(__name__)
STOP_TYPES = {"blocked", "failed", "paused", "heartbeat_lost"}
TERMINAL_STAGE_STATUSES = {"completed", "skipped"}


async def _stage_or_404(db: AsyncSession, stage_id: uuid.UUID) -> PipelineStage:
    stage = (await db.execute(
        select(PipelineStage).where(PipelineStage.id == stage_id).options(
            selectinload(PipelineStage.required_artifacts),
            selectinload(PipelineStage.gates),
            selectinload(PipelineStage.dependencies),
        )
    )).scalar_one_or_none()
    if stage is None:
        raise HTTPException(404, "Stage not found")
    return stage


async def _stage_project_id(db: AsyncSession, stage: PipelineStage) -> uuid.UUID:
    pipeline = await db.get(ProjectPipeline, stage.pipeline_id)
    if pipeline is None:
        raise HTTPException(409, "Stage pipeline is missing")
    return pipeline.project_id


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


async def _execution_context(
    db: AsyncSession, execution_id: uuid.UUID
) -> tuple[TaskExecution, ProjectTask, uuid.UUID]:
    execution = await db.get(TaskExecution, execution_id)
    if execution is None:
        raise HTTPException(404, "Execution not found")
    task = await db.get(ProjectTask, execution.task_id)
    if task is None:
        raise HTTPException(409, "Execution task is missing")
    return execution, task, await _task_project_id(db, task)


async def _latest_checkpoint(
    db: AsyncSession, *, stage_id: uuid.UUID | None = None, execution_id: uuid.UUID | None = None
) -> ProgressCheckpoint | None:
    stmt = select(ProgressCheckpoint)
    if execution_id:
        stmt = stmt.where(ProgressCheckpoint.task_execution_id == execution_id)
    elif stage_id:
        stmt = stmt.where(ProgressCheckpoint.pipeline_stage_id == stage_id)
    else:
        return None
    return (await db.execute(stmt.order_by(
        ProgressCheckpoint.last_confirmed_at.desc(), ProgressCheckpoint.sequence.desc()
    ).limit(1))).scalar_one_or_none()


async def _next_sequence(
    db: AsyncSession, *, execution_id: uuid.UUID | None, stage_id: uuid.UUID | None
) -> int:
    stmt = select(func.coalesce(func.max(ProgressCheckpoint.sequence), 0))
    if execution_id:
        stmt = stmt.where(ProgressCheckpoint.task_execution_id == execution_id)
    else:
        stmt = stmt.where(
            ProgressCheckpoint.task_execution_id.is_(None),
            ProgressCheckpoint.pipeline_stage_id == stage_id,
        )
    return int((await db.execute(stmt)).scalar_one()) + 1


async def _record_checkpoint(
    db: AsyncSession,
    principal: ActorPrincipal,
    project_id: uuid.UUID,
    payload: ProgressCheckpointCreate,
    task: ProjectTask | None = None,
    execution: TaskExecution | None = None,
) -> ProgressCheckpoint:
    existing = (await db.execute(select(ProgressCheckpoint).where(
        ProgressCheckpoint.idempotency_key == payload.idempotency_key
    ))).scalar_one_or_none()
    if existing:
        if execution and existing.task_execution_id != execution.id:
            raise HTTPException(409, "Idempotency key belongs to another execution")
        return existing
    if payload.pipeline_stage_id:
        stage = await _stage_or_404(db, payload.pipeline_stage_id)
        if await _stage_project_id(db, stage) != project_id:
            raise HTTPException(422, "pipeline_stage_id belongs to another project")
    sequence = await _next_sequence(
        db,
        execution_id=execution.id if execution else None,
        stage_id=payload.pipeline_stage_id,
    )
    checkpoint_data = payload.model_dump(exclude={"pipeline_stage_id"})
    checkpoint = ProgressCheckpoint(
        project_id=project_id,
        pipeline_stage_id=payload.pipeline_stage_id,
        task_id=task.id if task else None,
        task_execution_id=execution.id if execution else None,
        sequence=sequence,
        actor_type=principal.principal_type,
        actor_id=principal.principal_id,
        actor_name=principal.display_name,
        last_confirmed_at=datetime.now(timezone.utc),
        **checkpoint_data,
    )
    db.add(checkpoint)
    await db.flush()
    db.add(AuditEvent(
        entity_type="progress_checkpoint", entity_id=checkpoint.id,
        event_type=f"checkpoint_{checkpoint.checkpoint_type}", actor=principal.display_name,
        payload={
            "project_id": str(project_id),
            "pipeline_stage_id": str(checkpoint.pipeline_stage_id) if checkpoint.pipeline_stage_id else None,
            "task_execution_id": str(checkpoint.task_execution_id) if checkpoint.task_execution_id else None,
            "step_key": checkpoint.step_key,
        },
    ))
    return checkpoint


async def _notify_checkpoint(checkpoint_id: uuid.UUID, checkpoint_type: str, message: str | None) -> None:
    if checkpoint_type not in STOP_TYPES | {"resumed"}:
        return
    try:
        async with AsyncSessionLocal() as db:
            key = f"progress:{checkpoint_type}:{checkpoint_id}"
            if (await db.execute(select(Notification.id).where(Notification.event_key == key))).scalar_one_or_none():
                return
            severity = "success" if checkpoint_type == "resumed" else "warning"
            db.add(Notification(
                source="system", severity=severity,
                title=f"Execution {checkpoint_type.replace('_', ' ')}",
                message=message or f"Progress checkpoint {checkpoint_id}", summary=None,
                event_key=key, occurred_at=datetime.now(timezone.utc),
            ))
            await db.commit()
    except Exception:
        logger.exception("Progress notification failed for checkpoint %s", checkpoint_id)


async def _stage_inputs(db: AsyncSession, stage: PipelineStage) -> tuple[dict, list, list, list]:
    requirements: list[dict] = []
    evidence: list[str] = []
    blockers: list[dict] = []
    for dep in sorted(stage.dependencies, key=lambda value: str(value.depends_on_stage_id)):
        dependency = await db.get(PipelineStage, dep.depends_on_stage_id)
        passed = dependency is not None and dependency.status in TERMINAL_STAGE_STATUSES
        requirements.append({
            "key": f"dependency:{dep.depends_on_stage_id}", "kind": "dependency",
            "label": dependency.name if dependency else str(dep.depends_on_stage_id),
            "passed": passed, "value": dependency.status if dependency else "missing",
        })
    for artifact in sorted(stage.required_artifacts, key=lambda value: str(value.id)):
        if not artifact.is_mandatory:
            continue
        passed = artifact.is_fulfilled and artifact.artifact_id is not None
        requirements.append({
            "key": f"artifact:{artifact.id}", "kind": "artifact",
            "label": artifact.artifact_type, "passed": passed,
            "value": str(artifact.artifact_id) if artifact.artifact_id else None,
        })
        if passed:
            evidence.append(f"artifact:{artifact.artifact_id}")
    for gate in sorted(stage.gates, key=lambda value: str(value.id)):
        if not gate.is_mandatory:
            continue
        passed = gate.status == "approved"
        requirements.append({
            "key": f"gate:{gate.id}", "kind": "gate", "label": gate.name,
            "passed": passed, "value": gate.status,
        })
        if passed:
            evidence.append(f"gate:{gate.id}")
    if stage.requires_approval and not any(g.gate_type == "approval" for g in stage.gates):
        requirements.append({
            "key": "required:approval_gate", "kind": "gate", "label": "Approval gate",
            "passed": False, "value": "missing",
        })
    if stage.requires_verification and not any(g.gate_type == "verification" for g in stage.gates):
        requirements.append({
            "key": "required:verification_gate", "kind": "gate", "label": "Verification gate",
            "passed": False, "value": "missing",
        })
    latest = await _latest_checkpoint(db, stage_id=stage.id)
    if latest:
        evidence.extend(latest.evidence_refs)
        if latest.checkpoint_type in STOP_TYPES:
            reason = latest.blocker_code or latest.error_code or latest.checkpoint_type
            blockers.append({
                "code": reason, "checkpoint_id": str(latest.id), "message": latest.message,
                "resume_from": latest.resume_from_step_key,
            })
            requirements.append({
                "key": f"checkpoint:{latest.id}", "kind": "runtime",
                "label": "Latest execution checkpoint is recoverable", "passed": False,
                "value": latest.checkpoint_type,
            })
    missing = [item for item in requirements if not item["passed"]]
    inputs = {
        "stage_id": str(stage.id), "stage_revision": stage.revision,
        "status": stage.status, "requirements": requirements,
        "blockers": blockers, "evidence_refs": sorted(set(evidence)),
        "evaluator_version": "stage-completion-v1",
    }
    return inputs, requirements, missing, blockers


async def _evaluate_stage(
    db: AsyncSession, stage: PipelineStage, principal: ActorPrincipal
) -> StageCompletionAssessment:
    inputs, requirements, missing, blockers = await _stage_inputs(db, stage)
    input_hash = canonical_hash(inputs)
    existing = (await db.execute(select(StageCompletionAssessment).where(
        StageCompletionAssessment.pipeline_stage_id == stage.id,
        StageCompletionAssessment.input_hash == input_hash,
    ))).scalar_one_or_none()
    if existing:
        return existing
    project_id = await _stage_project_id(db, stage)
    baseline = (await db.execute(
        select(PlanBaseline).join(ProjectPlan, ProjectPlan.id == PlanBaseline.project_plan_id)
        .where(ProjectPlan.project_id == project_id).order_by(PlanBaseline.frozen_at.desc()).limit(1)
    )).scalar_one_or_none()
    assessment = StageCompletionAssessment(
        pipeline_stage_id=stage.id, stage_revision=stage.revision,
        baseline_id=baseline.id if baseline else None, policy_version_id=None,
        input_hash=input_hash, result="ready" if not missing and not blockers else "not_ready",
        requirement_results=requirements, missing_requirements=missing,
        blocking_reasons=blockers, evidence_refs=inputs["evidence_refs"],
        evaluator_version="stage-completion-v1", evaluated_at=datetime.now(timezone.utc),
        evaluated_by_type=principal.principal_type, evaluated_by_id=principal.principal_id,
        evaluated_by_name=principal.display_name,
    )
    db.add(assessment)
    await db.flush()
    return assessment


@router.post("/api/v1/executions/{execution_id}/checkpoints", response_model=ProgressCheckpointOut)
async def record_execution_checkpoint(
    execution_id: uuid.UUID, payload: ProgressCheckpointCreate,
    principal: ActorPrincipal = Depends(get_actor_principal), db: AsyncSession = Depends(get_db),
) -> ProgressCheckpoint:
    execution, task, project_id = await _execution_context(db, execution_id)
    await authorize_action(db, principal, "planning.progress.manage", project_id=project_id)
    checkpoint = await _record_checkpoint(db, principal, project_id, payload, task, execution)
    await db.commit()
    await db.refresh(checkpoint)
    await _notify_checkpoint(checkpoint.id, checkpoint.checkpoint_type, checkpoint.message)
    return checkpoint


async def _execution_action(
    db: AsyncSession, principal: ActorPrincipal, execution_id: uuid.UUID,
    payload: ExecutionActionIn, checkpoint_type: str, status_value: str,
) -> tuple[TaskExecution, ProgressCheckpoint]:
    execution, task, project_id = await _execution_context(db, execution_id)
    await authorize_action(db, principal, "planning.progress.manage", project_id=project_id)
    latest = await _latest_checkpoint(db, execution_id=execution.id)
    execution.status = status_value
    cp_payload = ProgressCheckpointCreate(
        pipeline_stage_id=latest.pipeline_stage_id if latest else None, checkpoint_type=checkpoint_type,
        step_key=payload.step_key, step_label=payload.step_label,
        evidence_refs=payload.evidence_refs, resume_from_step_key=payload.resume_from_step_key,
        blocker_code=payload.blocker_code, error_code=payload.error_code,
        message=payload.message, idempotency_key=payload.idempotency_key,
        state_snapshot={"execution_status": status_value},
    )
    checkpoint = await _record_checkpoint(db, principal, project_id, cp_payload, task, execution)
    return execution, checkpoint


@router.post("/api/v1/executions/{execution_id}:block", response_model=ExecutionActionOut)
async def block_execution(
    execution_id: uuid.UUID, payload: ExecutionActionIn,
    principal: ActorPrincipal = Depends(get_actor_principal), db: AsyncSession = Depends(get_db),
) -> ExecutionActionOut:
    if not payload.blocker_code:
        raise HTTPException(422, "blocker_code is required")
    execution, checkpoint = await _execution_action(db, principal, execution_id, payload, "blocked", "blocked")
    await db.commit(); await db.refresh(checkpoint)
    await _notify_checkpoint(checkpoint.id, "blocked", checkpoint.message)
    return ExecutionActionOut(execution_id=execution.id, execution_status=execution.status, checkpoint=checkpoint)


@router.post("/api/v1/executions/{execution_id}:pause", response_model=ExecutionActionOut)
async def pause_execution(
    execution_id: uuid.UUID, payload: ExecutionActionIn,
    principal: ActorPrincipal = Depends(get_actor_principal), db: AsyncSession = Depends(get_db),
) -> ExecutionActionOut:
    execution, checkpoint = await _execution_action(db, principal, execution_id, payload, "paused", "paused")
    await db.commit(); await db.refresh(checkpoint)
    await _notify_checkpoint(checkpoint.id, "paused", checkpoint.message)
    return ExecutionActionOut(execution_id=execution.id, execution_status=execution.status, checkpoint=checkpoint)


@router.post("/api/v1/executions/{execution_id}:reconcile", response_model=ExecutionActionOut)
async def reconcile_execution(
    execution_id: uuid.UUID, payload: ExecutionActionIn,
    principal: ActorPrincipal = Depends(get_actor_principal), db: AsyncSession = Depends(get_db),
) -> ExecutionActionOut:
    if payload.observed_state not in {"running", "finished", "missing"}:
        raise HTTPException(422, "observed_state must be running, finished, or missing")
    checkpoint_type = "reconciled" if payload.observed_state != "missing" else "failed"
    status_value = {"running": "running", "finished": "completed", "missing": "failed"}[payload.observed_state]
    if payload.observed_state == "finished" and not payload.evidence_refs:
        raise HTTPException(409, "Finished reconciliation requires evidence_refs")
    if checkpoint_type == "failed" and not payload.error_code:
        payload.error_code = "runtime_process_missing"
    execution, checkpoint = await _execution_action(
        db, principal, execution_id, payload, checkpoint_type, status_value
    )
    await db.commit(); await db.refresh(checkpoint)
    await _notify_checkpoint(checkpoint.id, checkpoint_type, checkpoint.message)
    return ExecutionActionOut(execution_id=execution.id, execution_status=execution.status, checkpoint=checkpoint)


@router.post("/api/v1/executions/{execution_id}:resume", response_model=ExecutionActionOut)
async def resume_execution(
    execution_id: uuid.UUID, payload: ExecutionActionIn,
    principal: ActorPrincipal = Depends(get_actor_principal), db: AsyncSession = Depends(get_db),
) -> ExecutionActionOut:
    execution, task, project_id = await _execution_context(db, execution_id)
    await authorize_action(db, principal, "planning.progress.manage", project_id=project_id)
    latest = await _latest_checkpoint(db, execution_id=execution.id)
    if latest is None or latest.checkpoint_type not in STOP_TYPES | {"reconciled"}:
        raise HTTPException(409, "Execution has no paused, blocked, failed, or reconciled checkpoint")
    resumed = execution
    if execution.status in {"failed", "completed", "verified"}:
        max_attempt = (await db.execute(select(func.coalesce(func.max(TaskExecution.attempt_number), 0)).where(
            TaskExecution.task_id == task.id
        ))).scalar_one()
        resumed = TaskExecution(
            task_id=task.id, assignment_id=execution.assignment_id,
            runtime_profile_id=execution.runtime_profile_id, loop_policy_id=execution.loop_policy_id,
            parent_execution_id=execution.id, attempt_number=int(max_attempt) + 1,
            executor_type=execution.executor_type, runtime_type=execution.runtime_type,
            loop_iteration=execution.loop_iteration + 1, status="running",
            started_at=datetime.now(timezone.utc),
        )
        db.add(resumed); await db.flush()
    else:
        resumed.status = "running"
    checkpoint = await _record_checkpoint(db, principal, project_id, ProgressCheckpointCreate(
        pipeline_stage_id=latest.pipeline_stage_id, checkpoint_type="resumed",
        step_key=payload.step_key, step_label=payload.step_label,
        evidence_refs=payload.evidence_refs,
        resume_from_step_key=payload.resume_from_step_key or latest.resume_from_step_key or latest.step_key,
        message=payload.message, idempotency_key=payload.idempotency_key,
        state_snapshot={"resumed_from_execution_id": str(execution.id)},
    ), task, resumed)
    task.status = "in_progress"
    await db.commit(); await db.refresh(checkpoint)
    await _notify_checkpoint(checkpoint.id, "resumed", checkpoint.message)
    return ExecutionActionOut(
        execution_id=execution.id, execution_status=resumed.status, checkpoint=checkpoint,
        resumed_execution_id=resumed.id,
    )


@router.post(
    "/api/v1/pipeline-stages/{stage_id}:evaluate-completion",
    response_model=StageCompletionAssessmentOut,
)
async def evaluate_stage_completion(
    stage_id: uuid.UUID, principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
) -> StageCompletionAssessment:
    stage = await _stage_or_404(db, stage_id)
    project_id = await _stage_project_id(db, stage)
    await authorize_action(db, principal, "planning.progress.view", project_id=project_id)
    assessment = await _evaluate_stage(db, stage, principal)
    await db.commit(); await db.refresh(assessment)
    return assessment


@router.post("/api/v1/pipeline-stages/{stage_id}:complete", response_model=CompleteStageOut)
async def complete_stage(
    stage_id: uuid.UUID, payload: CompleteStageIn,
    principal: ActorPrincipal = Depends(get_actor_principal), db: AsyncSession = Depends(get_db),
) -> CompleteStageOut:
    stage = await _stage_or_404(db, stage_id)
    project_id = await _stage_project_id(db, stage)
    await authorize_action(db, principal, "planning.stage.complete", project_id=project_id)
    existing_cp = (await db.execute(select(ProgressCheckpoint).where(
        ProgressCheckpoint.idempotency_key == f"stage-complete:{payload.idempotency_key}"
    ))).scalar_one_or_none()
    if existing_cp:
        assessment = await db.get(StageCompletionAssessment, payload.assessment_id)
        return CompleteStageOut(
            stage_id=stage.id, status=stage.status, revision=stage.revision,
            assessment_id=assessment.id, checkpoint=existing_cp,
        )
    assessment = await db.get(StageCompletionAssessment, payload.assessment_id)
    if assessment is None or assessment.pipeline_stage_id != stage.id:
        raise HTTPException(404, "Stage completion assessment not found")
    inputs, _, _, _ = await _stage_inputs(db, stage)
    if assessment.input_hash != canonical_hash(inputs) or assessment.stage_revision != stage.revision:
        raise HTTPException(409, "Stage completion assessment is stale; evaluate again")
    if assessment.result != "ready":
        raise HTTPException(409, {"code": "stage_not_ready", "missing": assessment.missing_requirements})
    stage.status = "completed"
    checkpoint = await _record_checkpoint(db, principal, project_id, ProgressCheckpointCreate(
        pipeline_stage_id=stage.id, checkpoint_type="completed",
        step_key="stage.completed", step_label=f"Stage {stage.name} completed",
        completed_requirement_keys=[item["key"] for item in assessment.requirement_results if item["passed"]],
        evidence_refs=assessment.evidence_refs,
        message="Stage completion confirmed by deterministic assessment",
        idempotency_key=f"stage-complete:{payload.idempotency_key}",
        state_snapshot={"assessment_id": str(assessment.id), "input_hash": assessment.input_hash},
    ))
    db.add(AuditEvent(
        entity_type="pipeline_stage", entity_id=stage.id, event_type="stage_completed",
        actor=principal.display_name,
        payload={"assessment_id": str(assessment.id), "input_hash": assessment.input_hash},
    ))
    await db.commit(); await db.refresh(checkpoint)
    return CompleteStageOut(
        stage_id=stage.id, status=stage.status, revision=stage.revision,
        assessment_id=assessment.id, checkpoint=checkpoint,
    )


async def _stage_progress_dict(db: AsyncSession, stage: PipelineStage) -> dict:
    checkpoint = await _latest_checkpoint(db, stage_id=stage.id)
    assessment = (await db.execute(select(StageCompletionAssessment).where(
        StageCompletionAssessment.pipeline_stage_id == stage.id
    ).order_by(StageCompletionAssessment.evaluated_at.desc()).limit(1))).scalar_one_or_none()
    assessment_data = None
    missing: list[dict] = []
    total = completed = 0
    if assessment:
        assessment_data = StageCompletionAssessmentOut.model_validate(assessment).model_dump()
        current_inputs, _, current_missing, _ = await _stage_inputs(db, stage)
        completion_confirms_assessment = (
            stage.status == "completed" and checkpoint is not None
            and checkpoint.checkpoint_type == "completed"
            and checkpoint.state_snapshot.get("assessment_id") == str(assessment.id)
        )
        if assessment.input_hash != canonical_hash(current_inputs) and not completion_confirms_assessment:
            assessment_data["result"] = "stale"
            missing = current_missing
        else:
            missing = assessment.missing_requirements
        total = len(assessment.requirement_results)
        completed = sum(1 for item in assessment.requirement_results if item.get("passed"))
    reason = None
    if checkpoint and checkpoint.checkpoint_type in STOP_TYPES:
        reason = checkpoint.blocker_code or checkpoint.error_code or checkpoint.message or checkpoint.checkpoint_type
    return {
        "stage_id": stage.id, "pipeline_id": stage.pipeline_id, "stage_name": stage.name,
        "order_index": stage.order_index, "effective_status": stage.status,
        "requirement_total": total, "requirement_completed": completed,
        "missing_requirements": missing,
        "last_checkpoint": checkpoint, "stopped_reason": reason,
        "resume_from": checkpoint.resume_from_step_key if checkpoint else None,
        "completion_assessment": assessment_data,
    }


@router.get("/api/v1/projects/{project_id}/progress", response_model=ProjectProgressOut)
async def get_project_progress(
    project_id: uuid.UUID, principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if await db.get(Project, project_id) is None:
        raise HTTPException(404, "Project not found")
    await authorize_action(db, principal, "planning.progress.view", project_id=project_id)
    pipeline = (await db.execute(select(ProjectPipeline).where(
        ProjectPipeline.project_id == project_id, ProjectPipeline.is_active.is_(True)
    ).order_by(ProjectPipeline.updated_at.desc()).limit(1))).scalar_one_or_none()
    if pipeline is None:
        return {"project_id": project_id, "macroflow": "conception", "pipeline_id": None,
                "current_stage_id": None, "stages": [], "last_confirmed_at": None,
                "stopped_at": None, "first_safe_action": "Create or activate a project pipeline"}
    stages = list((await db.execute(select(PipelineStage).where(
        PipelineStage.pipeline_id == pipeline.id
    ).order_by(PipelineStage.order_index))).scalars())
    stage_rows = [await _stage_progress_dict(db, await _stage_or_404(db, stage.id)) for stage in stages]
    current = next((row for row in stage_rows if row["effective_status"] not in TERMINAL_STAGE_STATUSES), None)
    all_checkpoints = list((await db.execute(select(ProgressCheckpoint).where(
        ProgressCheckpoint.project_id == project_id
    ).order_by(ProgressCheckpoint.last_confirmed_at.desc()).limit(1))).scalars())
    latest = all_checkpoints[0] if all_checkpoints else None
    stopped = None
    if latest and latest.checkpoint_type in STOP_TYPES:
        stopped = {
            "checkpoint_id": str(latest.id), "type": latest.checkpoint_type,
            "step_key": latest.step_key, "step_label": latest.step_label,
            "reason": latest.blocker_code or latest.error_code or latest.message,
            "task_execution_id": str(latest.task_execution_id) if latest.task_execution_id else None,
        }
    stage_type = next((s.stage_type for s in stages if current and s.id == current["stage_id"]), None)
    macroflow = "conception" if stage_type in {"discovery", "spec", "architecture_review"} else "delivery"
    safe_action = None
    if latest and latest.checkpoint_type in STOP_TYPES:
        safe_action = f"Reconcile and resume from {latest.resume_from_step_key or latest.step_key}"
    elif current:
        safe_action = f"Evaluate completion of {current['stage_name']}"
    return {
        "project_id": project_id, "macroflow": macroflow, "pipeline_id": pipeline.id,
        "current_stage_id": current["stage_id"] if current else None, "stages": stage_rows,
        "last_confirmed_at": latest.last_confirmed_at if latest else None,
        "stopped_at": stopped, "first_safe_action": safe_action,
    }


@router.get("/api/v1/projects/{project_id}/progress-timeline", response_model=list[ProgressCheckpointOut])
async def get_progress_timeline(
    project_id: uuid.UUID, principal: ActorPrincipal = Depends(get_actor_principal),
    db: AsyncSession = Depends(get_db),
) -> list[ProgressCheckpoint]:
    await authorize_action(db, principal, "planning.progress.view", project_id=project_id)
    return list((await db.execute(select(ProgressCheckpoint).where(
        ProgressCheckpoint.project_id == project_id
    ).order_by(ProgressCheckpoint.last_confirmed_at, ProgressCheckpoint.sequence))).scalars())

"""Prepare canonical answer context inside the existing dispatch admission."""
import hashlib

from fastapi import HTTPException
from sqlalchemy import select

from app.core.demand_workflow import WorkflowBlocked, requires_reconciliation
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent
from app.db.models.operations import AgentQuestion
from app.db.models.orchestration import TaskExecutionReview
from app.db.models.task import ProjectTask, TaskExecution


async def prepare_answer_context(db, demand):
    question = await db.scalar(select(AgentQuestion).where(AgentQuestion.reply_demand_id == demand.id)
                               .execution_options(populate_existing=True))
    if question is None or demand.origin_type != "task" or demand.origin_id is None:
        return
    if question.status != "answered" or question.agent_id != demand.target_agent_id:
        raise WorkflowBlocked("The canonical answer must retain its answered question and assigned recipient")
    source = await db.get(AgentDemand, question.origin_demand_id, populate_existing=True) if question.origin_demand_id else None
    if (source is None or requires_reconciliation(source) or source.dispatch_status in {"dispatched", "running"}
            or (source.agent_run_id and source.dispatch_status is None)):
        raise WorkflowBlocked("Reconcile the original run before executing its answer continuation")
    review = await db.scalar(select(TaskExecutionReview).where(
        TaskExecutionReview.runtime_session_ref == str(demand.id)))
    previous_id = review.execution_id if review else source.task_execution_id
    previous = await db.get(TaskExecution, previous_id) if previous_id else None
    source_task_id = previous.task_id if previous else source.origin_id
    if source_task_id is not None and source_task_id != demand.origin_id:
        raise WorkflowBlocked("The answer's original task context is inconsistent")
    task = await db.get(ProjectTask, demand.origin_id, populate_existing=True)
    if task is None:
        raise WorkflowBlocked("The canonical task is unavailable")
    observed = task.updated_at
    from app.core.agent_questions import compose_answer_message
    from app.core.mission_dispatch import build_mission_dispatch_context, plain_task_body
    from app.core.task_baseline_guard import assert_task_baseline_current, task_missions, _governing_mission

    await assert_task_baseline_current(db, task)
    instruction = compose_answer_message(question) + (
        "\n\nConsulte os resultados e evidências da tentativa anterior antes de agir. "
        "Preserve efeitos já produzidos; execute apenas o que falta no escopo autorizado da tarefa."
        f"\nMensagem de origem: #{source.number}; pergunta: #{question.number}.")
    missions = await task_missions(db, task)
    manifest = []
    try:
        if review is not None:
            latest = await db.scalar(select(TaskExecution.id).where(TaskExecution.task_id == task.id)
                .order_by(TaskExecution.attempt_number.desc()).limit(1))
            if review.status not in {"pending", "running"} or latest != review.execution_id:
                raise WorkflowBlocked("The original review no longer refers to the current delivery")
            body = source.body + "\n\n" + compose_answer_message(question)
            manifest = [{"source": "review_continuation", "id": str(review.id),
                         "hash": hashlib.sha256(source.body.encode()).hexdigest()}]
        elif missions:
            from app.api.routes.task import _mission_assignment
            from app.db.models.mission_cycle import MissionContextVersion
            _, member = await _mission_assignment(db, task, demand.target_agent_id)
            mission = await _governing_mission(db, task, missions)
            if source.mission_context_version_id:
                carried = await db.get(MissionContextVersion, source.mission_context_version_id)
                if (carried is None or carried.project_id != mission.project_id
                        or carried.sources.get("current_baseline_id") != str(mission.current_baseline_id)
                        or carried.sources.get("brief_artifact_id") != str(mission.brief_artifact_id)):
                    raise WorkflowBlocked("The original approved mission context changed; reevaluate this continuation")
            context = await build_mission_dispatch_context(db, task, mission=mission,
                working_path=demand.working_path, membership=member, command_text=instruction)
            body, manifest = context.body, context.manifest
        else:
            body = plain_task_body(task) + "\n\n" + instruction
    except HTTPException as exc:
        if isinstance(exc, WorkflowBlocked):
            raise
        raise WorkflowBlocked(exc.detail) from exc
    await db.refresh(task)
    if task.updated_at != observed:
        raise WorkflowBlocked("The task changed while preparing its continuation; reevaluate current context")
    demand.body = body
    db.add(AuditEvent(entity_type="agent_demand", entity_id=demand.id,
        event_type="canonical_answer_context_prepared", actor="system",
        payload={"question_id": str(question.id), "source_message_id": str(source.id),
                 "task_id": str(task.id), "body_sha256": hashlib.sha256(body.encode()).hexdigest(),
                 "context_manifest": manifest}))

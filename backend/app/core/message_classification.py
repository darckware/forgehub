"""Read-only, bounded-query Messages labels; no execution or approval authority."""
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath

from sqlalchemy import and_, or_, select

from app.core.demand_workflow import approval_fingerprint, requires_reconciliation
from app.core.message_triage_context import source_stamp
from app.core.message_triage_revision import context_revision_sql
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent
from app.db.models.message_triage import MessageTriageResult
from app.db.models.mission_cycle import AgentAvailability
from app.db.models.moodle_approval import MoodleApproval
from app.db.models.operations import AgentQuestion
from app.db.models.task import ProjectTask, TaskDependency, TaskExecution

MESSAGE_LABELS = (
    'analysis_pending', 'authorization_pending', 'decision_pending', 'awaiting_executor',
    'quota_unavailable', 'executor_busy', 'executor_unavailable', 'executor_unassigned',
    'awaiting_information', 'awaiting_dependency', 'awaiting_service', 'scheduled', 'ready',
    'running', 'awaiting_verification', 'uncertain_execution', 'needs_correction',
    'delivery_verified', 'completed', 'possible_duplicate', 'possible_obsolete', 'obsolete',
    'informational_feedback', 'missing_context', 'archived',
)


def _active(row):
    return row.dispatch_status in {'dispatched', 'running'} or (
        row.dispatch_status is None and row.agent_run_id is not None)


def _metadata(labels, summary, *, wait=None, until=None, decision=None, destination=None, question_id=None):
    return dict(message_labels=list(dict.fromkeys(labels))[:3], execution_wait_reason=wait,
        execution_wait_until=until, classification_summary=summary,
        operator_destination=destination, operator_decision=decision, operator_question_id=question_id)


async def classify_messages(db, demands):
    """Return ID→metadata using bounded batch queries, independently of list size.

    Cached model advice is accepted only for the current source and linked SQL
    revisions. It cannot assert delivery, authorization or completion.
    """
    if not demands:
        return {}
    now = datetime.now(timezone.utc)
    ids = [row.id for row in demands]
    target_ids = {row.target_agent_id for row in demands if row.target_agent_id}
    questions = {}
    for question in (await db.scalars(select(AgentQuestion).where(
        AgentQuestion.origin_demand_id.in_(ids), AgentQuestion.status == 'pending',
        AgentQuestion.blocking.is_(True)).order_by(AgentQuestion.created_at, AgentQuestion.id))).all():
        questions.setdefault(question.origin_demand_id, question.id)
    moodle = {row.message_id: row for row in (await db.scalars(select(MoodleApproval)
        .where(MoodleApproval.message_id.in_(ids)).execution_options(populate_existing=True))).all()}
    agents = {row.id: row for row in (await db.scalars(select(Agent).where(Agent.id.in_(target_ids))
        .execution_options(populate_existing=True))).all()}
    availability = {row.agent_id: row for row in (await db.scalars(select(AgentAvailability).where(
        AgentAvailability.agent_id.in_(target_ids), AgentAvailability.unavailable_until > now)
        .execution_options(populate_existing=True))).all()}
    busy = set((await db.scalars(select(AgentDemand.target_agent_id).where(
        AgentDemand.target_agent_id.in_(target_ids), or_(AgentDemand.dispatch_status.in_(('dispatched', 'running')),
            and_(AgentDemand.dispatch_status.is_(None), AgentDemand.agent_run_id.isnot(None)))))).all())
    deliveries = {}
    for event in (await db.scalars(select(AuditEvent).where(AuditEvent.entity_id.in_(ids),
        AuditEvent.entity_type == 'agent_demand',
        AuditEvent.event_type.in_(('message_delivery_verified', 'message_work_resolved')))
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()))).all():
        deliveries.setdefault(event.entity_id, []).append(event.payload or {})
    analyses = {row.message_id: row for row in (await db.scalars(select(MessageTriageResult)
        .join(AgentDemand, AgentDemand.id == MessageTriageResult.message_id)
        .where(MessageTriageResult.message_id.in_(ids),
            MessageTriageResult.source_updated_at == AgentDemand.updated_at,
            MessageTriageResult.context_versions['revision'] == context_revision_sql())
        .execution_options(populate_existing=True))).all()}
    checking = set((await db.scalars(select(AgentDemand.failure_check_source_id).where(
        AgentDemand.failure_check_source_id.in_(ids), AgentDemand.status != 'archived',
        or_(AgentDemand.dispatch_status.is_(None),
            AgentDemand.dispatch_status.notin_(('completed', 'failed')))))).all())
    execution_ids = {row.task_execution_id for row in demands if row.task_execution_id}
    executions = {row.id: row for row in (await db.scalars(select(TaskExecution)
        .where(TaskExecution.id.in_(execution_ids)).execution_options(populate_existing=True))).all()}
    task_ids = {row.origin_id for row in demands if row.origin_type == 'task' and row.origin_id}
    task_ids.update(row.task_id for row in executions.values())
    blocked_tasks = set((await db.scalars(select(TaskDependency.task_id)
        .outerjoin(ProjectTask, ProjectTask.id == TaskDependency.depends_on_task_id)
        .where(TaskDependency.task_id.in_(task_ids), or_(ProjectTask.status.is_(None),
            ProjectTask.status.notin_(('done', 'deployed')))))).all())

    result = {}
    for row in demands:
        fingerprint = approval_fingerprint(row)
        proof = next((event for event in deliveries.get(row.id, [])
                      if event.get('content_hash') == fingerprint), None)
        analysis = analyses.get(row.id)
        if analysis and analysis.source_fingerprint != source_stamp(row):
            analysis = None
        approval = moodle.get(row.id)
        destination = 'moodle_approvals' if approval else (
            'incubations' if row.origin_type == 'incubation' else 'agent_tasks')
        pending_authorization = row.requires_approval and row.approval_status != 'rejected' and (
            row.approval_status != 'approved' or row.approved_content_hash != fingerprint)
        if approval and approval.state in {'pending', 'approved'}:
            pending_authorization |= (approval.state == 'pending' or approval.message_hash != fingerprint
                or approval.executor_id != row.target_agent_id or approval.expires_at <= now)
        def human_turn(kind, row=row, approval=approval):
            # Same rule as demand_management.human_failure_sql: the operator's
            # decision queue, unless a diagnostic is still open or the Moodle
            # flow, an incubation owner or a consolidation already owns it.
            if (approval or row.id in checking or row.origin_type == 'incubation'
                    or row.status == 'archived' or row.consolidated_into_id):
                return {}
            return dict(decision=kind, destination='agent_tasks')
        own_tasks = {row.origin_id}
        execution = executions.get(row.task_execution_id)
        if execution:
            own_tasks.add(execution.task_id)

        if _active(row):
            info = _metadata(['running'], 'Execução ativa ou reservada no executor registrado.')
        elif requires_reconciliation(row):
            info = _metadata(['uncertain_execution'], 'Confirme o resultado da tentativa antes de qualquer repetição.',
                             **human_turn('reconciliation'))
        elif proof:
            info = _metadata(['delivery_verified'], 'Entrega verificada para o conteúdo atual; não executar novamente.')
        elif row.status == 'archived' or row.consolidated_into_id:
            info = _metadata(['obsolete'] if row.consolidated_into_id else ['archived'],
                'Registro preservado no histórico.' if not row.consolidated_into_id else 'Acompanhe a mensagem consolidada.')
        elif pending_authorization:
            info = _metadata(['authorization_pending'], 'O conteúdo atual precisa de autorização.',
                             decision='authorization', destination=destination)
        elif row.id in questions:
            info = _metadata(['decision_pending', 'awaiting_information'], 'Há uma pergunta bloqueante para você.',
                             decision='question', destination=destination, question_id=questions[row.id])
        elif (row.reply_to_id and row.from_agent_id == row.target_agent_id
              and row.dispatch_status == 'completed'
              and (row.command_text or '').startswith('failure-feedback:')):
            info = _metadata(['informational_feedback'], 'Retorno informativo vinculado à mensagem original.')
        elif row.requires_approval and row.approval_status == 'rejected':
            info = _metadata(['needs_correction'], 'Autorização recusada; preserve a decisão até nova revisão.')
        elif execution and execution.status == 'reported':
            info = _metadata(['awaiting_verification'], 'O relato da execução aguarda verificação e revisão.')
        elif row.dispatch_status == 'completed':
            info = _metadata(['completed'], 'A tentativa terminou; consulte o resultado e suas evidências.')
        elif row.origin_type == 'incubation':
            info = _metadata(['awaiting_information'] if row.incubation_state == 'decision_pending' else ['scheduled'],
                'A ideia aguarda a decisão do agente responsável.' if row.incubation_state == 'decision_pending'
                else 'A ideia está na janela de maturação.')
        elif own_tasks & blocked_tasks:
            info = _metadata(['awaiting_dependency'], 'Uma tarefa precedente ainda não foi concluída.')
        elif not row.from_agent_id or not PurePosixPath(row.working_path or '').is_absolute():
            info = _metadata(['missing_context'], 'Defina o responsável e o diretório de execução.')
        elif row.dispatch_status == 'failed':
            info = _metadata(['needs_correction'], 'A tentativa terminou com falha; analise a causa antes de repetir.',
                             **human_turn('correction'))
        else:
            executor = agents.get(row.target_agent_id)
            hold = availability.get(row.target_agent_id)
            quota = hold if hold and hold.recorded_by == "forgehub:usage-limit" else None
            # A future operator schedule is not an executor shortage. Existing
            # automatic quota schedules carry prior attempts and reset+margin.
            quota_schedule = quota and row.dispatch_attempts and row.scheduled_at and (
                row.scheduled_at <= quota.unavailable_until + timedelta(minutes=5))
            if row.scheduled_at and row.scheduled_at > now and not quota_schedule:
                info = _metadata(['scheduled'], 'Execução programada para uma data futura.')
            elif analysis and analysis.category in {'service', 'dependency', 'information'}:
                label = {'service': 'awaiting_service', 'dependency': 'awaiting_dependency',
                         'information': 'awaiting_information'}[analysis.category]
                info = _metadata([label], analysis.summary)
            elif row.target_agent_id is None:
                info = _metadata(['awaiting_executor', 'executor_unassigned'], 'A tarefa autorizada aguarda um executor.',
                                 wait='unassigned')
            elif executor is None or not executor.is_active or executor.status != "active" or not executor.runtime_type or (
                    executor.runtime_type == 'hermes' and not executor.profile_slug):
                info = _metadata(['awaiting_executor', 'executor_unavailable'], 'O executor registrado está indisponível.',
                                 wait='unavailable')
            elif quota:
                info = _metadata(['awaiting_executor', 'quota_unavailable'], 'A tarefa autorizada aguarda a cota do executor.',
                                 wait='quota', until=quota.unavailable_until)
            elif hold:
                info = _metadata(['awaiting_executor', 'executor_unavailable'],
                    'O executor tem uma indisponibilidade registrada.', wait='unavailable', until=hold.unavailable_until)
            elif row.target_agent_id in busy:
                info = _metadata(['awaiting_executor', 'executor_busy'], 'O executor já acompanha outra execução.', wait='busy')
            elif analysis and analysis.category in {'duplicate', 'obsolete'}:
                info = _metadata(['possible_duplicate' if analysis.category == 'duplicate' else 'possible_obsolete'],
                                 analysis.summary)
            elif analysis and analysis.operator_state == 'processing' and analysis.proposed_action == 'queue':
                info = _metadata(['ready'], 'A tarefa passou pela análise; os controles de despacho continuam obrigatórios.')
            else:
                info = _metadata(['analysis_pending'], 'Aguarda análise do conteúdo e das condições atuais.')
        result[row.id] = info
    return result


async def annotated_demands(db, demands):
    """Serialize additive API metadata without changing ORM or business state."""
    from app.api.schemas.demand import DemandOut
    metadata = await classify_messages(db, demands)
    return [DemandOut.model_validate(row).model_copy(update=metadata[row.id]) for row in demands]

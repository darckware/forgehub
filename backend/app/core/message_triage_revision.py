"""Database-side linked revisions for bounded Messages filtering and counts.

Every aggregate is correlated to the outer demand. Explicit related IDs support
snapshot creation without reading the triage table; otherwise the stored related
set is read from the outer triage result during freshness filtering.
"""
from sqlalchemy import String, and_, cast, exists, func, literal, or_, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import aliased

from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent
from app.db.models.message_triage import MessageTriageResult
from app.db.models.mission import MissionProjectLink, ProjectMission
from app.db.models.mission_cycle import AgentAvailability
from app.db.models.moodle_approval import MoodleApproval
from app.db.models.operations import AgentQuestion
from app.db.models.project import PlanBaseline, Project
from app.db.models.task import ProjectTask, TaskDependency, TaskExecution


def context_revision_sql(related_ids=None):
    """Return a JSONB revision expression correlated to ``AgentDemand``.

    ``None`` uses keys of the correlated result's context_versions['related'];
    an iterable uses only those IDs and never references MessageTriageResult.
    Missing/deleted rows change the object, including a non-max timestamp row.
    """
    empty = literal({}, type_=JSONB)

    def revisions(model, key, condition):
        return (select(func.coalesce(func.jsonb_object_agg(cast(key, String), model.updated_at), empty))
                .select_from(model).where(condition)
                .correlate(AgentDemand, MessageTriageResult).scalar_subquery())

    related = aliased(AgentDemand)
    if related_ids is None:
        keys = (select(cast(func.jsonb_object_keys(func.coalesce(
            MessageTriageResult.context_versions['related'], empty)), UUID(as_uuid=True)))
            .correlate(MessageTriageResult))
        related_condition = related.id.in_(keys)
    else:
        related_condition = related.id.in_(sorted({str(v) for v in related_ids}))

    # Match both task identities used by the runner's dependency guard.
    execution_task = (select(TaskExecution.task_id)
        .where(TaskExecution.id == AgentDemand.task_execution_id)
        .correlate(AgentDemand).scalar_subquery())

    def task_scope(column):
        return or_(and_(AgentDemand.origin_type == "task", column == AgentDemand.origin_id),
                   column == execution_task)

    dependency_ids = (select(TaskDependency.depends_on_task_id)
        .where(task_scope(TaskDependency.task_id)).correlate(AgentDemand))
    linked_missions = (select(MissionProjectLink.mission_project_id)
        .where(MissionProjectLink.executor_project_id == AgentDemand.project_id)
        .correlate(AgentDemand))
    mission_scope = or_(ProjectMission.project_id == AgentDemand.project_id,
                        ProjectMission.project_id.in_(linked_missions))
    baseline_ids = (select(ProjectMission.current_baseline_id)
        .where(mission_scope).correlate(AgentDemand))

    parts = {
        'moodle': revisions(MoodleApproval, MoodleApproval.id, MoodleApproval.message_id == AgentDemand.id),
        'questions': revisions(AgentQuestion, AgentQuestion.id, AgentQuestion.origin_demand_id == AgentDemand.id),
        'availability': revisions(AgentAvailability, AgentAvailability.agent_id,
                                  AgentAvailability.agent_id == AgentDemand.target_agent_id),
        'availability_active': exists(select(AgentAvailability.agent_id).where(
            AgentAvailability.agent_id == AgentDemand.target_agent_id,
            AgentAvailability.unavailable_until > func.now())).correlate(AgentDemand),
        'executor': revisions(Agent, Agent.id, Agent.id == AgentDemand.target_agent_id),
        'task': revisions(ProjectTask, ProjectTask.id, task_scope(ProjectTask.id)),
        'dependency_edges': revisions(TaskDependency, TaskDependency.id, task_scope(TaskDependency.task_id)),
        'dependency_tasks': revisions(ProjectTask, ProjectTask.id, ProjectTask.id.in_(dependency_ids)),
        'project': revisions(Project, Project.id, Project.id == AgentDemand.project_id),
        'mission_links': revisions(MissionProjectLink, MissionProjectLink.id,
                                   MissionProjectLink.executor_project_id == AgentDemand.project_id),
        'missions': revisions(ProjectMission, ProjectMission.project_id, mission_scope),
        'baselines': revisions(PlanBaseline, PlanBaseline.id, PlanBaseline.id.in_(baseline_ids)),
        'execution': revisions(TaskExecution, TaskExecution.id, TaskExecution.id == AgentDemand.task_execution_id),
        'deliveries': revisions(AuditEvent, AuditEvent.id, (AuditEvent.entity_id == AgentDemand.id)
            & AuditEvent.event_type.in_(('message_delivery_verified', 'message_work_resolved'))),
        'related': revisions(related, related.id, related_condition),
    }
    return func.jsonb_build_object(*(value for pair in parts.items() for value in pair))

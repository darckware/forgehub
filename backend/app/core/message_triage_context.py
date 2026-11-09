"""Trusted context routing and content/version stamps for advisory Messages analysis."""
import hashlib
import json

from sqlalchemy import select

from app.core.demand_workflow import approval_fingerprint
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent
from app.db.models.mission_cycle import AgentAvailability
from app.db.models.moodle_approval import MoodleApproval
from app.db.models.operations import AgentQuestion
from app.db.models.task import ProjectTask, TaskExecution

POLICY_VERSION = "messages-triage/2026-11-08.1"


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str).encode()).hexdigest()


def source_stamp(demand):
    return digest({key:getattr(demand,key,None) for key in (
        "subject","body","origin_type","origin_id","target_agent_id","from_agent_id","working_path",
        "project_id","context_area","command_text","channel","channel_ref","reply_to_id",
        "failure_check_source_id","consolidated_into_id","status","dispatch_status","agent_run_id",
        "dispatch_result","dispatch_error","dispatch_attempts","scheduled_at","requires_approval",
        "approval_status","approved_content_hash","incubation_state","matures_at","fixed_agent",
        "task_execution_id","mission_context_version_id","updated_at")})


def domain_for(demand, agents):
    """Only registered ownership and source channel determine the analysis identity."""
    slugs={agents[i].profile_slug for i in (demand.from_agent_id,demand.target_agent_id,
        demand.incubation_owner_id) if i in agents}
    private=slugs & {"maia","lara"}
    if len(private)>1:
        return None
    if demand.channel in {"whatsapp_group","whatsapp","personal"} and not private:
        return None
    return next(iter(private),"athos")


def display_context(demand):
    if demand.channel=="whatsapp_group" or (demand.context_area or "").startswith("instructor:"):
        return "Moodle · Grupo de instrutores"
    if demand.context_area:
        return demand.context_area
    return "Operação dos agentes"


def _version(row):
    if row is None:
        return None
    return {c.name:getattr(row,c.name) for c in row.__table__.columns
            if c.name in {"id","status","state","outcome","updated_at","finished_at","message_hash",
                          "unavailable_until","blocking","evidence_ref","agent_id","number",
                          "is_active","runtime_type","default_role","profile_slug"}}


async def context_stamp(db,demand,related_ids=(),*,lock=False):
    """Linked facts are part of freshness, independently of source.updated_at."""
    def stmt(model,condition):
        query=select(model).where(condition).execution_options(populate_existing=True)
        return query.with_for_update(read=True) if lock else query
    moodle=await db.scalar(stmt(MoodleApproval,MoodleApproval.message_id==demand.id))
    questions=(await db.scalars(stmt(AgentQuestion,AgentQuestion.origin_demand_id==demand.id))).all()
    availability=await db.scalar(stmt(AgentAvailability,AgentAvailability.agent_id==demand.target_agent_id))
    from app.db.models.agent import Agent
    executor=await db.scalar(stmt(Agent,Agent.id==demand.target_agent_id)) if demand.target_agent_id else None
    task=await db.scalar(stmt(ProjectTask,ProjectTask.id==demand.origin_id)) if demand.origin_id else None
    execution=await db.scalar(stmt(TaskExecution,TaskExecution.id==demand.task_execution_id)) if demand.task_execution_id else None
    diagnostic_source=await db.scalar(stmt(AgentDemand,AgentDemand.id==demand.failure_check_source_id)) if demand.failure_check_source_id else None
    diagnostic_deliveries=(await db.scalars(select(AuditEvent.id).where(
        AuditEvent.entity_id==demand.failure_check_source_id,
        AuditEvent.event_type.in_(("message_delivery_verified","message_work_resolved")))
        .order_by(AuditEvent.id))).all() if diagnostic_source else []
    related={}
    for rid in sorted({str(v) for v in related_ids}):
        import uuid
        row=await db.scalar(stmt(AgentDemand,AgentDemand.id==uuid.UUID(rid)))
        related[rid]=source_stamp(row) if row else None
    deliveries=(await db.scalars(select(AuditEvent).where(AuditEvent.entity_id==demand.id,
        AuditEvent.event_type.in_(("message_delivery_verified","message_work_resolved")))
        .order_by(AuditEvent.created_at,AuditEvent.id))).all()
    facts={"policy":POLICY_VERSION,"content":approval_fingerprint(demand),"moodle":_version(moodle),
           "questions":sorted((_version(q) for q in questions),key=lambda q:str(q["id"])),
           "availability":_version(availability),"executor":_version(executor),"task":_version(task),"execution":_version(execution),
           "deliveries":[str(e.id) for e in deliveries],"related":related}
    facts["diagnostic_source"]={"source":source_stamp(diagnostic_source),
        "deliveries":[str(i) for i in diagnostic_deliveries]} if diagnostic_source else None
    from app.core.message_triage_revision import context_revision_sql
    facts["revision"]=await db.scalar(select(context_revision_sql(related_ids)).select_from(AgentDemand)
        .where(AgentDemand.id==demand.id))
    facts=json.loads(json.dumps(facts,default=str))
    return digest(facts),facts


def prompt_item(demand,domain):
    return {"id":str(demand.id),"number":demand.number,"analysis_agent":domain,
            "title":demand.subject,"body":(demand.body or "")[:5000],
            "result":(demand.dispatch_result or "")[-5000:],"status":demand.dispatch_status,
            "origin_type":demand.origin_type,"context":display_context(demand),
            "working_path":demand.working_path,"updated_at":str(demand.updated_at),
            "approval":{"requires":demand.requires_approval,"status":demand.approval_status},
            "execution":{"run_id":demand.agent_run_id,"attempts":demand.dispatch_attempts,
                         "uncertain":"uncertain" in (demand.dispatch_error or "").lower()},
            "last_error":demand.dispatch_error}

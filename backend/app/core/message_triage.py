"""Messages operational decision layer: advisory context, deterministic authority, durable jobs."""
import asyncio
import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import and_, func, or_, select

from app.api.schemas.message_triage import TriageSuggestion
from app.core.completion_report import parse_completion_status
from app.core.config import settings
from app.core.demand_workflow import WorkflowBlocked, approval_fingerprint, ensure_workflow_allowed, requires_reconciliation
from app.core.evidence_bridge import verify_on_host
from app.core.message_triage_context import POLICY_VERSION, context_stamp, domain_for, prompt_item, source_stamp
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent
from app.db.models.message_triage import MessageAnalysisItem, MessageAnalysisRun, MessageTriageResult
from app.db.models.mission_cycle import AgentAvailability
from app.db.models.moodle_approval import MoodleApproval
from app.db.models.operations import AgentQuestion

logger=logging.getLogger(__name__)
ADMISSION_LOCK=0x464854524941
BATCH_SIZE=10
LEASE_SECONDS=180
POLL_SECONDS=30
SAFE_ERROR="Não foi possível concluir a análise. As tarefas foram preservadas; tente novamente."


def now():
    return datetime.now(timezone.utc)


def busy(demand):
    return demand.dispatch_status in ("running","dispatched") or (demand.agent_run_id and demand.dispatch_status is None) or requires_reconciliation(demand)


def scope_filters(agent_id=None,context=None):
    filters=[]
    if agent_id:
        filters.append(func.coalesce(AgentDemand.incubation_owner_id,AgentDemand.target_agent_id,AgentDemand.from_agent_id)==uuid.UUID(str(agent_id)))
    if context and context not in ("all",""):
        if context.startswith("project:"):
            filters.append(AgentDemand.project_id==uuid.UUID(context[8:]))
        elif context.startswith("area:"):
            filters.extend((AgentDemand.project_id.is_(None),AgentDemand.context_area==context[5:]))
        elif context=="unclassified":
            filters.extend((AgentDemand.project_id.is_(None),AgentDemand.context_area.is_(None)))
        else:
            raise ValueError("Invalid analysis context")
    return filters


def candidate_query(agent_id=None,context=None):
    return select(AgentDemand).where(AgentDemand.status!="archived",AgentDemand.consolidated_into_id.is_(None),
        or_(AgentDemand.dispatch_status.is_(None),AgentDemand.dispatch_status=="failed",
            and_(AgentDemand.reply_to_id.isnot(None),AgentDemand.dispatch_status=="completed",
                 AgentDemand.from_agent_id==AgentDemand.target_agent_id)),*scope_filters(agent_id,context))


async def enqueue_analysis(db,*,actor,agent_id=None,context=None):
    scope_filters(agent_id,context)  # validate before any mutation
    scope={"agent_id":str(agent_id) if agent_id else None,"context":context if context not in ("all","") else None}
    key=hashlib.sha256(json.dumps(scope,sort_keys=True).encode()).hexdigest()
    await db.execute(select(func.pg_advisory_xact_lock(ADMISSION_LOCK)))
    existing=await db.scalar(select(MessageAnalysisRun).where(MessageAnalysisRun.scope_key==key,
        MessageAnalysisRun.status.in_(("queued","running"))))
    if existing:
        await db.commit()
        return existing
    run=MessageAnalysisRun(scope_key=key,scope=scope,requested_by=actor)
    db.add(run)
    await db.flush()
    ids=list((await db.scalars(candidate_query(agent_id,context).with_only_columns(AgentDemand.id))).all())
    db.add_all(MessageAnalysisItem(run_id=run.id,message_id=i) for i in ids)
    run.total=len(ids)
    await db.commit()
    await db.refresh(run)
    return run


async def verified_delivery(db,demand):
    fingerprint=approval_fingerprint(demand)
    events=(await db.scalars(select(AuditEvent).where(AuditEvent.entity_id==demand.id,
        AuditEvent.entity_type=="agent_demand",AuditEvent.event_type.in_(("message_delivery_verified","message_work_resolved")))
        .order_by(AuditEvent.created_at.desc(),AuditEvent.id.desc()))).all()
    return next((e for e in events if (e.payload or {}).get("content_hash")==fingerprint),None)


async def register_delivery(db,message_id,payload,*,actor):
    demand=await db.get(AgentDemand,message_id,populate_existing=True)
    if demand is None:
        raise WorkflowBlocked("Message not found")
    if busy(demand) or demand.updated_at!=payload.expected_updated_at:
        raise WorkflowBlocked("The message changed or has an active/uncertain execution")
    if not demand.working_path or not demand.working_path.startswith("/"):
        raise WorkflowBlocked("An explicit working directory is required")
    if demand.origin_id or demand.task_execution_id:
        raise WorkflowBlocked("Use the governed ProjectTask evidence and independent review flow")
    if payload.executor_id and await db.get(Agent,payload.executor_id) is None:
        raise WorkflowBlocked("Executor not found")
    if payload.related_message_id:
        related=await db.get(AgentDemand,payload.related_message_id)
        if related is None or related.dispatch_status!="completed":
            raise WorkflowBlocked("Related delivery must have a completed execution")
    fingerprint=approval_fingerprint(demand)
    stamp=source_stamp(demand)
    directory,created=demand.working_path,demand.created_at
    await db.rollback()  # no row lock/transaction is held across host verification
    ok,_=await verify_on_host("git",directory,payload.evidence_ref[4:],created)
    if not ok:
        raise WorkflowBlocked("Delivery evidence could not be verified")
    demand=await db.scalar(select(AgentDemand).where(AgentDemand.id==message_id).with_for_update()
                           .execution_options(populate_existing=True))
    if demand is None or source_stamp(demand)!=stamp or busy(demand):
        raise WorkflowBlocked("The message changed during delivery verification")
    previous=await verified_delivery(db,demand)
    if previous is None:
        db.add(AuditEvent(entity_type="agent_demand",entity_id=demand.id,event_type="message_delivery_verified",
            actor=actor,payload={"content_hash":fingerprint,"evidence_ref":payload.evidence_ref,
                "summary":payload.summary,"executor_id":str(payload.executor_id) if payload.executor_id else None,
                "related_message_id":str(payload.related_message_id) if payload.related_message_id else None,
                "working_path":directory,"policy":POLICY_VERSION}))
        demand.scheduled_at=None
        await db.commit()
    return {"message_id":str(message_id),"verified":True,"evidence_ref":payload.evidence_ref}


def proposal(demand,status,category,summary,reason,recommendation,action="none",evidence=None):
    return TriageSuggestion(message_id=demand.id,status=status,category=category,summary=summary,
        reason=reason,recommendation=recommendation,proposed_action=action,evidence_refs=evidence or [])


async def deterministic_analysis(db,demand):
    if busy(demand):
        return proposal(demand,"waiting","uncertain","Execução em acompanhamento",
            "Uma execução ativa ou de resultado incerto não pode ser repetida.","Acompanhar o run registrado.")
    if demand.reply_to_id and demand.from_agent_id and demand.from_agent_id==demand.target_agent_id and demand.dispatch_status=="completed":
        return proposal(demand,"resolved","feedback","Aviso registrado na tarefa original",
            "Retorno informativo para o próprio agente, sem nova ação executável.","Preservar no histórico da origem.","archive_notice")
    delivery=await verified_delivery(db,demand)
    if delivery:
        return proposal(demand,"resolved","delivered","Entrega comprovada",
            (delivery.payload or {}).get("summary") or "Há uma entrega verificada para este conteúdo.",
            "Não despachar novamente; consultar as evidências.","resolve",[(delivery.payload or {}).get("evidence_ref","")])
    if demand.failure_check_source_id:
        source=await db.get(AgentDemand,demand.failure_check_source_id,populate_existing=True)
        source_delivery=await verified_delivery(db,source) if source else None
        if source_delivery:
            return proposal(demand,"resolved","obsolete","Diagnóstico superado pela entrega",
                "A tarefa original tem entrega comprovada para o conteúdo atual.",
                "Preservar o histórico; não executar um diagnóstico da falha antiga.","resolve",
                [(source_delivery.payload or {}).get("evidence_ref","")])
    moodle=await db.scalar(select(MoodleApproval).where(MoodleApproval.message_id==demand.id))
    if (moodle and moodle.state=="finished" and moodle.outcome=="completed"
            and moodle.message_hash==approval_fingerprint(demand)
            and parse_completion_status(demand.dispatch_result or "")=="DONE"):
        return proposal(demand,"resolved","delivered","Operação Moodle comprovada",
            "A proposta aprovada foi concluída e o relatório confirma DONE.","Preservar a tentativa; não repetir a operação.",
            "resolve",[f"moodle:{moodle.id}"])
    if demand.requires_approval and demand.approval_status=="rejected":
        return proposal(demand,"waiting","authorization","Execução recusada",
            "A autorização foi recusada no fluxo existente.","Preservar a decisão; não executar sem nova autorização.")
    if demand.requires_approval and (demand.approval_status!="approved" or demand.approved_content_hash!=approval_fingerprint(demand)):
        return proposal(demand,"decision","authorization","Autorização necessária",
            "O conteúdo atual ainda não tem autorização válida.","Revisar o objetivo e autorizar ou recusar pelo fluxo existente.")
    question=await db.scalar(select(AgentQuestion.id).where(AgentQuestion.origin_demand_id==demand.id,
        AgentQuestion.status=="pending",AgentQuestion.blocking.is_(True)).limit(1))
    if question:
        return proposal(demand,"decision","information","Há uma pergunta para você",
            "Existe uma pergunta bloqueante registrada para esta tarefa.","Responder à pergunta apresentada abaixo.")
    return None


async def check_admission(db,demand):
    if await verified_delivery(db,demand):
        raise WorkflowBlocked("This work is already delivered; no new execution is permitted")
    if demand.failure_check_source_id:
        source=await db.scalar(select(AgentDemand).where(AgentDemand.id==demand.failure_check_source_id)
            .with_for_update(read=True).execution_options(populate_existing=True))
        if source and await verified_delivery(db,source):
            raise WorkflowBlocked("The diagnostic source is already delivered; no new execution is permitted")
    if not settings.MESSAGE_TRIAGE_ENABLED:
        return
    result=await db.get(MessageTriageResult,demand.id,populate_existing=True)
    if result is None or result.source_fingerprint!=source_stamp(demand):
        raise WorkflowBlocked("Awaiting contextual analysis of the current message")
    context,_=await context_stamp(db,demand,result.context_versions.get("related",{}),lock=True)
    if context!=result.context_fingerprint or result.operator_state!="processing" or result.proposed_action!="queue":
        raise WorkflowBlocked("Analysis has changed or this task still has an unresolved blocker")


async def _claim_job(db):
    await db.execute(select(func.pg_advisory_xact_lock(ADMISSION_LOCK)))
    instant=now()
    active=await db.scalar(select(MessageAnalysisRun.id).where(MessageAnalysisRun.status=="running",
        MessageAnalysisRun.lease_until>instant).limit(1))
    if active:
        await db.rollback()
        return None
    run=await db.scalar(select(MessageAnalysisRun).where(or_(MessageAnalysisRun.status=="queued",
        and_(MessageAnalysisRun.status=="running",MessageAnalysisRun.lease_until<=instant)))
        .order_by(MessageAnalysisRun.created_at).with_for_update(skip_locked=True))
    if run is None:
        await db.rollback()
        return None
    if run.attempts>=3:
        run.status="failed"
        run.error=SAFE_ERROR
        run.finished_at=instant
        run.lease_until=None
        await db.commit()
        return None
    run.status="running"
    run.started_at=run.started_at or instant
    run.lease_until=instant+timedelta(seconds=LEASE_SECONDS)
    run.lease_token=uuid.uuid4()
    run.attempts+=1
    token,run_id=run.lease_token,run.id
    await db.commit()
    return run_id,token


async def _apply(db,run_id,token,message_id,stamp,context_hash,versions,suggestion):
    run=await db.scalar(select(MessageAnalysisRun).where(MessageAnalysisRun.id==run_id).with_for_update()
        .execution_options(populate_existing=True))
    if not run or run.status!="running" or run.lease_token!=token or run.lease_until<=now():
        await db.rollback()
        return False
    item=await db.get(MessageAnalysisItem,(run_id,message_id),populate_existing=True)
    if item is None or item.status!="pending":
        await db.rollback()
        return False
    demand=await db.scalar(select(AgentDemand).where(AgentDemand.id==message_id).with_for_update()
        .execution_options(populate_existing=True))
    if demand is None or demand.status=="archived" or source_stamp(demand)!=stamp:
        item.status="skipped"
    else:
        current_hash,_=await context_stamp(db,demand,versions.get("related",{}),lock=True)
        if current_hash!=context_hash:
            item.status="skipped"
        else:
            # Model recommendations never authorize a mutation. Resolve/archive only
            # when an independent deterministic check confirms the same action now.
            proven=await deterministic_analysis(db,demand)
            chosen=proven or suggestion
            applied=None
            state=chosen.status
            if not proven and state == "decision":
                state = "waiting"
            action=chosen.proposed_action
            if proven and proven.proposed_action in ("resolve","archive_notice"):
                applied=proven.proposed_action
                demand.scheduled_at=None
                if applied=="archive_notice":
                    demand.status="archived"
                    demand.decision_reason="Retorno ao próprio agente preservado no histórico da origem."
                elif not await verified_delivery(db,demand):
                    db.add(AuditEvent(entity_type="agent_demand",entity_id=demand.id,event_type="message_work_resolved",
                        actor="messages:triage",payload={"content_hash":approval_fingerprint(demand),
                            "summary":proven.summary,"evidence_ref":proven.evidence_refs[0] if proven.evidence_refs else None,
                            "policy":POLICY_VERSION}))
            elif state=="resolved":
                state="waiting"
                action="none"
            elif action=="queue":
                # New, already-authorized work only. Failed/partial attempts,
                # incubations and proposals are never reprocessed by model output.
                if demand.origin_type!="task" or demand.dispatch_status is not None or demand.reply_to_id:
                    state,action="waiting","none"
                else:
                    try:
                        await ensure_workflow_allowed(db,demand)
                        from app.api.routes.demand import _ensure_demand_dependencies_satisfied
                        await _ensure_demand_dependencies_satisfied(db,demand)
                        from app.core.task_baseline_guard import assert_task_baseline_current
                        from app.db.models.task import ProjectTask
                        task=await db.get(ProjectTask,demand.origin_id) if demand.origin_id else None
                        if task:
                            await assert_task_baseline_current(db,task)
                        agent=await db.get(Agent,demand.target_agent_id)
                        available=await db.get(AgentAvailability,demand.target_agent_id) if demand.target_agent_id else None
                        if not agent or not agent.is_active or agent.status!="active" or not agent.runtime_type or not demand.from_agent_id or not (demand.working_path or "").startswith("/"):
                            raise WorkflowBlocked("Execution context is incomplete")
                        if available and available.unavailable_until>now():
                            raise WorkflowBlocked("Awaiting executor availability")
                    except WorkflowBlocked:
                        state,action="waiting","none"
                    else:
                        state="processing"
                        if demand.scheduled_at is None:
                            demand.scheduled_at=now()
                        applied="queued"
            if not proven and action not in ("none","queue"):
                action="none"
            if not proven and state=="processing" and applied!="queued":
                state="waiting"
            await db.flush()
            await db.refresh(demand)
            final_context,final_versions=await context_stamp(db,demand,versions.get("related",{}),lock=True)
            result=await db.get(MessageTriageResult,message_id)
            if result is None:
                result=MessageTriageResult(message_id=message_id)
                db.add(result)
            for key,value in dict(analysis_run_id=run_id,source_updated_at=demand.updated_at,
                source_fingerprint=source_stamp(demand),context_fingerprint=final_context,context_versions=final_versions,
                operator_state=state,category=chosen.category,summary=chosen.summary,reason=chosen.reason,
                recommendation=chosen.recommendation,proposed_action=action,related_message_id=chosen.related_message_id,
                evidence_refs=chosen.evidence_refs,analyzed_at=now(),applied_action=applied).items():
                setattr(result,key,value)
            db.add(AuditEvent(entity_type="agent_demand",entity_id=message_id,event_type="message_triage_decided",
                actor="messages:triage",payload={"run_id":str(run_id),"policy":POLICY_VERSION,
                    "source_hash":stamp,"context_hash":context_hash,"state":state,"proposed_action":chosen.proposed_action,
                    "applied_action":applied,"summary":chosen.summary,"reason":chosen.reason}))
            item.status="done"
            run.applied+=int(applied is not None)
            summary=dict(run.summary or {})
            summary[state]=summary.get(state,0)+1
            run.summary=summary
    run.processed+=1
    run.lease_until=now()+timedelta(seconds=LEASE_SECONDS)
    await db.commit()
    return True


async def _renew_lease(run_id, token):
    async with AsyncSessionLocal() as db:
        run=await db.scalar(select(MessageAnalysisRun).where(MessageAnalysisRun.id==run_id)
            .with_for_update().execution_options(populate_existing=True))
        if not run or run.status!="running" or run.lease_token!=token or run.lease_until<=now():
            raise RuntimeError("Analysis lease lost")
        run.lease_until=now()+timedelta(seconds=LEASE_SECONDS)
        await db.commit()


async def _analyze_with_lease(run_id, token, analysis):
    """Keep a slow advisory call fenced without holding its database transaction."""
    task=asyncio.create_task(analysis)
    try:
        while True:
            done,_=await asyncio.wait({task},timeout=30)
            if done:
                return task.result()
            await _renew_lease(run_id,token)
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task,return_exceptions=True)


async def process_next_analysis():
    from app.core.message_triage_analysis import analyze_messages
    async with AsyncSessionLocal() as db:
        claim=await _claim_job(db)
    if not claim:
        return False
    run_id,token=claim
    cursor=None
    model_failed=False
    try:
        while True:
            await _renew_lease(run_id,token)
            prepared=[]
            async with AsyncSessionLocal() as db:
                ids=list((await db.scalars(select(MessageAnalysisItem.message_id).where(
                    MessageAnalysisItem.run_id==run_id,MessageAnalysisItem.status=="pending",
                    MessageAnalysisItem.message_id>cursor if cursor else True)
                    .order_by(MessageAnalysisItem.message_id).limit(BATCH_SIZE))).all())
                if not ids:
                    break
                cursor=ids[-1]
                agents={a.id:a for a in (await db.scalars(select(Agent))).all()}
                recent=list((await db.scalars(select(AgentDemand).where(AgentDemand.consolidated_into_id.is_(None))
                    .order_by(AgentDemand.updated_at.desc()).limit(300))).all())
                related=[]
                items=[]
                for message_id in ids:
                    demand=await db.get(AgentDemand,message_id,populate_existing=True)
                    if demand is None or demand.status=="archived":
                        prepared.append((message_id,None,None,{},None))
                        continue
                    domain=domain_for(demand,agents)
                    proven=await deterministic_analysis(db,demand)
                    candidates=[r for r in recent if r.id!=message_id and domain_for(r,agents)==domain
                        and (r.working_path==demand.working_path or (r.project_id and r.project_id==demand.project_id)
                             or r.id in (demand.reply_to_id,demand.failure_check_source_id))][:10]
                    linked=[r.id for r in candidates]
                    context_hash,versions=await context_stamp(db,demand,linked)
                    prepared.append((message_id,source_stamp(demand),context_hash,versions,proven))
                    if proven is None and domain:
                        items.append(prompt_item(demand,domain))
                        related.extend(prompt_item(r,domain) for r in candidates)
                    elif proven is None:
                        prepared[-1]=(*prepared[-1][:-1],proposal(demand,"waiting","review",
                            "Contexto privado a verificar","Não foi possível determinar uma identidade de análise segura.",
                            "Conferir a origem antes de analisar."))
                domains={item["analysis_agent"] for item in items}
                registry=[{"id":str(a.id),"name":a.name,"slug":a.profile_slug,"runtime":a.runtime_type,
                    "specialty":a.default_role,"status":a.status,"analysis_agent":domain} for domain in domains for a in agents.values()]
                availability=[{"agent_id":str(a.agent_id),"until":str(a.unavailable_until),"analysis_agent":domain}
                    for domain in domains for a in (await db.scalars(select(AgentAvailability))).all()]
                related=list({r["id"]:r for r in related}.values())[:20]
                await db.rollback()
                # Deterministic proof and genuine decisions must survive a model
                # outage. Apply these before making the optional contextual call.
                remaining=[]
                for entry in prepared:
                    message_id,stamp,context_hash,versions,proven=entry
                    if proven is not None or stamp is None:
                        async with AsyncSessionLocal() as apply_db:
                            if not await _apply(apply_db,run_id,token,message_id,stamp,context_hash,versions,proven):
                                return True
                    else:
                        remaining.append(entry)
                prepared=remaining
                if model_failed:
                    continue  # still inspect later batches for deterministic proof
                from app.core.message_triage_analysis import AnalysisError
                try:
                    proposals=await _analyze_with_lease(run_id,token,
                        analyze_messages(db,items,related,registry,availability)) if items else []
                except AnalysisError:
                    model_failed=True
                    continue
            suggestions={p.message_id:p for p in proposals}
            for message_id,stamp,context_hash,versions,proven in prepared:
                suggestion=proven or suggestions.get(message_id)
                async with AsyncSessionLocal() as db:
                    if suggestion is None and stamp is not None:
                        raise ValueError("Missing analysis")
                    if not await _apply(db,run_id,token,message_id,stamp,context_hash,versions,suggestion):
                        return True  # lease fenced; this worker must not keep analysing/applying
        if model_failed:
            raise ValueError("Contextual provider unavailable")
        async with AsyncSessionLocal() as db:
            run=await db.scalar(select(MessageAnalysisRun).where(MessageAnalysisRun.id==run_id).with_for_update())
            if run.lease_token==token and run.status=="running" and run.lease_until>now():
                run.status="completed"
                run.finished_at=now()
                run.lease_until=None
                await db.commit()
        from app.core.dispatch_signal import wake_scheduled_dispatch
        wake_scheduled_dispatch()
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.warning("Messages analysis %s deferred; no unverified action applied",run_id)
        async with AsyncSessionLocal() as db:
            run=await db.scalar(select(MessageAnalysisRun).where(MessageAnalysisRun.id==run_id).with_for_update())
            if run.lease_token==token and run.status=="running" and run.lease_until>now():
                run.status="failed"
                run.error=SAFE_ERROR
                run.finished_at=now()
                run.lease_until=None
                await db.commit()
    return True


async def refresh_native_availability():
    """A fresh observation removes only an older Codex usage-limit record."""
    async with AsyncSessionLocal() as db:
        agent=await db.scalar(select(Agent).where(Agent.profile_slug=="aramis",Agent.runtime_type=="codex"))
        record=await db.get(AgentAvailability,agent.id) if agent else None
        if record is None or record.recorded_by!="forgehub:usage-limit" or record.unavailable_until<=now():
            return
        agent_id,version=agent.id,record.updated_at
        await db.rollback()
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response=await client.get(settings.CHAT_BRIDGE_URL.rstrip("/")+"/v1/agent-runs/availability",
                headers={"X-Bridge-Token":settings.CHAT_BRIDGE_TOKEN})
        response.raise_for_status()
        observed=response.json()
        instant=datetime.fromisoformat(observed["observed_at"]) if observed.get("observed_at") else None
        if observed.get("available") is not True or not instant or instant.tzinfo is None or not now()-timedelta(minutes=5)<=instant<=now()+timedelta(seconds=30):
            return
    except (httpx.HTTPError,ValueError,KeyError,TypeError):
        return
    async with AsyncSessionLocal() as db:
        record=await db.scalar(select(AgentAvailability).where(AgentAvailability.agent_id==agent_id).with_for_update())
        if record and record.updated_at==version and instant>record.updated_at and record.recorded_by=="forgehub:usage-limit":
            db.add(AuditEvent(entity_type="agent",entity_id=agent_id,event_type="agent_availability_observed",
                actor="messages:triage",payload={"runtime":"codex","observed_at":instant.isoformat(),
                    "previous_until":record.unavailable_until.isoformat(),"available":True,"policy":POLICY_VERSION}))
            await db.delete(record)
            await db.commit()


async def message_triage_loop():
    if not settings.background_workers_enabled or not settings.MESSAGE_TRIAGE_ENABLED:
        return
    offset=0
    while True:
        try:
            await refresh_native_availability()
            async with AsyncSessionLocal() as db:
                # A changed linked fact also invalidates a cached decision. Bound
                # background reads; the manual job still spans its complete scope.
                rows=(await db.scalars(candidate_query().order_by(AgentDemand.created_at,AgentDemand.id).offset(offset).limit(100))).all()
                offset=offset+len(rows) if len(rows)==100 else 0
                dirty=False
                for demand in rows:
                    result=await db.get(MessageTriageResult,demand.id)
                    if result is None or result.source_fingerprint!=source_stamp(demand):
                        dirty=True
                        break
                    stamp,_=await context_stamp(db,demand,result.context_versions.get("related",{}))
                    if stamp!=result.context_fingerprint:
                        dirty=True
                        break
                latest=await db.scalar(select(MessageAnalysisRun).where(MessageAnalysisRun.scope_key==hashlib.sha256(
                    json.dumps({"agent_id":None,"context":None},sort_keys=True).encode()).hexdigest())
                    .order_by(MessageAnalysisRun.created_at.desc()).limit(1))
                # At most one automatic retry per ten minutes after provider failure.
                if dirty and (not latest or latest.status!="failed" or latest.finished_at<now()-timedelta(minutes=10)):
                    await enqueue_analysis(db,actor="messages:auto")
            await process_next_analysis()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Messages analysis maintenance failed")
        await asyncio.sleep(POLL_SECONDS)

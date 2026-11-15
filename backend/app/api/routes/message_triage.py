"""Operator commands for contextual Messages analysis; never model-owned authority."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.message_triage import AnalysisRequest, AnalysisRunOut, MessageDeliveryIn
from app.core.config import settings
from app.core.deps import get_current_admin
from app.core.message_triage import analysis_enabled, enqueue_analysis, register_delivery
from app.db.base import get_db
from app.db.models.message_triage import MessageAnalysisRun

router=APIRouter(prefix="/api/v1/demands",tags=["messages-analysis"])


@router.post("/agent-work/analyze",response_model=AnalysisRunOut,status_code=202)
async def analyze(payload:AnalysisRequest,db:AsyncSession=Depends(get_db),admin=Depends(get_current_admin)):
    if not analysis_enabled():
        raise HTTPException(503,"Contextual analysis is not enabled")
    try:
        return await enqueue_analysis(db,actor=admin.username,agent_id=payload.agent_id,context=payload.context)
    except ValueError as exc:
        raise HTTPException(422,"Invalid analysis scope") from exc


@router.get("/agent-work/triage-settings")
async def triage_settings(agent_id:uuid.UUID | None=None,context:str | None=None,
    db:AsyncSession=Depends(get_db),admin=Depends(get_current_admin)):
    """Whether "Analisar e encaminhar" can run here, so the screen can say so up front instead of
    learning it from a 503 after the click and showing an old run as if it were current (2026-11-15).

    Also what there is to analyse in this scope -- the same messages the analysis would take
    (candidate_query) and the pending questions -- so the button never runs on nothing (Marcelo,
    2026-11-15: "não faz sentido fazer a análise sem tarefas, incubada, aprovação e resposta")."""
    from sqlalchemy import func
    from app.core.message_triage import candidate_query
    from app.db.models.operations import AgentQuestion
    try:
        query=candidate_query(agent_id,context if context not in ("all","") else None)
    except ValueError as exc:
        raise HTTPException(422,"Invalid analysis scope") from exc
    pending_tasks=await db.scalar(select(func.count()).select_from(query.subquery()))
    pending_questions=await db.scalar(select(func.count(AgentQuestion.id)).where(AgentQuestion.status=="pending"))
    return {"enabled": analysis_enabled(), "gates_dispatch": settings.MESSAGE_TRIAGE_ENABLED,
            "pending_tasks": int(pending_tasks or 0), "pending_questions": int(pending_questions or 0)}


@router.get("/agent-work/analysis",response_model=AnalysisRunOut | None)
async def latest(agent_id:uuid.UUID | None=None,context:str | None=None,
    db:AsyncSession=Depends(get_db),admin=Depends(get_current_admin)):
    from app.core.message_triage import scope_filters
    import hashlib
    import json
    try:
        scope_filters(agent_id,context)
    except ValueError as exc:
        raise HTTPException(422,"Invalid analysis scope") from exc
    scope={"agent_id":str(agent_id) if agent_id else None,"context":context if context not in ("all","") else None}
    key=hashlib.sha256(json.dumps(scope,sort_keys=True).encode()).hexdigest()
    return await db.scalar(select(MessageAnalysisRun).where(MessageAnalysisRun.scope_key==key)
        .order_by(MessageAnalysisRun.created_at.desc(),MessageAnalysisRun.id).limit(1))


@router.get("/agent-work/analysis/{run_id}",response_model=AnalysisRunOut)
async def status(run_id:uuid.UUID,db:AsyncSession=Depends(get_db),admin=Depends(get_current_admin)):
    result=await db.get(MessageAnalysisRun,run_id)
    if result is None:
        raise HTTPException(404,"Analysis not found")
    return result


@router.post("/{message_id}/delivery")
async def delivery(message_id:uuid.UUID,payload:MessageDeliveryIn,
    db:AsyncSession=Depends(get_db),admin=Depends(get_current_admin)):
    from app.core.evidence_bridge import EvidenceUnverifiable
    try:
        return await register_delivery(db,message_id,payload,actor=admin.username)
    except EvidenceUnverifiable as exc:
        raise HTTPException(503,"Delivery evidence could not be verified; no completion was recorded") from exc

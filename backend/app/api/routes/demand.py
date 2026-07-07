"""Agent demand inbox routes -- "like an e-mail" agents can send ForgeHub
(a request, a finding, a proposal) that a human then reads and converts
into a Task, a Docs document, an Artifact, or a Knowledge Base note (see
core/conversions.py). Existing /root/docs notes/annotations get the same
four-way conversion menu through docs.py's /convert -- no demand row
needed for those, they already have a body (the file content).
"""
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.demand import (
    ConvertIn,
    ConvertOut,
    DemandOut,
    DemandSubmitIn,
    DemandUpdateIn,
)
from app.core import conversions
from app.core.config import settings
from app.db.base import get_db
from app.db.models.demand import AgentDemand

router = APIRouter(prefix="/api/v1/demands", tags=["demands"])


async def _get_demand_or_404(db: AsyncSession, demand_id: uuid.UUID) -> AgentDemand:
    demand = (
        await db.execute(select(AgentDemand).where(AgentDemand.id == demand_id))
    ).scalar_one_or_none()
    if demand is None:
        raise HTTPException(status_code=404, detail="Demand not found")
    return demand


@router.post("/submit", response_model=DemandOut, status_code=status.HTTP_201_CREATED)
async def submit_demand(
    payload: DemandSubmitIn,
    x_bridge_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> AgentDemand:
    """Public path (see main.py's _PUBLIC_API_PATHS) guarded by the shared
    bridge token -- the same trust boundary the chat bridge and the
    Auditor's cron trigger use, so any Hermes agent on the host can submit
    a demand with a plain curl (no user JWT available to a cron/agent)."""
    if not settings.CHAT_BRIDGE_TOKEN or x_bridge_token != settings.CHAT_BRIDGE_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid bridge token")
    demand = AgentDemand(
        from_agent=payload.from_agent, subject=payload.subject, body=payload.body
    )
    db.add(demand)
    await db.commit()
    await db.refresh(demand)
    return demand


@router.post("", response_model=DemandOut, status_code=status.HTTP_201_CREATED)
async def create_demand(
    payload: DemandSubmitIn, db: AsyncSession = Depends(get_db)
) -> AgentDemand:
    """Authenticated (JWT, normal RequireAuthMiddleware) counterpart to
    /submit's bridge-token path -- backs the chat's "/demanda" command:
    ForgeHub itself (on the logged-in user's behalf) files the agent's
    reply into the inbox, as opposed to an autonomous host-side agent
    submitting on its own."""
    demand = AgentDemand(
        from_agent=payload.from_agent, subject=payload.subject, body=payload.body
    )
    db.add(demand)
    await db.commit()
    await db.refresh(demand)
    return demand


@router.get("", response_model=list[DemandOut])
async def list_demands(
    status_filter: str | None = None, db: AsyncSession = Depends(get_db)
) -> list[AgentDemand]:
    query = select(AgentDemand).order_by(AgentDemand.created_at.desc())
    if status_filter is not None:
        query = query.where(AgentDemand.status == status_filter)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.patch("/{demand_id}", response_model=DemandOut)
async def update_demand(
    demand_id: uuid.UUID, payload: DemandUpdateIn, db: AsyncSession = Depends(get_db)
) -> AgentDemand:
    demand = await _get_demand_or_404(db, demand_id)
    demand.status = payload.status
    await db.commit()
    await db.refresh(demand)
    return demand


@router.delete("/{demand_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_demand(demand_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    demand = await _get_demand_or_404(db, demand_id)
    await db.delete(demand)
    await db.commit()


@router.post("/{demand_id}/convert", response_model=ConvertOut)
async def convert_demand(
    demand_id: uuid.UUID, payload: ConvertIn, db: AsyncSession = Depends(get_db)
) -> ConvertOut:
    demand = await _get_demand_or_404(db, demand_id)
    title = payload.title or demand.subject

    try:
        if payload.target == "task":
            if payload.planning_item_id is None:
                raise HTTPException(400, "planning_item_id is required for target=task")
            entity_id, reference = await conversions.convert_to_task(
                db, title=title, content=demand.body, planning_item_id=payload.planning_item_id
            )
        elif payload.target == "doc":
            if not payload.path:
                raise HTTPException(400, "path is required for target=doc")
            reference = await conversions.convert_to_doc(path=payload.path, content=demand.body)
            entity_id = None
        elif payload.target == "artifact":
            if not payload.artifact_type:
                raise HTTPException(400, "artifact_type is required for target=artifact")
            doc_path = payload.path or f"anotacoes/demandas/{demand.id}.md"
            entity_id, reference = await conversions.convert_to_artifact(
                db,
                name=title,
                content=demand.body,
                artifact_type=payload.artifact_type,
                doc_path=doc_path,
            )
        else:  # knowledge_base
            if not payload.path:
                raise HTTPException(400, "path is required for target=knowledge_base")
            reference = await conversions.convert_to_knowledge_base(
                path=payload.path, content=demand.body
            )
            entity_id = None
    except conversions.ConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    demand.status = "converted"
    demand.converted_entity_type = payload.target
    demand.converted_reference = reference
    await db.commit()

    return ConvertOut(
        entity_type=payload.target,
        entity_id=str(entity_id) if entity_id else None,
        reference=reference,
    )

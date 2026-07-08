"""Agent demand inbox routes -- ForgeHub's "console de desenvolvimento"
intake: agents (and the logged-in user, via the compose path) send a
note here, a human reads it and converts it into a Task, a Docs document,
an Artifact, a Knowledge Base note, or straight into project work (a new
planning item, a project-linked doc, or a "task avulsa" shortcut that
creates a planning item + task together) -- see core/conversions.py for
the full CONVERT_TARGETS list. Existing /root/docs notes/annotations get
the same conversion menu through docs.py's /convert -- no demand row
needed for those, they already have a body (the file content).
"""
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.demand import (
    ConvertIn,
    ConvertOut,
    DemandAttachmentOut,
    DemandOut,
    DemandSubmitIn,
    DemandUpdateIn,
)
from app.core import conversions
from app.core.config import settings
from app.core.markdown_docs import resolve_doc_path
from app.db.base import get_db
from app.db.models.backlog import PLANNING_ITEM_TYPES
from app.db.models.demand import AgentDemand, DemandAttachment
from app.db.models.notification import Notification

router = APIRouter(prefix="/api/v1/demands", tags=["demands"])

# Same mount docs.py writes under -- attachments live in their own
# subfolder so they don't clutter the user-browsable Docs tree.
DOCS_ROOT = Path("/docs")
ATTACHMENTS_SUBDIR = "anexos/demandas"
MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024


async def _get_demand_or_404(db: AsyncSession, demand_id: uuid.UUID) -> AgentDemand:
    demand = (
        await db.execute(select(AgentDemand).where(AgentDemand.id == demand_id))
    ).scalar_one_or_none()
    if demand is None:
        raise HTTPException(status_code=404, detail="Demand not found")
    return demand


def _demand_preview(body: str, limit: int = 200) -> str:
    body = body.strip()
    return body if len(body) <= limit else f"{body[:limit].rstrip()}…"


async def _create_demand_and_notify(db: AsyncSession, payload: DemandSubmitIn) -> AgentDemand:
    """Every new inbox item also surfaces in the system Notifications bell
    (source="system", not "cron") -- so arriving mail doesn't go unnoticed
    unless the user happens to have the Inbox page open. event_key is
    demand-id-scoped so re-notifying the same demand is impossible."""
    demand = AgentDemand(
        from_agent=payload.from_agent, subject=payload.subject, body=payload.body
    )
    db.add(demand)
    await db.flush()  # assigns demand.id (Python-side default) before the notification references it

    notification = Notification(
        source="system",
        severity="info",
        title=f"Novo no Inbox: {demand.subject}",
        message=_demand_preview(payload.body),
        event_key=f"demand:{demand.id}",
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(notification)

    await db.commit()
    await db.refresh(demand)
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
    return await _create_demand_and_notify(db, payload)


@router.post("", response_model=DemandOut, status_code=status.HTTP_201_CREATED)
async def create_demand(
    payload: DemandSubmitIn, db: AsyncSession = Depends(get_db)
) -> AgentDemand:
    """Authenticated (JWT, normal RequireAuthMiddleware) counterpart to
    /submit's bridge-token path -- backs the chat's "/demanda" command:
    ForgeHub itself (on the logged-in user's behalf) files the agent's
    reply into the inbox, as opposed to an autonomous host-side agent
    submitting on its own."""
    return await _create_demand_and_notify(db, payload)


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


@router.post("/{demand_id}/attachments", response_model=DemandAttachmentOut, status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    demand_id: uuid.UUID, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)
) -> DemandAttachment:
    demand = await _get_demand_or_404(db, demand_id)
    name = Path(file.filename or "").name
    if not name:
        raise HTTPException(status_code=400, detail="Missing filename")
    content = await file.read()
    if len(content) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the 50MB upload limit")
    rel_path = f"{ATTACHMENTS_SUBDIR}/{demand.id}/{name}"
    target = resolve_doc_path(DOCS_ROOT, rel_path)
    if target is None:
        raise HTTPException(status_code=400, detail="Invalid filename")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    attachment = DemandAttachment(
        demand_id=demand.id,
        filename=name,
        path=rel_path,
        size_bytes=len(content),
        content_type=file.content_type,
    )
    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)
    return attachment


@router.get("/{demand_id}/attachments/{attachment_id}/download")
async def download_attachment(
    demand_id: uuid.UUID, attachment_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> FileResponse:
    attachment = (
        await db.execute(
            select(DemandAttachment).where(
                DemandAttachment.id == attachment_id, DemandAttachment.demand_id == demand_id
            )
        )
    ).scalar_one_or_none()
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    target = resolve_doc_path(DOCS_ROOT, attachment.path)
    if target is None or not target.is_file():
        raise HTTPException(status_code=404, detail="Attachment file missing on disk")
    return FileResponse(target, filename=attachment.filename)


@router.delete("/{demand_id}/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attachment(
    demand_id: uuid.UUID, attachment_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> None:
    attachment = (
        await db.execute(
            select(DemandAttachment).where(
                DemandAttachment.id == attachment_id, DemandAttachment.demand_id == demand_id
            )
        )
    ).scalar_one_or_none()
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    target = resolve_doc_path(DOCS_ROOT, attachment.path)
    if target is not None and target.is_file():
        target.unlink()
    await db.delete(attachment)
    await db.commit()


@router.post("/{demand_id}/notify-telegram")
async def notify_telegram(demand_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """"Encaminhar pro Telegram": proxies the host-bridge's
    /v1/messages/send (see host-bridge/send_message.py), which forwards
    through Hermes's already-configured cross-channel gateway -- no
    target/chat_id needed, "telegram" alone resolves to the home channel
    (the user's own Telegram) via ~/.hermes/config.yaml."""
    demand = await _get_demand_or_404(db, demand_id)
    text = f"*{demand.subject}*\n\n{demand.body}"[:4000]
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{settings.CHAT_BRIDGE_URL}/v1/messages/send",
            headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
            json={"target": "telegram", "message": text},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Host-bridge error: {resp.text[:500]}")
    return resp.json()


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
        elif payload.target == "knowledge_base":
            if not payload.path:
                raise HTTPException(400, "path is required for target=knowledge_base")
            reference = await conversions.convert_to_knowledge_base(
                path=payload.path, content=demand.body
            )
            entity_id = None
        elif payload.target == "planning_item":
            if payload.project_id is None:
                raise HTTPException(400, "project_id is required for target=planning_item")
            item_type = payload.item_type or conversions.DEFAULT_ITEM_TYPE
            if item_type not in PLANNING_ITEM_TYPES:
                raise HTTPException(400, f"item_type must be one of {PLANNING_ITEM_TYPES}")
            entity_id, reference = await conversions.convert_to_planning_item(
                db, title=title, content=demand.body, project_id=payload.project_id, item_type=item_type
            )
        elif payload.target == "project_doc":
            if payload.project_id is None:
                raise HTTPException(400, "project_id is required for target=project_doc")
            doc_path = payload.path or f"projetos/{payload.project_id}/{demand.id}.md"
            reference = await conversions.convert_to_project_doc(
                db, project_id=payload.project_id, path=doc_path, content=demand.body
            )
            entity_id = None
        else:  # quick_task
            if payload.project_id is None:
                raise HTTPException(400, "project_id is required for target=quick_task")
            item_type = payload.item_type or conversions.DEFAULT_ITEM_TYPE
            if item_type not in PLANNING_ITEM_TYPES:
                raise HTTPException(400, f"item_type must be one of {PLANNING_ITEM_TYPES}")
            entity_id, reference = await conversions.convert_to_quick_task(
                db, title=title, content=demand.body, project_id=payload.project_id, item_type=item_type
            )
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

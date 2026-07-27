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
import json
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
    DemandGroupCreateIn,
    DemandGroupOut,
    DemandGroupUpdateIn,
    DemandOut,
    DemandSubmitIn,
    DemandUpdateIn,
    DispatchIn,
    DispatchStatusOut,
)
from app.core import conversions
from app.core.agent_runs import AgentRunDispatchError, dispatch_agent_run, poll_agent_run
from app.core.config import settings
from app.core.demand_thread import build_thread_prompt
from app.core.markdown_docs import resolve_doc_path
from app.db.base import get_db
from app.db.models.agent import Agent
from app.db.models.backlog import PLANNING_ITEM_TYPES
from app.db.models.demand import AgentDemand, DemandAttachment, DemandGroup
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


async def _get_agent_or_404(db: AsyncSession, agent_id: uuid.UUID) -> Agent:
    agent = await db.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


async def _get_group_or_404(db: AsyncSession, group_id: uuid.UUID) -> DemandGroup:
    group = (
        await db.execute(select(DemandGroup).where(DemandGroup.id == group_id))
    ).scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=404, detail="Demand group not found")
    return group


async def _would_create_cycle(db: AsyncSession, group_id: uuid.UUID, new_parent_id: uuid.UUID) -> bool:
    """True if reparenting `group_id` under `new_parent_id` would create a
    cycle -- walks up from new_parent_id toward the root, bailing out if it
    reaches group_id itself (moving a folder into its own descendant)."""
    current_id: uuid.UUID | None = new_parent_id
    while current_id is not None:
        if current_id == group_id:
            return True
        current_id = (
            await db.execute(select(DemandGroup.parent_id).where(DemandGroup.id == current_id))
        ).scalar_one_or_none()
    return False


def _demand_preview(body: str, limit: int = 200) -> str:
    body = body.strip()
    return body if len(body) <= limit else f"{body[:limit].rstrip()}…"


async def create_demand_and_notify(db: AsyncSession, payload: DemandSubmitIn) -> AgentDemand:
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
        title=f"New in Inbox: {demand.subject}",
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
    return await create_demand_and_notify(db, payload)


@router.post("", response_model=DemandOut, status_code=status.HTTP_201_CREATED)
async def create_demand(
    payload: DemandSubmitIn, db: AsyncSession = Depends(get_db)
) -> AgentDemand:
    """Authenticated (JWT, normal RequireAuthMiddleware) counterpart to
    /submit's bridge-token path -- backs the chat's "/demanda" command:
    ForgeHub itself (on the logged-in user's behalf) files the agent's
    reply into the inbox, as opposed to an autonomous host-side agent
    submitting on its own."""
    return await create_demand_and_notify(db, payload)


@router.get("", response_model=list[DemandOut])
async def list_demands(
    status_filter: str | None = None, db: AsyncSession = Depends(get_db)
) -> list[AgentDemand]:
    query = select(AgentDemand).order_by(AgentDemand.created_at.desc())
    if status_filter is not None:
        query = query.where(AgentDemand.status == status_filter)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/groups", response_model=list[DemandGroupOut])
async def list_demand_groups(db: AsyncSession = Depends(get_db)) -> list[DemandGroup]:
    """Flat list -- the frontend builds the tree from parent_id, same as
    DocTree builds its tree from filesystem path segments."""
    result = await db.execute(select(DemandGroup).order_by(DemandGroup.name))
    return list(result.scalars().all())


@router.post("/groups", response_model=DemandGroupOut, status_code=status.HTTP_201_CREATED)
async def create_demand_group(
    payload: DemandGroupCreateIn, db: AsyncSession = Depends(get_db)
) -> DemandGroup:
    if payload.parent_id is not None:
        await _get_group_or_404(db, payload.parent_id)
    group = DemandGroup(name=payload.name, parent_id=payload.parent_id)
    db.add(group)
    await db.commit()
    await db.refresh(group)
    return group


@router.patch("/groups/{group_id}", response_model=DemandGroupOut)
async def update_demand_group(
    group_id: uuid.UUID, payload: DemandGroupUpdateIn, db: AsyncSession = Depends(get_db)
) -> DemandGroup:
    """Rename and/or reparent (drag a folder onto another folder, or onto
    the Arquivados root by sending parent_id: null explicitly)."""
    group = await _get_group_or_404(db, group_id)
    data = payload.model_dump(exclude_unset=True)
    if "parent_id" in data:
        new_parent_id = data["parent_id"]
        if new_parent_id is not None:
            await _get_group_or_404(db, new_parent_id)
            if await _would_create_cycle(db, group_id, new_parent_id):
                raise HTTPException(status_code=400, detail="Cannot move a folder into its own descendant")
        group.parent_id = new_parent_id
    if "name" in data:
        group.name = data["name"]
    await db.commit()
    await db.refresh(group)
    return group


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_demand_group(group_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    """Cascades to subfolders (DemandGroup.parent_id's ondelete=CASCADE);
    demands filed directly under this folder fall back to the Arquivados
    root instead of being deleted (AgentDemand.group_id's ondelete=SET NULL)."""
    group = await _get_group_or_404(db, group_id)
    await db.delete(group)
    await db.commit()


@router.patch("/{demand_id}", response_model=DemandOut)
async def update_demand(
    demand_id: uuid.UUID, payload: DemandUpdateIn, db: AsyncSession = Depends(get_db)
) -> AgentDemand:
    demand = await _get_demand_or_404(db, demand_id)
    data = payload.model_dump(exclude_unset=True)
    if "group_id" in data:
        if data["group_id"] is not None:
            await _get_group_or_404(db, data["group_id"])
        demand.group_id = data["group_id"]
    if "target_agent_id" in data:
        if data["target_agent_id"] is not None:
            await _get_agent_or_404(db, data["target_agent_id"])
        demand.target_agent_id = data["target_agent_id"]
    if "status" in data:
        demand.status = data["status"]
    elif "group_id" in data and data["group_id"] is not None:
        # Filing a demand into an Arquivados subfolder always archives it,
        # even if the caller only sent group_id (the Inbox drag-and-drop
        # case -- see InboxGroupTree's drop handler).
        demand.status = "archived"
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


def _extract_run_result_text(run: dict[str, Any]) -> str:
    """Best-effort human-readable text from a finished agent-runs output.
    `claude --output-format json` returns one JSON object with a "result"
    field (verified against a real run 2026-07-23) -- other runtimes'
    formats weren't exercised yet, so this falls back to the raw
    output/error rather than guessing at their shape."""
    output = (run.get("output") or "").strip()
    if output:
        try:
            parsed = json.loads(output)
            if isinstance(parsed, dict) and isinstance(parsed.get("result"), str):
                return parsed["result"]
        except (json.JSONDecodeError, ValueError):
            pass
    return output or (run.get("error") or "").strip() or "(no output)"


async def _send_notice(text: str) -> None:
    """Best-effort Telegram notice for an "independent" dispatch (§5 of the
    dispatch proposal) -- same proxy notify_telegram above already uses.
    Never blocks/fails the dispatch itself: the run already started, a
    notice delivery hiccup shouldn't roll that back."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            await client.post(
                f"{settings.CHAT_BRIDGE_URL}/v1/messages/send",
                headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
                json={"target": "telegram", "message": text[:4000]},
            )
    except httpx.HTTPError:
        pass


@router.post("/{demand_id}/dispatch", response_model=DemandOut)
async def dispatch_demand(
    demand_id: uuid.UUID, payload: DispatchIn, db: AsyncSession = Depends(get_db)
) -> AgentDemand:
    """Sends this item's context (+ Marcelo's command_text, if any) as a
    prompt to a target agent's CLI via the host-bridge's governed runner
    (app/core/agent_runs.py). Never blocks: the dispatch always proceeds:
    a Telegram notice is sent only when the action is "independent" --
    see PROPOSTA-INBOX-DISPATCH-E-DIALOGO-ENTRE-AGENTES.md §5 for the full
    governance model this implements."""
    demand = await _get_demand_or_404(db, demand_id)

    if payload.reply_to_sender:
        if payload.target_agent_id is not None:
            raise HTTPException(400, "Send either target_agent_id or reply_to_sender, not both")
        if demand.from_agent_id is None:
            raise HTTPException(400, "This item has no registered agent sender to reply to")
        target_agent_id = demand.from_agent_id
    else:
        if payload.target_agent_id is None:
            raise HTTPException(400, "target_agent_id or reply_to_sender is required")
        target_agent_id = payload.target_agent_id

    agent = await _get_agent_or_404(db, target_agent_id)

    # Independent vs. descendant: no origin, a task origin (not yet
    # cross-referenced against an assignee -- v1 always treats these as
    # independent), or an origin dispatched to a DIFFERENT agent all count
    # as independent. Staying with the same already-notified target agent
    # never re-notifies.
    independent = True
    if demand.origin_type == "demand" and demand.origin_id is not None:
        origin = await db.get(AgentDemand, demand.origin_id)
        if origin is not None and origin.target_agent_id == target_agent_id:
            independent = False

    prompt = await build_thread_prompt(db, demand, payload.command_text)
    project_path = settings.AGENT_RUNTIME_PATHS.get(agent.runtime_type, "/root")

    run_id = str(uuid.uuid4())
    try:
        run = await dispatch_agent_run(run_id, agent, prompt, project_path)
    except AgentRunDispatchError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Host-bridge dispatch failed: {exc}") from exc

    demand.target_agent_id = target_agent_id
    demand.command_text = payload.command_text
    demand.agent_run_id = run["run_id"]
    demand.dispatch_status = "dispatched"

    if independent and not demand.notice_sent:
        await _send_notice(f"*Disparo para {agent.name}*\n\n{prompt}")
        demand.notice_sent = True

    await db.commit()
    await db.refresh(demand)
    return demand


@router.get("/{demand_id}/dispatch-status", response_model=DispatchStatusOut)
async def get_dispatch_status(
    demand_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> DispatchStatusOut:
    """Polled by the frontend while a dispatch is dispatched/running.
    Idempotent past the first terminal poll -- the reply item is only
    created once (dispatch_status flips to completed/failed exactly once)."""
    demand = await _get_demand_or_404(db, demand_id)
    if demand.agent_run_id is None:
        raise HTTPException(status_code=400, detail="This item has not been dispatched")

    if demand.dispatch_status in ("completed", "failed"):
        return DispatchStatusOut(dispatch_status=demand.dispatch_status, agent_run_id=demand.agent_run_id)

    try:
        run = await poll_agent_run(demand.agent_run_id)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Host-bridge poll failed: {exc}") from exc

    run_status = run.get("status")
    if run_status in ("starting", "running"):
        demand.dispatch_status = "running"
        await db.commit()
        return DispatchStatusOut(dispatch_status=demand.dispatch_status, agent_run_id=demand.agent_run_id)

    # Terminal: completed / failed / timed_out / cancelled / stale.
    demand.dispatch_status = "completed" if run_status == "completed" else "failed"

    agent = await db.get(Agent, demand.target_agent_id) if demand.target_agent_id else None
    reply_body = _extract_run_result_text(run)
    reply = AgentDemand(
        from_agent=agent.name if agent else "agent",
        from_agent_id=demand.target_agent_id,
        subject=f"Re: {demand.subject}",
        body=reply_body,
        origin_type="demand",
        origin_id=demand.id,
    )
    db.add(reply)
    await db.flush()

    db.add(Notification(
        source="system",
        severity="info",
        title=f"Reply in Inbox: {reply.subject}",
        message=_demand_preview(reply_body),
        event_key=f"demand-reply:{demand.id}",
        occurred_at=datetime.now(timezone.utc),
    ))

    await db.commit()
    await db.refresh(reply)
    return DispatchStatusOut(
        dispatch_status=demand.dispatch_status,
        agent_run_id=demand.agent_run_id,
        reply_demand_id=reply.id,
    )


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
            doc_root = (
                await conversions.resolve_area_root(db, payload.area_id)
                if payload.area_id is not None
                else conversions.DOCS_ROOT
            )
            reference = await conversions.convert_to_doc(path=payload.path, content=demand.body, root=doc_root)
            entity_id = None
            if demand.attachments:
                # Attached files land next to the note itself, not just the
                # markdown body -- see copy_attachments_to_folder's docstring.
                await conversions.copy_attachments_to_folder(
                    attachments=[(a.filename, a.path) for a in demand.attachments],
                    dest_path=payload.path,
                    dest_root=doc_root,
                )
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

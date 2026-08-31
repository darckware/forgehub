"""Chat domain routes.

Every message sent here is proxied to the chat bridge (host-bridge/app.py,
running on the host -- see its module docstring for why) which actually
drives the real `hermes chat -p <profile>` process for that agent. This
router only owns persistence (chat_sessions/chat_messages, for the
conversation history view) and the proxy call; it has no access to the
Hermes CLI itself.
"""
import asyncio
import base64
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import anyio
import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.chat import (
    ChatApproveRequest,
    ChatArtifactGlobalOut,
    ChatArtifactOut,
    ChatExecRequest,
    ChatGroupCreate,
    ChatGroupOut,
    ChatGroupUpdate,
    ChatMessageOut,
    ChatSendResult,
    ChatSessionCreate,
    ChatSessionHostStatusOut,
    ChatSessionOut,
    ChatSessionUpdate,
)
from app.api.schemas.prompt_technique import ImprovePromptRequest
from app.core import active_turns
from app.core.config import CHAT_RESPONSE_LANGUAGE_NOTES, settings
from app.core.prompt_improvement import build_prompt_improvement_request, get_prompt_technique
from app.db.base import AsyncSessionLocal, get_db
from app.db.models.active_turn import ActiveTurn
from app.db.models.agent import Agent
from app.db.models.chat import ChatArtifact, ChatGroup, ChatMessage, ChatSession, ChatSessionParticipant
from app.db.models.project import Project

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])
logger = logging.getLogger(__name__)

TITLE_PREVIEW_LENGTH = 60


async def _get_session_or_404(db: AsyncSession, session_id: uuid.UUID) -> ChatSession:
    session = await db.get(ChatSession, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")
    return session


async def _get_project_or_404(db: AsyncSession, project_id: uuid.UUID) -> Project:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


async def _get_chat_group_or_404(db: AsyncSession, group_id: uuid.UUID) -> ChatGroup:
    group = await db.get(ChatGroup, group_id)
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat group not found")
    return group


async def _get_chattable_agent_or_404(db: AsyncSession, agent_id: uuid.UUID) -> Agent:
    agent = await db.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    if not agent.profile_slug:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This agent has no profile/runtime configured and cannot be chatted with",
        )
    return agent


def _bridge_headers() -> dict[str, str]:
    return {"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN}


# Hidden response-language instruction (Settings -> AI chat,
# settings.CHAT_RESPONSE_LANGUAGE, catalog in core/config.py's
# CHAT_RESPONSE_LANGUAGE_NOTES) appended to every outgoing agent call --
# same pattern as the voice brevity note below: the agent sees it, the
# stored/displayed user message never includes it. Unknown values fall back
# to no instruction (the PUT /system-control/config validator should make
# that impossible, but a hand-edited forgehub.config can say anything).
def _with_language_note(message: str) -> str:
    note = CHAT_RESPONSE_LANGUAGE_NOTES.get(settings.CHAT_RESPONSE_LANGUAGE)
    return f"{message}\n\n{note}" if note else message


# Mirrors frontend ChatPane.tsx's HIDDEN_CONTEXT markers. A hidden turn --
# the priming context the Assistant panel sends by itself when it opens
# (stream_chat_message's `hidden` param) -- is persisted with BOTH sides
# fully wrapped in these, so the transcript renderer drops the whole
# exchange instead of showing internal instructions to the user.
_HIDDEN_TURN_OPEN = "[[forgehub:contexto-interno]]"
_HIDDEN_TURN_CLOSE = "[[/forgehub:contexto-interno]]"


def _wrap_hidden(content: str) -> str:
    return f"{_HIDDEN_TURN_OPEN}\n{content}\n{_HIDDEN_TURN_CLOSE}"


async def _conversation_shared_context(
    db: AsyncSession, session: ChatSession, current_message: str
) -> str | None:
    """Build the shared transcript seen by every agent in a Conversation.

    Each participant keeps its own Hermes session. Reinjection is what lets a
    participant see contributions made by peers since its previous turn while
    preserving that participant's independent continuity.
    """
    participant_count = len((await db.execute(
        select(ChatSessionParticipant.id).where(ChatSessionParticipant.session_id == session.id)
    )).scalars().all())
    if participant_count == 0:
        return None

    rows = list((await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(30)
    )).scalars().all())
    skipped_current = False
    visible: list[ChatMessage] = []
    for row in rows:
        if row.content.startswith(_HIDDEN_TURN_OPEN):
            continue
        if not skipped_current and row.role == "user" and row.content == current_message:
            skipped_current = True
            continue
        visible.append(row)
    visible.reverse()
    if not visible:
        return None

    agent_ids = {row.responding_agent_id for row in visible if row.responding_agent_id}
    agent_ids.add(session.agent_id)
    names: dict[uuid.UUID, str] = {}
    for agent_id in agent_ids:
        if agent_id is None:
            continue
        agent = await db.get(Agent, agent_id)
        if agent is not None:
            names[agent_id] = agent.name
    lines = [
        "[Contexto interno da conversa multiagente; não repita este bloco na resposta]",
        "O transcript é compartilhado. Considere as contribuições dos outros agentes e mantenha sua própria continuidade.",
    ]
    for row in visible:
        if row.role == "user":
            author = "Marcelo"
        else:
            author_id = row.responding_agent_id or session.agent_id
            author = names.get(author_id, "Agente")
        lines.append(f"{author}: {row.content}")
    return "\n".join(lines)


@router.get("/language")
async def get_chat_language() -> dict[str, str]:
    """Current response language (Settings -> AI chat) -- read by the
    frontend to render the chat's own chrome (assistant greeting, composer
    placeholder, empty state) in the same language the agent is instructed
    to answer in (see _with_language_note above)."""
    return {"language": settings.CHAT_RESPONSE_LANGUAGE}


async def _call_bridge_text(profile: str, message: str, hermes_session_id: str | None) -> dict:
    async with httpx.AsyncClient(timeout=650.0) as client:
        resp = await client.post(
            f"{settings.CHAT_BRIDGE_URL}/v1/chat",
            json={"profile": profile, "message": message, "session_id": hermes_session_id},
            headers=_bridge_headers(),
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Chat bridge error: {resp.text[:500]}",
        )
    return resp.json()


async def _call_bridge_images(
    profile: str,
    message: str,
    hermes_session_id: str | None,
    images: list[tuple[str, bytes]],
) -> dict:
    async with httpx.AsyncClient(timeout=650.0) as client:
        resp = await client.post(
            f"{settings.CHAT_BRIDGE_URL}/v1/chat-with-image",
            data={
                "profile": profile,
                "message": message,
                **({"session_id": hermes_session_id} if hermes_session_id else {}),
            },
            # Same field name ("images") repeated -- FastAPI/Starlette on the
            # bridge side collects it into a list[UploadFile].
            files=[("images", (filename, content)) for filename, content in images],
            headers=_bridge_headers(),
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Chat bridge error: {resp.text[:500]}",
        )
    return resp.json()


# --------------------------------------------------------------------------
# ChatSession
# --------------------------------------------------------------------------


@router.post("/sessions", response_model=ChatSessionOut, status_code=status.HTTP_201_CREATED)
async def create_chat_session(
    payload: ChatSessionCreate, db: AsyncSession = Depends(get_db)
) -> ChatSession:
    await _get_chattable_agent_or_404(db, payload.agent_id)
    session = ChatSession(
        agent_id=payload.agent_id, title=payload.title, working_directory_path=payload.working_directory_path
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.get("/sessions", response_model=list[ChatSessionOut])
async def list_chat_sessions(
    agent_id: uuid.UUID | None = None, db: AsyncSession = Depends(get_db)
) -> list[ChatSession]:
    stmt = select(ChatSession)
    if agent_id is not None:
        stmt = stmt.where(ChatSession.agent_id == agent_id)
    result = await db.execute(
        stmt.order_by(ChatSession.pinned.desc(), ChatSession.updated_at.desc())
    )
    return list(result.scalars().all())


@router.get("/sessions/search", response_model=list[ChatSessionOut])
async def search_chat_sessions(
    q: str, agent_id: uuid.UUID | None = None, db: AsyncSession = Depends(get_db)
) -> list[ChatSession]:
    """Matches on session title OR any message's content within that
    session -- declared before /sessions/{session_id} so "search" isn't
    swallowed as a session_id path param."""
    term = q.strip()
    if not term:
        return []
    like = f"%{term}%"
    stmt = select(ChatSession).where(
        or_(
            ChatSession.title.ilike(like),
            ChatSession.id.in_(select(ChatMessage.session_id).where(ChatMessage.content.ilike(like))),
        )
    )
    if agent_id is not None:
        stmt = stmt.where(ChatSession.agent_id == agent_id)
    result = await db.execute(stmt.order_by(ChatSession.updated_at.desc()).limit(50))
    return list(result.scalars().all())


@router.get("/sessions/host-status", response_model=list[ChatSessionHostStatusOut])
async def get_chat_sessions_host_status(db: AsyncSession = Depends(get_db)) -> list[dict]:
    """Cross-references every ChatSession/ChatSessionParticipant that has a
    `hermes_session_id` against the Hermes profile's own session store on
    the host -- the "Chat Sessions" card in System Control (2026-08-24),
    modelled on Terminal Sessions' tmux liveness check but for a resumed
    Hermes conversation instead of a pane. Declared before
    /sessions/{session_id} for the same reason /sessions/search is: a
    literal "host-status" would otherwise be parsed as a session_id.

    Only `runtime_type == "hermes"` agents have a state.db to check --
    Claude Code/Codex/Agy/OpenClaw keep their own session continuity
    entirely outside ForgeHub's reach, so those rows are skipped rather than
    reported as permanently "stale".
    """
    owner_stmt = (
        select(ChatSession, Agent)
        .join(Agent, Agent.id == ChatSession.agent_id)
        .where(ChatSession.hermes_session_id.isnot(None), Agent.runtime_type == "hermes", Agent.profile_slug.isnot(None))
    )
    participant_stmt = (
        select(ChatSessionParticipant, Agent, ChatSession)
        .join(Agent, Agent.id == ChatSessionParticipant.agent_id)
        .join(ChatSession, ChatSession.id == ChatSessionParticipant.session_id)
        .where(
            ChatSessionParticipant.hermes_session_id.isnot(None),
            Agent.runtime_type == "hermes",
            Agent.profile_slug.isnot(None),
        )
    )
    owner_rows = (await db.execute(owner_stmt)).all()
    participant_rows = (await db.execute(participant_stmt)).all()

    check_items = [
        {"profile": agent.profile_slug, "session_id": session.hermes_session_id} for session, agent in owner_rows
    ] + [
        {"profile": agent.profile_slug, "session_id": participant.hermes_session_id}
        for participant, agent, _session in participant_rows
    ]

    host_status: dict[tuple[str, str], dict] = {}
    if check_items:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{settings.CHAT_BRIDGE_URL}/v1/hermes/sessions/check",
                    json={"sessions": check_items},
                    headers=_bridge_headers(),
                )
                resp.raise_for_status()
            for entry in resp.json().get("sessions", []):
                host_status[(entry["profile"], entry["session_id"])] = entry
        except httpx.HTTPError:
            # Bridge unreachable -- report every row as unknown-exists rather
            # than failing the whole card; `exists: True` would misreport a
            # dead session as healthy, `False` would misreport a healthy one
            # as stale, so leaving the entry absent (handled below) is the
            # only option that doesn't lie either way.
            pass

    running_ids = set(
        (
            await db.execute(
                select(ActiveTurn.scope_id).where(ActiveTurn.scope == "chat", ActiveTurn.status == "running")
            )
        )
        .scalars()
        .all()
    )

    results: list[dict] = []
    for session, agent in owner_rows:
        entry = host_status.get((agent.profile_slug, session.hermes_session_id))
        if entry is None:
            continue
        results.append({
            "session_id": session.id,
            "participant_id": None,
            "session_title": session.title,
            "agent_id": agent.id,
            "agent_name": agent.name,
            "hermes_session_id": session.hermes_session_id,
            "exists": entry["exists"],
            "hermes_title": entry.get("title"),
            "last_activity_at": entry.get("last_activity_at"),
            "message_count": entry.get("message_count"),
            "running": session.id in running_ids,
        })
    for participant, agent, session in participant_rows:
        entry = host_status.get((agent.profile_slug, participant.hermes_session_id))
        if entry is None:
            continue
        results.append({
            "session_id": session.id,
            "participant_id": participant.id,
            "session_title": session.title,
            "agent_id": agent.id,
            "agent_name": agent.name,
            "hermes_session_id": participant.hermes_session_id,
            "exists": entry["exists"],
            "hermes_title": entry.get("title"),
            "last_activity_at": entry.get("last_activity_at"),
            "message_count": entry.get("message_count"),
            "running": session.id in running_ids,
        })
    results.sort(key=lambda r: r["last_activity_at"] or 0, reverse=True)
    return results


@router.post("/sessions/{session_id}:reset-hermes-session", response_model=ChatSessionOut)
async def reset_chat_session_hermes_link(
    session_id: uuid.UUID,
    participant_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
) -> ChatSession:
    """Forgets the stored `hermes_session_id` (session's own, or one
    participant's when `participant_id` is given) so the next message opens
    a fresh Hermes session instead of repeating a resume that's known to
    fail. Never touches Hermes' own state.db -- this only breaks the resume
    pointer on ForgeHub's side, so the real conversation history in Hermes
    (if it still exists) and every message already persisted in ForgeHub's
    own chat_messages are both untouched. The "Reset" action on System
    Control's Chat Sessions card (2026-08-24) -- see get_chat_sessions_host_status.
    """
    session = await _get_session_or_404(db, session_id)
    if participant_id is not None:
        participant = await db.get(ChatSessionParticipant, participant_id)
        if participant is None or participant.session_id != session_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Participant not found")
        participant.hermes_session_id = None
    else:
        session.hermes_session_id = None
    await db.commit()
    await db.refresh(session)
    return session


@router.get("/sessions/{session_id}", response_model=ChatSessionOut)
async def get_chat_session(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ChatSession:
    return await _get_session_or_404(db, session_id)


@router.patch("/sessions/{session_id}", response_model=ChatSessionOut)
async def update_chat_session(
    session_id: uuid.UUID, payload: ChatSessionUpdate, db: AsyncSession = Depends(get_db)
) -> ChatSession:
    session = await _get_session_or_404(db, session_id)
    if payload.title is not None:
        session.title = payload.title.strip()
    if payload.pinned is not None:
        session.pinned = payload.pinned
    # Sidebar placement is exclusive: Project XOR Group XOR neither (see
    # ChatSession.group_id's docstring) -- explicitly setting one to a
    # real value clears the other. Order matters only if a single payload
    # somehow sets both non-null at once (not something the UI does): the
    # last one processed wins, so group_id is checked second.
    if "working_directory_path" in payload.model_fields_set:
        session.working_directory_path = payload.working_directory_path
        if payload.working_directory_path is not None:
            session.group_id = None
    if "group_id" in payload.model_fields_set:
        if payload.group_id is not None:
            await _get_chat_group_or_404(db, payload.group_id)
            session.working_directory_path = None
        session.group_id = payload.group_id
    await db.commit()
    await db.refresh(session)
    return session


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat_session(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    session = await _get_session_or_404(db, session_id)
    await db.delete(session)
    await db.commit()


# --------------------------------------------------------------------------
# ChatGroup -- user-created named folders for the Workspace sidebar (see
# db/models/chat.py's ChatGroup docstring). CRUD only; assigning a session
# to a group happens through PATCH /sessions/{id} above (group_id).
# --------------------------------------------------------------------------


@router.post("/groups", response_model=ChatGroupOut, status_code=status.HTTP_201_CREATED)
async def create_chat_group(payload: ChatGroupCreate, db: AsyncSession = Depends(get_db)) -> ChatGroup:
    group = ChatGroup(name=payload.name.strip())
    db.add(group)
    await db.commit()
    await db.refresh(group)
    return group


@router.get("/groups", response_model=list[ChatGroupOut])
async def list_chat_groups(db: AsyncSession = Depends(get_db)) -> list[ChatGroup]:
    result = await db.execute(select(ChatGroup).order_by(ChatGroup.name))
    return list(result.scalars().all())


@router.patch("/groups/{group_id}", response_model=ChatGroupOut)
async def update_chat_group(
    group_id: uuid.UUID, payload: ChatGroupUpdate, db: AsyncSession = Depends(get_db)
) -> ChatGroup:
    group = await _get_chat_group_or_404(db, group_id)
    group.name = payload.name.strip()
    await db.commit()
    await db.refresh(group)
    return group


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat_group(group_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    # Sessions in this group return to the loose list via ON DELETE SET
    # NULL on chat_sessions.group_id -- never cascade-deletes them.
    group = await _get_chat_group_or_404(db, group_id)
    await db.delete(group)
    await db.commit()


# --------------------------------------------------------------------------
# ChatArtifact -- files the agent wrote during the session (write_file/patch
# tool calls), captured in stream_chat_message below. Ad-hoc, not linked to
# product/version/pipeline like the governance Artifact domain -- see
# db/models/chat.py's ChatArtifact docstring for why.
# --------------------------------------------------------------------------


@router.get("/sessions/{session_id}/artifacts", response_model=list[ChatArtifactOut])
async def list_chat_artifacts(
    session_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[ChatArtifact]:
    await _get_session_or_404(db, session_id)
    result = await db.execute(
        select(ChatArtifact)
        .where(ChatArtifact.session_id == session_id)
        .order_by(ChatArtifact.created_at.desc())
    )
    return list(result.scalars().all())


@router.delete("/artifacts/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat_artifact(artifact_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    """Removes the ForgeHub-side reference only -- the real file on the
    host filesystem is never touched (see ChatArtifact's docstring: this
    table just points at a path, it doesn't own a copy)."""
    artifact = await db.get(ChatArtifact, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    await db.delete(artifact)
    await db.commit()


@router.get("/artifacts", response_model=list[ChatArtifactGlobalOut])
async def search_chat_artifacts(q: str = "", db: AsyncSession = Depends(get_db)) -> list[dict]:
    """Global (cross-session, cross-agent) artifact search backing the
    composer's "$Artefato" picker -- unlike list_chat_artifacts above,
    this isn't scoped to one conversation. Selecting a result inserts its
    real path directly (same as the "@" file mention), no name-to-path
    resolution step (confirmed: simpler > a friendly "$Name" token)."""
    stmt = (
        select(ChatArtifact, Agent.name.label("agent_name"))
        .join(ChatSession, ChatArtifact.session_id == ChatSession.id)
        .join(Agent, ChatSession.agent_id == Agent.id)
        .order_by(ChatArtifact.created_at.desc())
        .limit(50)
    )
    if q.strip():
        stmt = stmt.where(ChatArtifact.name.ilike(f"%{q.strip()}%"))
    result = await db.execute(stmt)
    return [
        {
            "id": artifact.id,
            "session_id": artifact.session_id,
            "path": artifact.path,
            "name": artifact.name,
            "created_at": artifact.created_at,
            "agent_name": agent_name,
        }
        for artifact, agent_name in result.all()
    ]


@router.get("/artifacts/{artifact_id}/download")
async def download_chat_artifact(
    artifact_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> Response:
    artifact = await db.get(ChatArtifact, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")

    # Re-reads the file live from the host via the bridge (nothing is copied
    # into ForgeHub's own storage) -- same /v1/fs/read endpoint the terminal's
    # file browser/editor already uses, so it's text-only.
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{settings.CHAT_BRIDGE_URL}/v1/fs/read",
            params={"path": artifact.path},
            headers=_bridge_headers(),
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not read artifact from host: {resp.text[:300]}",
        )
    content = resp.json()["content"]
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{artifact.name}"'},
    )


# --------------------------------------------------------------------------
# ChatMessage
# --------------------------------------------------------------------------


@router.get("/sessions/{session_id}/active-turn")
async def get_session_active_turn(
    session_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """"Há algo rodando nesta sessão, e o que já aconteceu?"

    O `tmux has-session` do chat (2026-08-13). O cliente pergunta isto ao
    montar: se a resposta traz um turno, ele redesenha o balão em execução com
    a trilha e o texto já gravados, em vez de mostrar a tela como se nada
    estivesse acontecendo -- que era o caso depois de um F5, um crash ou de
    fechar o navegador, mesmo com o agente ainda trabalhando.

    Devolve `{"turn": null}` quando não há nada em curso, e não 404: "nada
    rodando" é a resposta normal e mais comum, não um erro.
    """
    await _get_session_or_404(db, session_id)
    turns = await active_turns.get_active_all(db, scope="chat", scope_id=session_id)
    if not turns:
        return {"turn": None, "turns": []}
    for turn in turns:
        await active_turns.mark_reattached(db, turn.id)
    await db.commit()
    serialized = [
        {
            "id": str(turn.id),
            "stream_id": turn.stream_id,
            "prompt": turn.prompt,
            "agent_id": str(turn.agent_id) if turn.agent_id else None,
            "steps": turn.steps or [],
            "live_text": turn.live_text or "",
            "pending_approval": turn.pending_approval,
            "started_at": turn.created_at.isoformat(),
            "deadline_at": turn.deadline_at.isoformat() if turn.deadline_at else None,
        }
        for turn in turns
    ]
    return {"turn": serialized[0], "turns": serialized}


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageOut])
async def list_chat_messages(
    session_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[ChatMessage]:
    await _get_session_or_404(db, session_id)
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    )
    return list(result.scalars().all())


@router.delete("/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat_message(message_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    """Deletes a single message -- used by the frontend's "Regenerate" action
    to drop the assistant's last reply before re-requesting a fresh one (see
    stream_chat_message's `regenerate` param). Only removes the ForgeHub-side
    row; the real Hermes CLI session transcript (resumed via
    hermes_session_id) still has the old exchange in its own context."""
    message = await db.get(ChatMessage, message_id)
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    await db.delete(message)
    await db.commit()


@router.post(
    "/sessions/{session_id}/messages",
    response_model=ChatSendResult,
    status_code=status.HTTP_201_CREATED,
)
async def send_chat_message(
    session_id: uuid.UUID,
    message: str = Form(default=""),
    files: list[UploadFile] = File(default=[]),
    db: AsyncSession = Depends(get_db),
) -> ChatSendResult:
    session = await _get_session_or_404(db, session_id)
    agent = await _get_chattable_agent_or_404(db, session.agent_id)

    if not message.strip() and not files:
        raise HTTPException(status_code=400, detail="message or file is required")

    attachment_name = ", ".join(f.filename for f in files if f.filename) or None
    outgoing_message = message
    call_started_at = time.monotonic()

    attachment_data_urls_str: str | None = None
    if files:
        images: list[tuple[str, bytes]] = []
        text_blocks: list[str] = []
        data_urls: list[str] = []
        for f in files:
            content = await f.read()
            if (f.content_type or "").startswith("image/"):
                images.append((f.filename or "image.png", content))
                mime = f.content_type or "image/png"
                b64 = base64.b64encode(content).decode("utf-8")
                data_urls.append(f"data:{mime};base64,{b64}")
            else:
                try:
                    text_content = content.decode("utf-8")
                except UnicodeDecodeError:
                    raise HTTPException(
                        status_code=400, detail="Attached file must be a text file or an image"
                    ) from None
                text_blocks.append(f'Content of file "{f.filename}" pasted below:\n---\n{text_content}\n---')

        if data_urls:
            attachment_data_urls_str = json.dumps(data_urls)

        if images:
            # Plain prose framing, not a bracketed "[Arquivo anexado: ...]"
            # tag -- that reads like a system attachment token to the agent
            # and makes it try to fetch the file via a tool instead of just
            # reading the content pasted right here (confirmed during testing).
            combined_message = "\n\n".join([*text_blocks, message]).strip()
            bridge_result = await _call_bridge_images(
                agent.profile_slug,
                _with_language_note(combined_message or "See the attached images."),
                session.hermes_session_id,
                images,
            )
        else:
            outgoing_message = "\n\n".join([*text_blocks, message]).strip()
            bridge_result = await _call_bridge_text(
                agent.profile_slug, _with_language_note(outgoing_message), session.hermes_session_id
            )
    else:
        bridge_result = await _call_bridge_text(
            agent.profile_slug, _with_language_note(message), session.hermes_session_id
        )

    user_message = ChatMessage(
        session_id=session.id,
        role="user",
        content=message,
        attachment_names=attachment_name,
        attachment_data_urls=attachment_data_urls_str,
    )
    assistant_message = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=bridge_result["reply"],
        thinking_seconds=round(time.monotonic() - call_started_at),
    )
    db.add(user_message)
    db.add(assistant_message)

    session.hermes_session_id = bridge_result.get("session_id") or session.hermes_session_id
    if session.title == "New chat" and message.strip():
        session.title = message.strip()[:TITLE_PREVIEW_LENGTH]

    await db.commit()
    await db.refresh(user_message)
    await db.refresh(assistant_message)
    await db.refresh(session)

    return ChatSendResult(
        user_message=user_message, assistant_message=assistant_message, session=session
    )


@router.post(
    "/sessions/{session_id}/exec",
    response_model=ChatSendResult,
    status_code=status.HTTP_201_CREATED,
)
async def exec_chat_command(
    session_id: uuid.UUID, payload: ChatExecRequest, db: AsyncSession = Depends(get_db)
) -> ChatSendResult:
    """Backs the composer's "!command" prefix -- runs a raw bash command via
    the bridge, no agent/LLM call at all (unlike SAFE_SLASH_COMMANDS, which
    still goes through Hermes's own dispatcher). Persisted like a normal
    exchange so it shows inline in the thread, formatted as a command-reply
    block on the frontend (same as slash command output)."""
    session = await _get_session_or_404(db, session_id)

    async with httpx.AsyncClient(timeout=65.0) as client:
        resp = await client.post(
            f"{settings.CHAT_BRIDGE_URL}/v1/exec",
            json={"command": payload.command, "cwd": payload.cwd},
            headers=_bridge_headers(),
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Exec bridge error: {resp.text[:500]}",
        )
    result = resp.json()
    output_parts = [p for p in (result["stdout"].strip(), result["stderr"].strip()) if p]
    if result["exit_code"] != 0:
        output_parts.append(f"(exit code {result['exit_code']})")
    output = "\n".join(output_parts) or "(no output)"

    user_message = ChatMessage(session_id=session.id, role="user", content=f"!{payload.command}")
    assistant_message = ChatMessage(session_id=session.id, role="assistant", content=output)
    db.add(user_message)
    db.add(assistant_message)
    if session.title == "New chat":
        session.title = f"!{payload.command}"[:TITLE_PREVIEW_LENGTH]
    await db.commit()
    await db.refresh(user_message)
    await db.refresh(assistant_message)
    await db.refresh(session)

    return ChatSendResult(
        user_message=user_message, assistant_message=assistant_message, session=session
    )


# --------------------------------------------------------------------------
# Streaming chat (SSE proxy — streams token deltas for voice mode)
# --------------------------------------------------------------------------


# Turns detached from the request that started them (2026-08-14, see
# `_run_chat_turn`'s docstring for why) still need a strong reference kept
# somewhere, or asyncio is free to garbage-collect a Task nothing is holding
# onto -- silently ending the turn mid-run with no error anywhere. Discarded
# by the task's own done-callback once it finishes either way.
_LIVE_CHAT_TASKS: set[asyncio.Task] = set()
_CHAT_AGENT_LOCKS: dict[tuple[uuid.UUID, uuid.UUID], asyncio.Lock] = {}
_CHAT_PARTICIPANT_LOCKS: dict[tuple[uuid.UUID, uuid.UUID], asyncio.Lock] = {}


def _chat_agent_lock(session_id: uuid.UUID, agent_id: uuid.UUID) -> asyncio.Lock:
    return _CHAT_AGENT_LOCKS.setdefault((session_id, agent_id), asyncio.Lock())


def _content_from_turn(turn: "ActiveTurn") -> str | None:
    """Same shape as `_run_chat_turn`'s in-memory `_interrupted_turn_content`,
    read from the ActiveTurn row instead of local variables -- what the Stop
    route uses, since it never had those variables in the first place (the
    turn it is stopping runs inside a different coroutine entirely)."""
    parts: list[str] = []
    if turn.steps:
        labels = [s.get("label") or s.get("name") for s in turn.steps if s.get("label") or s.get("name")]
        unique_labels = list(dict.fromkeys(labels))
        if unique_labels:
            parts.append(
                "⚠️ Turno interrompido antes de concluir. Etapas executadas:\n"
                + "\n".join(f"- {s}" for s in unique_labels)
            )
    partial = (turn.live_text or "").strip()
    if partial:
        parts.append(partial)
    return "\n\n".join(parts) or None


async def _run_chat_turn(
    *,
    session_id: uuid.UUID,
    participant_id: uuid.UUID | None,
    target_agent_id: uuid.UUID,
    message: str,
    bridge_params: dict,
    hidden: bool,
    stream_started_at: float,
    out_queue: "asyncio.Queue[str | None]",
) -> None:
    """Drives one chat turn against the host-bridge to completion, entirely
    independent of the browser connection that asked for it.

    Runs as a free-standing asyncio.Task (see the route below), with its own
    DB session -- never the request's -- because the request's session is
    torn down once the HTTP response it belongs to finishes, and this task
    must keep running well past that point.

    Why it has to: a browser tab navigating to another screen, being
    reloaded, or simply losing its connection ends the HTTP response, and
    Starlette cancels whatever async generator was feeding it. When this
    logic used to run *inside* that generator, the cancellation reached all
    the way down through the httpx stream to the host-bridge and killed the
    agent's subprocess (2026-08-14, Marcelo: "ao sair do chat para abrir uma
    outra tela... ao retornar não apareceu nenhum processo" -- the very
    machinery built to survive a reload or a crash, `ActiveTurn`/reattach,
    was undone by the one thing it exists to survive). Since this function is
    never awaited by the route -- only queued as a task and left alone -- a
    disconnect cannot reach it. It is the chat's tmux: it keeps going, and a
    reconnect finds it exactly as the Terminal finds a detached session.

    Every event is also pushed onto `out_queue` for whichever browser
    connection happens to be listening right now; `None` is the sentinel
    that tells that connection's generator the turn is over (successfully or
    not) so it can end its own response instead of hanging forever.
    """
    accumulated: list[str] = []
    turn_id: uuid.UUID | None = None
    created_paths: list[str] = []
    steps_run: list[str] = []

    def _interrupted_turn_content() -> str | None:
        parts: list[str] = []
        if steps_run:
            unique_steps = list(dict.fromkeys(steps_run))
            parts.append(
                "⚠️ Turno interrompido antes de concluir. Etapas executadas:\n"
                + "\n".join(f"- {s}" for s in unique_steps)
            )
        partial = "".join(accumulated).strip()
        if partial:
            parts.append(partial)
        return "\n\n".join(parts) or None

    async def _persist_reply(db: AsyncSession, content: str) -> None:
        db.add(ChatMessage(
            session_id=session_id,
            role="assistant",
            content=_wrap_hidden(content) if hidden else content,
            responding_agent_id=target_agent_id,
            thinking_seconds=round(time.monotonic() - stream_started_at),
        ))

    lane_lock = _chat_agent_lock(session_id, target_agent_id)
    lane_acquired = False
    try:
        # One Hermes session is a linear conversation. Messages addressed to
        # different agents use different lanes and therefore execute in
        # parallel; several messages for this same agent wait here and resume
        # the session produced by the previous turn instead of forking it.
        await lane_lock.acquire()
        lane_acquired = True
        async with AsyncSessionLocal() as db:
            effective_bridge_params = dict(bridge_params)
            effective_bridge_params.pop("session_id", None)
            if participant_id is not None:
                participant = await db.get(ChatSessionParticipant, participant_id)
                if participant is not None and participant.hermes_session_id:
                    effective_bridge_params["session_id"] = participant.hermes_session_id
            else:
                fresh_session = await db.get(ChatSession, session_id)
                if fresh_session is not None and fresh_session.hermes_session_id:
                    effective_bridge_params["session_id"] = fresh_session.hermes_session_id
            try:
                async with httpx.AsyncClient(timeout=660.0) as client:
                    async with client.stream(
                        "GET",
                        f"{settings.CHAT_BRIDGE_URL}/v1/chat/stream",
                        params=effective_bridge_params,
                        headers=_bridge_headers(),
                    ) as resp:
                        if resp.status_code != 200:
                            body = await resp.aread()
                            await out_queue.put(f'data: {json.dumps({"error": body.decode()[:200]})}\n\n')
                            return

                        async for line in resp.aiter_lines():
                            if not line.startswith("data:"):
                                # SSE comment = keepalive ping from the bridge
                                # (agent thinking silently). Forward it so the
                                # browser<->backend hops don't idle out either;
                                # the frontend ignores non-"data:" lines.
                                if line.startswith(":"):
                                    await out_queue.put(": ping\n\n")
                                continue
                            raw = line[5:].strip()
                            data = json.loads(raw)

                            if data.get("error"):
                                await out_queue.put(f"data: {raw}\n\n")
                                # The bridge itself reported failure mid-stream --
                                # previously left the ActiveTurn row "running"
                                # forever (only the 20-minute sweep would ever
                                # close it). Close it now, same as every other
                                # non-`done` ending.
                                if turn_id is not None:
                                    closed = await active_turns.close_turn(
                                        db, turn_id, status="failed", error=str(data["error"])[:2000],
                                    )
                                    if closed:
                                        content = _interrupted_turn_content()
                                        if content:
                                            await _persist_reply(db, content)
                                    await db.commit()
                                # "_init_agent() returned False" is hermes_stream.py's
                                # one generic message for every _init_agent() failure
                                # mode (cli_agent_setup_mixin.py) -- including "Session
                                # not found" when the Hermes profile's own SQLite store
                                # no longer has the session_id we resumed with (pruned,
                                # rebuilt, or otherwise gone on the host side, outside
                                # ForgeHub's control). Without this, effective_bridge_params
                                # above keeps resolving to that same dead session_id on
                                # every future message in this chat/participant, so the
                                # conversation is permanently stuck repeating the exact
                                # same failure (observed 2026-08-24, Athos Workspace
                                # session idle since 2026-08-14). Clearing it here costs
                                # nothing when the real cause was something else (e.g.
                                # credentials) -- the next turn just fails again with the
                                # same message -- but recovers the common case by letting
                                # the next message start a fresh Hermes session instead.
                                if (
                                    "_init_agent() returned False" in str(data["error"])
                                    and effective_bridge_params.get("session_id")
                                ):
                                    if participant_id is not None:
                                        participant = await db.get(ChatSessionParticipant, participant_id)
                                        if participant is not None:
                                            participant.hermes_session_id = None
                                    else:
                                        stale_session = await db.get(ChatSession, session_id)
                                        if stale_session is not None:
                                            stale_session.hermes_session_id = None
                                    await db.commit()
                                return

                            if data.get("done"):
                                full_reply = data.get("reply") or "".join(accumulated)
                                new_hsid = data.get("session_id")
                                await _persist_reply(db, full_reply)
                                for path in dict.fromkeys(created_paths):  # de-dupe, keep order
                                    db.add(
                                        ChatArtifact(
                                            session_id=session_id,
                                            path=path,
                                            name=os.path.basename(path.rstrip("/")) or path,
                                        )
                                    )
                                if new_hsid:
                                    if participant_id is not None:
                                        participant = await db.get(ChatSessionParticipant, participant_id)
                                        if participant is not None:
                                            participant.hermes_session_id = new_hsid
                                    else:
                                        session = await db.get(ChatSession, session_id)
                                        if session is not None:
                                            session.hermes_session_id = new_hsid
                                if turn_id is not None:
                                    await active_turns.close_turn(db, turn_id, status="completed")
                                await db.commit()
                                await out_queue.put(f'data: {json.dumps({"done": True})}\n\n')
                                return

                            # O primeiro evento com stream_id é o que torna este
                            # turno encontrável por quem reconectar -- o
                            # equivalente ao `tmux new-session` do terminal. Antes
                            # disso não há o que re-anexar.
                            if turn_id is None and data.get("stream_id"):
                                turn = await active_turns.open_turn(
                                    db,
                                    scope="chat",
                                    scope_id=session_id,
                                    stream_id=str(data["stream_id"]),
                                    prompt=message,
                                    agent_id=target_agent_id,
                                    hidden=hidden,
                                    supersede_existing=False,
                                )
                                turn_id = turn.id
                                await db.commit()
                                # Only thing the browser needs from this line --
                                # it is what lets a live tab's Stop button target
                                # this specific turn (see stop_chat_turn below).
                                await out_queue.put(f'data: {json.dumps({"turn_id": str(turn_id)})}\n\n')

                            tool_start = data.get("tool_start")
                            if isinstance(tool_start, dict):
                                step = tool_start.get("context") or tool_start.get("name")
                                if step:
                                    steps_run.append(str(step))
                                if turn_id is not None:
                                    await active_turns.record_step(
                                        db,
                                        turn_id,
                                        {
                                            "id": tool_start.get("id") or str(uuid.uuid4()),
                                            "name": tool_start.get("name"),
                                            "label": tool_start.get("context") or tool_start.get("name"),
                                            "status": "running",
                                        },
                                        agent_id=target_agent_id,
                                    )
                                    await db.commit()

                            # Uma aprovação no meio do turno é particularidade do
                            # chat: sem gravá-la, quem reconecta não vê o pedido e
                            # o turno espera para sempre por uma resposta que a
                            # tela nunca pede.
                            approval_request = data.get("approval_request")
                            if isinstance(approval_request, dict) and turn_id is not None:
                                await active_turns.set_pending_approval(db, turn_id, approval_request)
                                await db.commit()

                            tool_complete = data.get("tool_complete")
                            if isinstance(tool_complete, dict) and tool_complete.get("path"):
                                created_paths.append(tool_complete["path"])

                            delta = data.get("delta", "")
                            accumulated.append(delta)
                            if delta and turn_id is not None:
                                await active_turns.record_text(db, turn_id, delta)
                                await db.commit()
                            await out_queue.put(f"data: {raw}\n\n")

                        # Bridge stream closed without a done/error event (the
                        # agent subprocess died, the bridge connection broke, or
                        # this is the natural end of an explicit Stop: killing
                        # the subprocess closes the bridge's own stream the same
                        # way). The processing the user watched (partial text,
                        # tool steps) counts as the response -- persist it
                        # instead of dropping it, and tell the client explicitly;
                        # a silent close makes the in-flight turn vanish with no
                        # trace.
                        closed = True
                        if turn_id is not None:
                            closed = await active_turns.close_turn(
                                db, turn_id, status="failed",
                                error="O stream terminou sem concluir (o processo do agente caiu ou a ponte fechou).",
                            )
                        # Only the caller that actually transitioned the row
                        # persists a message -- stop_chat_turn may have already
                        # closed it (and written its own partial message) a
                        # moment before this loop noticed the stream end.
                        if closed:
                            content = _interrupted_turn_content()
                            if content:
                                await _persist_reply(db, content)
                        await db.commit()
                        await out_queue.put(f'data: {json.dumps({"error": "agent stream ended unexpectedly"})}\n\n')

            except asyncio.CancelledError:
                # Reachable only if this task is cancelled directly (e.g. a
                # server shutdown) -- a browser disconnecting no longer does
                # this, see the route below. Persist whatever was generated so
                # far instead of silently losing it, same as every other
                # non-`done` ending. shield=True: an unshielded commit here
                # would itself be cut off mid-flight by the same cancellation.
                with anyio.CancelScope(shield=True):
                    closed = True
                    if turn_id is not None:
                        closed = await active_turns.close_turn(db, turn_id, status="cancelled")
                    if closed:
                        content = _interrupted_turn_content()
                        if content:
                            await _persist_reply(db, content)
                    await db.commit()
                raise
            except Exception as exc:
                await out_queue.put(f'data: {json.dumps({"error": str(exc)})}\n\n')
    finally:
        if lane_acquired:
            lane_lock.release()
        # Sentinel: guaranteed even on an exception above, so a live tap never
        # waits forever on a turn that has, one way or another, ended.
        await out_queue.put(None)


@router.post("/sessions/{session_id}/turns/{turn_id}/stop")
async def stop_chat_turn(
    session_id: uuid.UUID, turn_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """Ends a running turn on purpose -- the Stop button's actual mechanism
    now that a turn no longer dies when the browser disconnects (see
    `_run_chat_turn`'s docstring). Before that change, "Stop" and "navigated
    away" were the same event from the backend's point of view: whichever one
    happened, the connection dropped and everything downstream died with it.
    Now the two have to be told apart on purpose, and this route is the
    "on purpose" one.

    Kills the underlying CLI process via the bridge (best-effort: if the
    bridge is unreachable or the process already finished, the row is still
    closed below, since the caller's actual goal -- stop waiting on this
    turn -- is satisfied either way) and persists whatever the agent had
    produced so far, from the ActiveTurn row itself rather than from any
    in-flight request's local state.
    """
    turn = await db.get(ActiveTurn, turn_id)
    if turn is None or turn.scope != "chat" or turn.scope_id != session_id:
        raise HTTPException(status_code=404, detail="No such turn")
    if turn.status != "running":
        return {"status": turn.status}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"{settings.CHAT_BRIDGE_URL}/v1/chat/stop",
                json={"stream_id": turn.stream_id},
                headers=_bridge_headers(),
            )
    except httpx.HTTPError:
        pass

    content = _content_from_turn(turn)
    hidden = turn.hidden
    target_agent_id = turn.agent_id
    closed = await active_turns.close_turn(db, turn_id, status="cancelled")
    if closed and content:
        db.add(ChatMessage(
            session_id=session_id,
            role="assistant",
            content=_wrap_hidden(content) if hidden else content,
            responding_agent_id=target_agent_id,
            thinking_seconds=round((datetime.now(timezone.utc) - turn.created_at).total_seconds()),
        ))
    await db.commit()
    return {"status": "cancelled"}


@router.get("/sessions/{session_id}/messages/stream")
async def stream_chat_message(
    session_id: uuid.UUID,
    message: str,
    voice: bool = False,
    regenerate: bool = False,
    target_agent_id: uuid.UUID | None = None,
    skip_user_message: bool = False,
    hidden: bool = False,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """SSE proxy: saves user message, streams agent deltas, saves assistant message on done.
    voice=true injects a brevity instruction before sending to the agent (not stored in DB).
    hidden=true marks this turn as internal priming (the Assistant panel
    sends its screen context this way when it opens, as its own turn in the
    same session instead of piggybacking on the user's first message): both
    the user message and the agent's reply are persisted wrapped in
    _HIDDEN_TURN markers so the transcript renderer drops them, and the
    session title is never taken from it.
    regenerate=true skips persisting a new user message -- the frontend's
    "Regenerate" action already deleted the old assistant reply and resends
    the existing last user message's text to get a fresh one appended,
    without duplicating that user turn in history.

    target_agent_id routes this turn to a "#Agente"-mentioned agent other
    than the session's own agent_id: that agent's own continuity lives in
    a ChatSessionParticipant row (not ChatSession.hermes_session_id), and
    its reply is tagged responding_agent_id so the frontend can badge it.
    The frontend calls this endpoint once per mentioned agent for a single
    user input; skip_user_message=true on the 2nd+ calls avoids persisting
    that same typed text as multiple duplicate user turns.
    """
    session = await _get_session_or_404(db, session_id)
    agent = await _get_chattable_agent_or_404(db, target_agent_id or session.agent_id)

    participant: ChatSessionParticipant | None = None
    if target_agent_id is not None:
        # Two simultaneous first messages to the same secondary agent must
        # converge on one participant row. The database uniqueness constraint
        # remains the last line of defence; this lock avoids turning that
        # normal UI gesture into an IntegrityError.
        participant_lock = _CHAT_PARTICIPANT_LOCKS.setdefault(
            (session.id, target_agent_id), asyncio.Lock()
        )
        async with participant_lock:
            result = await db.execute(
                select(ChatSessionParticipant).where(
                    ChatSessionParticipant.session_id == session.id,
                    ChatSessionParticipant.agent_id == target_agent_id,
                )
            )
            participant = result.scalar_one_or_none()
            if participant is None:
                participant = ChatSessionParticipant(session_id=session.id, agent_id=target_agent_id)
                db.add(participant)
                await db.commit()
                await db.refresh(participant)

    user_msg: ChatMessage | None = None
    if not regenerate and not skip_user_message:
        # Persist user message immediately (original text, no brevity wrapper;
        # hidden priming turns get wrapped so the transcript drops them)
        user_msg = ChatMessage(
            session_id=session.id, role="user", content=_wrap_hidden(message) if hidden else message
        )
        db.add(user_msg)
        if not hidden and session.title == "New chat" and message.strip():
            session.title = message.strip()[:TITLE_PREVIEW_LENGTH]
        await db.commit()
        await db.refresh(user_msg)

    # Voice mode: wrap with brevity instruction for the agent call only
    bridge_message = message
    if voice:
        bridge_message = (
            f"{message}\n\n"
            "(Modo voz — responda em no máximo 2 frases curtas e naturais, "
            "como numa conversa oral. Sem listas, sem markdown.)"
        )
    # Response-language note rides along the same hidden way (agent call
    # only, never persisted with the user's message).
    bridge_message = _with_language_note(bridge_message)
    bridge_message = (
        f"{bridge_message}\n\n"
        "[Roteamento interno ForgeHub: ao delegar com send_agent_message, "
        "use channel='workspace' e "
        f"channel_ref='{session.id}' para o resultado voltar a esta conversa.]"
    )

    shared_context = await _conversation_shared_context(db, session, message)
    if shared_context:
        bridge_message = f"{shared_context}\n\nMensagem atual para você:\n{bridge_message}"

    # Voice mode takes the fast ForgeRouter direct path (raw history, no tools,
    # ~2s first token) -- text mode takes the subprocess path (real hermes chat
    # session, full tool-calling) by omitting `history` and resuming via
    # `session_id`, same as the non-streaming /messages endpoint above.
    bridge_params: dict[str, str] = {"profile": agent.profile_slug, "message": bridge_message}
    if agent.runtime_type and agent.runtime_type != "hermes":
        bridge_params["runtime"] = agent.runtime_type
    if voice:
        history_result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session.id)
            .where(ChatMessage.id != user_msg.id)
            .order_by(ChatMessage.created_at)
            .limit(20)
        )
        history = [{"role": m.role, "content": m.content} for m in history_result.scalars().all()]
        bridge_params["history"] = json.dumps(history)
    elif participant is not None:
        if participant.hermes_session_id:
            bridge_params["session_id"] = participant.hermes_session_id
    elif session.hermes_session_id:
        bridge_params["session_id"] = session.hermes_session_id
    # Text-mode (subprocess) turns only -- voice's direct ForgeRouter path
    # has no terminal/tools, so a cwd wouldn't do anything there anyway.
    if not voice and session.working_directory_path:
        bridge_params["cwd"] = session.working_directory_path

    # From here on the actual work is detached (see _run_chat_turn): a
    # background task drives the bridge call and persistence to completion no
    # matter what this specific HTTP connection does. This route's only job
    # left is to launch it and tap its output for as long as a browser is
    # actually listening.
    queue: "asyncio.Queue[str | None]" = asyncio.Queue()
    task = asyncio.create_task(
        _run_chat_turn(
            session_id=session.id,
            participant_id=participant.id if participant is not None else None,
            target_agent_id=agent.id,
            message=message,
            bridge_params=bridge_params,
            hidden=hidden,
            stream_started_at=time.monotonic(),
            out_queue=queue,
        )
    )
    _LIVE_CHAT_TASKS.add(task)

    def _log_turn_failure(finished: asyncio.Task) -> None:
        _LIVE_CHAT_TASKS.discard(finished)
        if finished.cancelled():
            return
        exc = finished.exception()
        if exc is not None:
            logger.exception("Chat turn task for session %s failed", session_id, exc_info=exc)

    task.add_done_callback(_log_turn_failure)

    async def _tap():
        try:
            while True:
                item = await queue.get()
                if item is None:
                    return
                yield item
        except asyncio.CancelledError:
            # The browser disconnected -- navigated away, closed the tab, or
            # aborted the fetch. `task` above was never awaited from inside
            # this generator (only queued), so this cancellation has no way
            # to reach it: it keeps running on its own and finishes normally,
            # exactly like a detached tmux session. Re-raise so Starlette can
            # tear down this one HTTP response; there is nothing left to
            # persist here, that is entirely `_run_chat_turn`'s job now.
            raise

    return StreamingResponse(
        _tap(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )



@router.post("/sessions/{session_id}/improve-prompt/stream")
async def stream_improve_prompt(
    session_id: uuid.UUID, payload: ImprovePromptRequest, db: AsyncSession = Depends(get_db)
) -> StreamingResponse:
    """Asks this session's own agent to rewrite a draft message per an
    improvement instruction -- ported from channel.py's
    stream_improve_prompt, which shipped first for the Channels room
    (2026-08-06, Marcelo: "no ChatPane (Conversations) o icone de melhoria
    do prompt que foi construido no ChatPane (Canais)"). A channel asks its
    designated orchestrator; a 1:1 session has no such role, so this asks
    the session's own agent instead -- there's exactly one agent it could
    mean. A private utility call, never a real turn: no ChatMessage is
    created, nothing is added to the session's transcript, and the call
    always starts a fresh bridge session (hermes_session_id=None) so it
    never interferes with the session's own conversational continuity.
    Same SSE + ping pattern as channel.py's version (a single
    non-streaming bridge call can take up to ~650s -- see
    _call_bridge_text)."""
    session = await _get_session_or_404(db, session_id)
    agent = await _get_chattable_agent_or_404(db, session.agent_id)
    technique = await get_prompt_technique(db, payload.technique_code)

    prompt = build_prompt_improvement_request(
        actor_context=(
            f'Você é o agente "{agent.name}" no ForgeHub. O usuário está rascunhando uma mensagem '
            "e pediu sua ajuda para melhorá-la."
        ),
        draft=payload.draft,
        instruction=payload.instruction,
        technique=technique,
    )

    async def _events() -> AsyncIterator[str]:
        try:
            task = asyncio.ensure_future(_call_bridge_text(agent.profile_slug, prompt, None))
            while True:
                done, _pending = await asyncio.wait([task], timeout=15)
                if done:
                    break
                yield ": ping\n\n"
            bridge_result = await task
            improved_text = (bridge_result.get("reply") or "").strip()
            yield f"data: {json.dumps({'improved_text': improved_text})}\n\n"
        except Exception as exc:
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            yield f"event: error\ndata: {json.dumps({'detail': str(detail)})}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(_events(), media_type="text/event-stream")


@router.post("/approve")
async def approve_chat_action(payload: ChatApproveRequest) -> dict:
    """Answers a privileged-action approval_request raised mid-stream by an
    agent (e.g. a dangerous terminal command). Proxied straight through to
    the bridge, which writes the decision into the waiting subprocess's stdin."""
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            f"{settings.CHAT_BRIDGE_URL}/v1/chat/approve",
            json={"stream_id": payload.stream_id, "choice": payload.choice},
            headers=_bridge_headers(),
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Chat bridge error: {resp.text[:500]}",
        )
    return resp.json()


# --------------------------------------------------------------------------
# Voice transcription (proxied to the bridge's faster-whisper instance)
# --------------------------------------------------------------------------


@router.post("/tts")
async def tts(payload: dict) -> StreamingResponse:
    """Proxy text-to-speech synthesis to the Piper endpoint in the host bridge."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{settings.CHAT_BRIDGE_URL}/v1/tts",
            json=payload,
            headers=_bridge_headers(),
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"TTS bridge error: {resp.text[:200]}",
        )
    from fastapi import Response as FResponse
    return FResponse(content=resp.content, media_type="audio/wav")


@router.post("/transcribe")
async def transcribe_audio(audio: UploadFile = File(...)) -> dict:
    content = await audio.read()
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{settings.CHAT_BRIDGE_URL}/v1/transcribe",
            files={"audio": (audio.filename or "audio.webm", content, audio.content_type)},
            headers=_bridge_headers(),
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Chat bridge error: {resp.text[:500]}",
        )
    return resp.json()

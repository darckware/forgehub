"""Chat domain routes.

Every message sent here is proxied to the chat bridge (host-bridge/app.py,
running on the host -- see its module docstring for why) which actually
drives the real `hermes chat -p <profile>` process for that agent. This
router only owns persistence (chat_sessions/chat_messages, for the
conversation history view) and the proxy call; it has no access to the
Hermes CLI itself.
"""
import asyncio
import json
import os
import time
import uuid

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
    ChatMessageOut,
    ChatSendResult,
    ChatSessionCreate,
    ChatSessionOut,
    ChatSessionUpdate,
)
from app.core.config import CHAT_RESPONSE_LANGUAGE_NOTES, settings
from app.db.base import get_db
from app.db.models.agent import Agent
from app.db.models.chat import ChatArtifact, ChatMessage, ChatSession, ChatSessionParticipant

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

TITLE_PREVIEW_LENGTH = 60


async def _get_session_or_404(db: AsyncSession, session_id: uuid.UUID) -> ChatSession:
    session = await db.get(ChatSession, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")
    return session


async def _get_chattable_agent_or_404(db: AsyncSession, agent_id: uuid.UUID) -> Agent:
    agent = await db.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    if not agent.profile_slug:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This agent has no Hermes profile and cannot be chatted with",
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
    session = ChatSession(agent_id=payload.agent_id, title=payload.title)
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
    await db.commit()
    await db.refresh(session)
    return session


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat_session(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    session = await _get_session_or_404(db, session_id)
    await db.delete(session)
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

    if files:
        images: list[tuple[str, bytes]] = []
        text_blocks: list[str] = []
        for f in files:
            content = await f.read()
            if (f.content_type or "").startswith("image/"):
                images.append((f.filename or "image.png", content))
            else:
                try:
                    text_content = content.decode("utf-8")
                except UnicodeDecodeError:
                    raise HTTPException(
                        status_code=400, detail="Attached file must be a text file or an image"
                    ) from None
                text_blocks.append(f'Content of file "{f.filename}" pasted below:\n---\n{text_content}\n---')

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
        session_id=session.id, role="user", content=message, attachment_names=attachment_name
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

    # Voice mode takes the fast ForgeRouter direct path (raw history, no tools,
    # ~2s first token) -- text mode takes the subprocess path (real hermes chat
    # session, full tool-calling) by omitting `history` and resuming via
    # `session_id`, same as the non-streaming /messages endpoint above.
    bridge_params = {"profile": agent.profile_slug, "message": bridge_message}
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

    accumulated: list[str] = []
    created_paths: list[str] = []
    # Tool steps the agent ran this turn ("Running sleep 45", ...). If the
    # stream breaks before `done`, this processing activity IS the response
    # the user watched -- it gets persisted (see the interrupted-turn
    # handling below) instead of vanishing with the connection.
    steps_run: list[str] = []
    # Powers the "Pensou por mm:ss" label -- wall-clock from opening the
    # bridge stream to the agent's "done" (or a Stop-button cancellation).
    stream_started_at = time.monotonic()

    def _interrupted_turn_content() -> str | None:
        """Assistant-message content for a turn that ended before `done`:
        the partial text plus the tool steps the user watched run -- that
        processing activity counts as the response. None when the turn
        produced nothing at all."""
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

    async def proxy_stream():
        try:
            async with httpx.AsyncClient(timeout=660.0) as client:
                async with client.stream(
                    "GET",
                    f"{settings.CHAT_BRIDGE_URL}/v1/chat/stream",
                    params=bridge_params,
                    headers=_bridge_headers(),
                ) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        yield f'data: {json.dumps({"error": body.decode()[:200]})}\n\n'
                        return

                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            # SSE comment = keepalive ping from the bridge
                            # (agent thinking silently). Forward it so the
                            # browser<->backend hops don't idle out either;
                            # the frontend ignores non-"data:" lines.
                            if line.startswith(":"):
                                yield ": ping\n\n"
                            continue
                        raw = line[5:].strip()
                        data = json.loads(raw)

                        if data.get("error"):
                            yield f"data: {raw}\n\n"
                            return

                        if data.get("done"):
                            # Persist assistant message and update hermes session id
                            full_reply = data.get("reply") or "".join(accumulated)
                            new_hsid = data.get("session_id")
                            asst_msg = ChatMessage(
                                session_id=session.id,
                                role="assistant",
                                content=_wrap_hidden(full_reply) if hidden else full_reply,
                                responding_agent_id=target_agent_id,
                                thinking_seconds=round(time.monotonic() - stream_started_at),
                            )
                            db.add(asst_msg)
                            for path in dict.fromkeys(created_paths):  # de-dupe, keep order
                                db.add(
                                    ChatArtifact(
                                        session_id=session.id,
                                        path=path,
                                        name=os.path.basename(path.rstrip("/")) or path,
                                    )
                                )
                            if new_hsid:
                                if participant is not None:
                                    participant.hermes_session_id = new_hsid
                                else:
                                    session.hermes_session_id = new_hsid
                            await db.commit()
                            yield f'data: {json.dumps({"done": True})}\n\n'
                            return

                        tool_start = data.get("tool_start")
                        if isinstance(tool_start, dict):
                            step = tool_start.get("context") or tool_start.get("name")
                            if step:
                                steps_run.append(str(step))

                        tool_complete = data.get("tool_complete")
                        if isinstance(tool_complete, dict) and tool_complete.get("path"):
                            created_paths.append(tool_complete["path"])

                        delta = data.get("delta", "")
                        accumulated.append(delta)
                        yield f"data: {raw}\n\n"

                    # Bridge stream closed without a done/error event (the
                    # agent subprocess died or the bridge connection broke).
                    # The processing the user watched (partial text, tool
                    # steps) counts as the response -- persist it instead of
                    # dropping it, and tell the client explicitly; a silent
                    # close makes the in-flight turn vanish with no trace.
                    content = _interrupted_turn_content()
                    if content:
                        asst_msg = ChatMessage(
                            session_id=session.id,
                            role="assistant",
                            content=_wrap_hidden(content) if hidden else content,
                            responding_agent_id=target_agent_id,
                            thinking_seconds=round(time.monotonic() - stream_started_at),
                        )
                        db.add(asst_msg)
                        await db.commit()
                    yield f'data: {json.dumps({"error": "agent stream ended unexpectedly"})}\n\n'

        except asyncio.CancelledError:
            # Client aborted (Stop button / tab closed) -- the httpx stream
            # to the bridge is torn down as this propagates, which closes
            # the bridge's connection and lets its own finally block kill
            # the underlying hermes_stream.py subprocess. Persist whatever
            # was generated so far instead of silently losing it, same as a
            # normal turn's assistant message. The enclosing cancel scope
            # keeps injecting CancelledError at every await checkpoint
            # (confirmed: an unshielded `await db.commit()` here gets cut
            # off mid-flight and nothing is saved) -- shield=True is
            # required to let this specific write actually complete.
            cancelled_content = _interrupted_turn_content()
            if cancelled_content:
                with anyio.CancelScope(shield=True):
                    asst_msg = ChatMessage(
                        session_id=session.id,
                        role="assistant",
                        content=_wrap_hidden(cancelled_content) if hidden else cancelled_content,
                        responding_agent_id=target_agent_id,
                        thinking_seconds=round(time.monotonic() - stream_started_at),
                    )
                    db.add(asst_msg)
                    await db.commit()
            raise
        except Exception as exc:
            yield f'data: {json.dumps({"error": str(exc)})}\n\n'

    return StreamingResponse(
        proxy_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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

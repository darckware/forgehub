"""Pydantic schemas for the Chat domain (chat_sessions, chat_messages)."""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ChatSessionCreate(BaseModel):
    agent_id: uuid.UUID
    title: str = Field(default="New chat", max_length=150)


class ChatSessionUpdate(BaseModel):
    """Partial update -- only the provided fields are applied."""

    title: str | None = Field(default=None, min_length=1, max_length=150)
    pinned: bool | None = None


class ChatSessionOut(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    title: str
    pinned: bool
    hermes_session_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChatMessageOut(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    attachment_names: str | None
    responding_agent_id: uuid.UUID | None
    thinking_seconds: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatSendResult(BaseModel):
    """Returned by POST .../messages -- both turns of the exchange, since
    the frontend needs the assistant reply right away."""

    user_message: ChatMessageOut
    assistant_message: ChatMessageOut
    session: ChatSessionOut


class ChatArtifactOut(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    path: str
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatArtifactGlobalOut(ChatArtifactOut):
    """Same as ChatArtifactOut, plus who made it -- used by the "$Artefato"
    picker's global (cross-session, cross-agent) search."""

    agent_name: str


class ChatApproveRequest(BaseModel):
    """Answers a pending approval_request SSE event from /messages/stream.
    stream_id addresses the live agent subprocess directly (see
    host-bridge/hermes_stream.py); no session_id needed."""

    stream_id: str
    choice: str  # "once" | "session" | "always" | "deny"


class ChatExecRequest(BaseModel):
    """Backs the composer's "!command" prefix -- see exec_chat_command."""

    command: str
    cwd: str | None = None

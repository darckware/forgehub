"""Pydantic schemas for the Chat domain (chat_sessions, chat_messages)."""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ChatSessionCreate(BaseModel):
    agent_id: uuid.UUID
    title: str = Field(default="New chat", max_length=150)
    working_directory_path: str | None = Field(default=None, max_length=1024)


class ChatSessionUpdate(BaseModel):
    """Partial update -- only the provided fields are applied."""

    title: str | None = Field(default=None, min_length=1, max_length=150)
    pinned: bool | None = None
    # No sentinel needed for "clear the folder" -- unlike title/pinned,
    # explicitly setting this to null is a valid, meaningful update (unpin
    # the session from its folder), not "leave unchanged". The route uses
    # "working_directory_path"/"group_id" in payload.model_fields_set to
    # tell "omitted" from "explicitly nulled".
    working_directory_path: str | None = Field(default=None, max_length=1024)
    # A session's sidebar placement is exclusive with working_directory_path
    # above (Project XOR Group XOR neither) -- setting one explicitly clears
    # the other, enforced in update_chat_session.
    group_id: uuid.UUID | None = None


class ChatSessionOut(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    title: str
    pinned: bool
    hermes_session_id: str | None
    working_directory_path: str | None
    group_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChatGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)


class ChatGroupUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=150)


class ChatGroupOut(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChatMessageOut(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    attachment_names: str | None = None
    attachment_data_urls: str | None = None
    responding_agent_id: uuid.UUID | None = None
    thinking_seconds: int | None = None
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


class ChatSessionHostStatusOut(BaseModel):
    """One ChatSession's (or ChatSessionParticipant's) Hermes-side liveness
    -- backs System Control's "Chat Sessions" card (2026-08-24), the same
    "is what we think is running actually still there" question Terminal
    Sessions answers for tmux panes. `participant_id` is set only for a
    participant lane (a message addressed to a non-owning agent -- see
    ChatSessionParticipant's own docstring); `None` means this is the
    session's own owning agent (ChatSession.hermes_session_id)."""

    session_id: uuid.UUID
    participant_id: uuid.UUID | None
    session_title: str
    agent_id: uuid.UUID
    agent_name: str
    hermes_session_id: str
    exists: bool
    hermes_title: str | None
    last_activity_at: float | None
    message_count: int | None
    running: bool


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

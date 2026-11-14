"""Agent customer-service rules (Pessoal -> Regras de atendimento)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

FileState = Literal["in_sync", "missing", "differs", "unknown"]


class ServiceRuleOut(BaseModel):
    agent: str
    channel: str
    file_name: str
    file_path: str
    content: str
    content_hash: str | None
    chars: int
    max_chars: int
    updated_at: datetime | None
    updated_by: str | None
    file_state: FileState


class ServiceRuleUpdate(BaseModel):
    content: str = Field(max_length=20000)
    expected_hash: str | None = Field(default=None, max_length=64)


class ServiceRuleHistoryOut(BaseModel):
    at: datetime
    actor: str
    content_hash: str
    previous_hash: str | None
    chars: int

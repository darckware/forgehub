"""Bounded, advisory analysis; backend authority never comes from model output."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

OperatorState = Literal["decision", "processing", "waiting", "resolved"]


class TriageSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_id: uuid.UUID
    status: OperatorState
    category: Literal["authorization", "information", "quota", "dependency", "service",
                      "duplicate", "obsolete", "delivered", "feedback", "diagnosis", "ready", "uncertain", "review"]
    summary: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=1, max_length=1500)
    recommendation: str = Field(min_length=1, max_length=1500)
    proposed_action: Literal["none", "queue", "archive_notice", "resolve", "link", "diagnose"] = "none"
    related_message_id: uuid.UUID | None = None
    evidence_refs: list[str] = Field(default_factory=list, max_length=20)


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_id: uuid.UUID | None = None
    context: str | None = Field(default=None, max_length=200)


class AnalysisRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    status: Literal["queued", "running", "completed", "failed"]
    total: int
    processed: int
    applied: int
    summary: dict = Field(default_factory=dict)
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class MessageDeliveryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_updated_at: datetime
    evidence_ref: str = Field(pattern=r"^git:[0-9a-fA-F]{7,64}$", max_length=68)
    summary: str = Field(min_length=10, max_length=2000)
    executor_id: uuid.UUID | None = None
    related_message_id: uuid.UUID | None = None

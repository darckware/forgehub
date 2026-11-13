"""Schemas for the orchestrator's authorization requests and Marcelo's
pending mission decisions (2026-11-13)."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AuthorizationRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str = Field(min_length=1, max_length=255)
    justification: str = Field(min_length=1, max_length=8000)
    # What the orchestrator will execute once approved: the approved task's body.
    instructions: str = Field(min_length=1, max_length=20000)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=150)


class AuthorizationRequestOut(BaseModel):
    mission_project_id: uuid.UUID
    demand_id: uuid.UUID
    demand_number: int | None
    approval_status: str
    link: str


class PendingMissionDecision(BaseModel):
    kind: Literal["plan_approval", "phase_approval"]
    mission_project_id: uuid.UUID
    mission_name: str
    title: str
    summary: str | None
    requested_at: datetime | None
    requested_by: str | None = None
    # plan_approval: decided on POST /governed/approval-requests/{approval_request_id}:decide.
    approval_request_id: uuid.UUID | None = None
    project_plan_id: uuid.UUID | None = None
    task_count: int | None = None
    # phase_approval: POST /missions/{mission_project_id}/phases/{phase_id}:approve|:return.
    phase_id: uuid.UUID | None = None
    phase_position: int | None = None
    phase_name: str | None = None
    homologation_evidence: list[str] = []
    link: str

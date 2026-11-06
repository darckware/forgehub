import uuid
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProposalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message_number: int = Field(gt=0)
    server_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    shell: Literal["sh", "powershell"]
    content: str = Field(min_length=1, max_length=100_000)
    risk: Literal["change", "destructive"] = "change"
    timeout_seconds: int = Field(default=300, ge=1, le=3600)
    requires_elevation: bool = False
    parameters: list[dict] = Field(default_factory=list, max_length=30)
    reason: str = Field(min_length=1, max_length=5000)
    expected_effect: str = Field(min_length=1, max_length=5000)
    rollback: str = Field(min_length=1, max_length=10000)

    @field_validator('reason', 'expected_effect', 'rollback', 'content')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Cannot be blank')
        return value


class ProposalRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message_number: int
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ProposalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Literal["approved", "rejected"]
    reason: str | None = Field(default=None, max_length=5000)


class ProposalOut(ProposalCreate):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    id: uuid.UUID
    agent_id: uuid.UUID
    agent_demand_id: uuid.UUID
    content_hash: str
    status: str
    approved_at: datetime | None
    expires_at: datetime | None
    decision_reason: str | None
    execution_id: uuid.UUID | None
    machines: list[dict]

"""Pydantic schemas for the audit domain (ecosystem checkpoints)."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models.audit import AUDIT_RUN_STATUSES


class AuditCheckBase(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = None
    category: str | None = Field(default=None, max_length=50)
    command: str = Field(min_length=1)
    remediation_description: str | None = None
    remediation_command: str | None = None
    workdir: str | None = Field(default=None, max_length=500)
    agent_profile: str = Field(default="athos", max_length=50)
    enabled: bool = True
    timeout_seconds: int = Field(default=55, ge=1, le=600)


class AuditCheckCreate(AuditCheckBase):
    pass


class AuditCheckUpdate(BaseModel):
    """Partial update -- omitted (None) fields are left unchanged."""

    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = None
    category: str | None = Field(default=None, max_length=50)
    command: str | None = Field(default=None, min_length=1)
    remediation_description: str | None = None
    remediation_command: str | None = None
    workdir: str | None = Field(default=None, max_length=500)
    agent_profile: str | None = Field(default=None, max_length=50)
    enabled: bool | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=600)


class AuditRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    check_id: uuid.UUID
    status: str
    exit_code: int | None
    output: str | None
    duration_ms: int | None
    requested_by: str
    created_at: datetime

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: str) -> str:
        if v not in AUDIT_RUN_STATUSES:
            raise ValueError(f"status must be one of {AUDIT_RUN_STATUSES}")
        return v


class AuditCheckOut(AuditCheckBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    last_run: AuditRunOut | None = None


class AuditStatusOut(BaseModel):
    """Header summary for the Auditor page."""

    total: int
    enabled: int
    ok: int
    fail: int
    never_ran: int
    last_run_at: datetime | None = None


class AuditRunAllOut(BaseModel):
    runs: list[AuditRunOut]


class AuditRemediationOut(BaseModel):
    remediation_run: AuditRunOut
    verification_run: AuditRunOut
    escalated_to_inbox: bool = False
    inbox_demand_id: uuid.UUID | None = None

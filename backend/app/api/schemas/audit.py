"""Pydantic schemas for the audit domain (ecosystem checkpoints)."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models.audit import AUDIT_RUN_STATUSES

AuditFrequency = Literal["daily", "weekly", "monthly", "quarterly"]


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
    frequency: AuditFrequency = "weekly"


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


class AuditCheckFrequencyIn(BaseModel):
    """Admin-only (PUT /checks/{id}/frequency): moves a check between tiers."""

    frequency: AuditFrequency


class AuditRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    check_id: uuid.UUID
    batch_id: uuid.UUID | None = None
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
    evidence_state: Literal["fresh", "stale", "never"] = "never"
    expires_at: datetime | None = None


class AthosAuditMonitorOut(BaseModel):
    # "replaced": the four audit routines are the schedule now and this cron
    # is off (or gone), as the activation plan intends.
    state: Literal["healthy", "degraded", "failed", "not_configured", "replaced"]
    job_id: str | None = None
    job_name: str | None = None
    script: str | None = None
    schedule: str | None = None
    enabled: bool | None = None
    health: str | None = None
    last_run_at: str | None = None
    last_status: str | None = None
    next_run_at: str | None = None
    last_cron_run_at: datetime | None = None
    issues: list[str] = Field(default_factory=list)


class AuditTierOut(BaseModel):
    """One frequency tier: its checks, its routine and its last complete batch."""

    frequency: AuditFrequency
    enabled_checks: int
    # Newest scheduled batch (routine or legacy cron) holding every enabled
    # check of this tier; a manual tier run doesn't count as the schedule.
    last_complete_run_at: datetime | None = None
    routine_id: uuid.UUID | None = None
    routine_title: str | None = None
    routine_enabled: bool = False
    schedule: str | None = None
    timezone: str | None = None
    next_due_at: datetime | None = None
    # The tier's evidence has outlived one period plus grace.
    overdue: bool = False


class AuditStatusOut(BaseModel):
    """Header summary for the Auditor page."""

    total: int
    enabled: int
    ok: int
    fail: int
    never_ran: int
    stale: int = 0
    last_complete_cron_run_at: datetime | None = None
    last_run_at: datetime | None = None
    athos_monitor: AthosAuditMonitorOut | None = None
    # "routines" once all four audit routines are enabled, else the legacy
    # Hermes cron still schedules the audit.
    schedule_source: Literal["routines", "hermes_cron"] = "hermes_cron"
    tiers: list[AuditTierOut] = Field(default_factory=list)


class AuditRunAllOut(BaseModel):
    runs: list[AuditRunOut]


class AuditRemediationOut(BaseModel):
    remediation_run: AuditRunOut
    verification_run: AuditRunOut
    escalated_to_inbox: bool = False
    inbox_demand_id: uuid.UUID | None = None

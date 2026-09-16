"""Public report and credential projections; secrets are never read back."""
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReportCreate(BaseModel):
    period_start: date
    period_end: date
    irregularity_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def validate_interval(self):
        if self.period_end < self.period_start or self.period_end == date.max:
            raise ValueError("Invalid report interval")
        return self


class MonthlyReportCreate(BaseModel):
    month: str = Field(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")


class ReportReview(BaseModel):
    reviewed: bool


class ClientReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    kind: Literal["monthly", "on_demand"]
    period_start: date
    period_end: date
    irregularity_id: uuid.UUID | None
    generated_at: datetime
    generated_by_user_id: uuid.UUID | None
    reviewed_at: datetime | None
    reviewed_by_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ClientReportDetailOut(ClientReportOut):
    snapshot: dict


class ReadCredentialCreate(BaseModel):
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def validate_expiry(self):
        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise ValueError("Expiry requires a timezone")
        return self


class ReadCredentialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    expires_at: datetime | None
    revoked_at: datetime | None
    created_by_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ReadCredentialIssued(BaseModel):
    credential: ReadCredentialOut
    token: str


class ExternalIrregularityOut(BaseModel):
    id: uuid.UUID
    workstation_id: uuid.UUID
    hostname: str | None
    rule_key: str
    severity: str
    detail: str
    status: str
    detected_at: datetime
    resolved_at: datetime | None

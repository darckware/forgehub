import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, computed_field


class ClientBase(BaseModel):
    name: str
    contact_name: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    support_plan: str | None = None
    notes: str | None = None


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    name: str | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    support_plan: str | None = None
    notes: str | None = None


class ClientOut(ClientBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    headscale_tag: str | None
    created_at: datetime
    updated_at: datetime


class WorkstationCreate(BaseModel):
    client_id: uuid.UUID
    os_kind: str


class WorkstationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    hostname: str | None
    os_kind: str
    device_token_issued_at: datetime
    device_token_revoked_at: datetime | None
    last_report_at: datetime | None
    last_seen_agent_version: str | None
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def device_token_active(self) -> bool:
        return self.device_token_revoked_at is None


class WorkstationTokenIssued(BaseModel):
    """Returned exactly once, at issuance -- the only response that ever
    carries the raw token."""
    workstation: WorkstationOut
    device_token: str

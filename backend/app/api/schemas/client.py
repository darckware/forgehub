import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


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

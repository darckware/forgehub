import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PeerGrantCreate(BaseModel):
    workstation_a_id: uuid.UUID
    workstation_b_id: uuid.UUID


class PeerGrantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workstation_a_id: uuid.UUID
    workstation_b_id: uuid.UUID
    granted_by_user_id: uuid.UUID | None
    granted_at: datetime
    revoked_at: datetime | None

"""Service-line catalog request and response models."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ServiceLineCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    stages: list[str] = Field(default_factory=list)
    required_documents: list[str] = Field(default_factory=list)
    evidence_types: list[str] = Field(default_factory=list)
    default_agents: list[str] = Field(default_factory=list)
    sla_hours: int | None = Field(default=None, ge=0)
    darckware_contract_type: str | None = None
    client_visible: bool = False
    is_active: bool = True


class ServiceLineUpdate(BaseModel):
    slug: str | None = Field(default=None, min_length=1, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    stages: list[str] | None = None
    required_documents: list[str] | None = None
    evidence_types: list[str] | None = None
    default_agents: list[str] | None = None
    sla_hours: int | None = Field(default=None, ge=0)
    darckware_contract_type: str | None = None
    client_visible: bool | None = None
    is_active: bool | None = None


class ServiceLineOut(ServiceLineCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

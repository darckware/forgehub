"""Pydantic schemas for the Environment domain (Plano Integrado M0.7)."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.environment import ENVIRONMENTS, RELEASE_SOURCES


class EnvironmentReleaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    environment: str = Field(pattern=f"^({'|'.join(ENVIRONMENTS)})$")
    target: str = Field(min_length=1, max_length=200, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    branch: str | None = Field(default=None, max_length=255)
    released_at: datetime | None = None
    task_id: uuid.UUID | None = None
    evidence_ref: str | None = Field(default=None, max_length=500)
    source: str = Field(default="recorded", pattern=f"^({'|'.join(RELEASE_SOURCES)})$")


class EnvironmentReleaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    environment: str
    target: str
    commit_sha: str
    branch: str | None
    released_at: datetime
    released_by: str
    task_id: uuid.UUID | None
    task_number: int | None = None
    evidence_ref: str | None
    source: str

"""Pydantic Create/Update/Read schemas for the Artifact domain."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.artifact import (
    ArtifactStatus,
    ArtifactType,
    ArtifactVersionStatus,
)


# ---------------------------------------------------------------------------
# ArtifactVersion
# ---------------------------------------------------------------------------
class ArtifactVersionCreate(BaseModel):
    location_uri: str = Field(..., max_length=2048)
    checksum: str | None = Field(default=None, max_length=128)
    notes: str | None = None
    status: ArtifactVersionStatus = ArtifactVersionStatus.DRAFT
    produced_by_task_execution_id: uuid.UUID | None = None
    # version_number is server-assigned (next sequential number for the
    # artifact) -- not accepted from the client.


class ArtifactVersionUpdate(BaseModel):
    location_uri: str | None = Field(default=None, max_length=2048)
    checksum: str | None = Field(default=None, max_length=128)
    notes: str | None = None
    status: ArtifactVersionStatus | None = None


class ArtifactVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    artifact_id: uuid.UUID
    version_number: int
    status: ArtifactVersionStatus
    location_uri: str
    checksum: str | None
    notes: str | None
    produced_by_task_execution_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Artifact
# ---------------------------------------------------------------------------
class ArtifactCreate(BaseModel):
    name: str = Field(..., max_length=255)
    artifact_type: ArtifactType
    description: str | None = None
    pipeline_stage_id: uuid.UUID | None = None
    task_execution_id: uuid.UUID | None = None
    requires_approval: bool = False
    is_locked: bool = False
    # Optional first version supplied at creation time.
    initial_version: ArtifactVersionCreate | None = None


class ArtifactUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    description: str | None = None
    pipeline_stage_id: uuid.UUID | None = None
    task_execution_id: uuid.UUID | None = None
    requires_approval: bool | None = None
    status: ArtifactStatus | None = None
    is_locked: bool | None = None


class ArtifactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    artifact_type: ArtifactType
    status: ArtifactStatus
    description: str | None
    pipeline_stage_id: uuid.UUID | None
    task_execution_id: uuid.UUID | None
    requires_approval: bool
    is_locked: bool
    created_at: datetime
    updated_at: datetime


class ArtifactWithVersionsOut(ArtifactOut):
    versions: list[ArtifactVersionOut] = []


class ArtifactApprovalDecision(BaseModel):
    """Body for the approve/reject action endpoint."""

    approve: bool
    notes: str | None = None

"""Public projections for Nexo agent builds and installation tracking."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class NexoSource(BaseModel):
    git_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    agent_version: str = Field(min_length=1, max_length=50)


class NexoAgentBuildOut(BaseModel):
    """Build metadata safe for API clients; storage paths stay server-side."""

    id: uuid.UUID
    git_sha: str
    agent_version: str
    os_kind: Literal["linux", "windows"]
    status: Literal["queued", "building", "ready", "failed"]
    artifact_size: int | None
    sha256: str | None
    build_log_excerpt: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NexoBuildCatalogOut(BaseModel):
    source: NexoSource
    builds: list[NexoAgentBuildOut]


NexoOsKind = Literal["linux", "windows"]
NexoInstallationStatus = Literal[
    "package_ready", "downloaded", "online", "outdated", "error"
]
NexoInstallationEventType = Literal[
    "package_generated", "downloaded", "first_report", "version_mismatch", "error"
]


class NexoInstallationOut(BaseModel):
    """Current installation state joined to its safe display metadata."""

    id: uuid.UUID
    workstation_id: uuid.UUID
    client_id: uuid.UUID
    build_id: uuid.UUID
    client_name: str
    workstation_hostname: str | None
    os_kind: NexoOsKind
    status: NexoInstallationStatus
    expected_version: str
    detected_version: str | None
    package_generated_at: datetime
    downloaded_at: datetime | None
    online_at: datetime | None
    last_report_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class NexoInstallationEventOut(BaseModel):
    id: uuid.UUID
    event_type: NexoInstallationEventType
    from_status: NexoInstallationStatus | None
    to_status: NexoInstallationStatus
    detail: str | None
    actor_user_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class NexoInstallationDetailOut(NexoInstallationOut):
    events: list[NexoInstallationEventOut]

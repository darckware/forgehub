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

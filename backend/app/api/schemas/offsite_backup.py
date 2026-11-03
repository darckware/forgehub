"""Off-site backup request/response schemas -- see api/routes/offsite_backup.py."""
import posixpath
import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

TARGET_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
CONTAINER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,254}$")


def _normalize_path(raw: str) -> str:
    path = raw.strip()
    if not path.startswith("/"):
        raise ValueError(f"'{raw}' is not an absolute path")
    normalized = posixpath.normpath(path)
    if normalized == "/":
        raise ValueError("The whole filesystem (/) can't be a backup path; pick the folders")
    if any(ch in normalized for ch in "\n\r\0"):
        raise ValueError(f"'{raw}' has invalid characters")
    return normalized


class OffsiteBackupTargetWrite(BaseModel):
    label: str = Field(min_length=1, max_length=255)
    paths: list[str] = Field(min_length=1, max_length=50)
    excludes: list[str] = Field(default_factory=list, max_length=200)
    postgres_container: str | None = None
    include_system_state: bool = False
    enabled: bool = True
    sort_order: int = 0

    @field_validator("label")
    @classmethod
    def _strip_label(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("A name is required")
        return value

    @field_validator("paths")
    @classmethod
    def _paths(cls, value: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(_normalize_path(p) for p in value if p.strip()))
        if not cleaned:
            raise ValueError("At least one folder is required")
        return cleaned

    @field_validator("excludes")
    @classmethod
    def _excludes(cls, value: list[str]) -> list[str]:
        cleaned = []
        for pattern in value:
            pattern = pattern.strip()
            if not pattern:
                continue
            if len(pattern) > 1024 or any(ch in pattern for ch in "\n\r\0"):
                raise ValueError(f"Invalid exclude pattern '{pattern[:40]}'")
            cleaned.append(pattern)
        return list(dict.fromkeys(cleaned))

    @field_validator("postgres_container")
    @classmethod
    def _container(cls, value: str | None) -> str | None:
        value = (value or "").strip() or None
        if value is not None and not CONTAINER_RE.match(value):
            raise ValueError("Invalid container name")
        return value


class OffsiteBackupTargetCreate(OffsiteBackupTargetWrite):
    # Restic tag of every snapshot of this target, so it can't change later.
    name: str

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        value = value.strip().lower()
        if not TARGET_NAME_RE.match(value):
            raise ValueError("Identifier: lowercase letters, digits and hyphens (up to 63)")
        return value


class OffsiteBackupRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    target_id: uuid.UUID | None
    target_name: str
    trigger: str
    status: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    snapshot_id: str | None
    files_new: int | None
    data_added: int | None
    total_bytes: int | None
    error: str | None


class OffsiteBackupTargetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    label: str
    paths: list[str]
    excludes: list[str]
    postgres_container: str | None
    include_system_state: bool
    enabled: bool
    sort_order: int
    last_run: OffsiteBackupRunOut | None = None
    last_success: OffsiteBackupRunOut | None = None


class OffsiteBackupSchedule(BaseModel):
    job_id: str
    expression: str
    enabled: bool
    next_run_at: str | None
    last_run_at: str | None
    last_status: str | None


class OffsiteBackupOverview(BaseModel):
    repository: str
    script: str
    # None when the Athos cron job isn't registered yet, or the host-bridge
    # couldn't be read -- `schedule_error` tells which.
    schedule: OffsiteBackupSchedule | None
    schedule_error: str | None
    running: bool
    # Targets waiting in the queue.
    queued: int
    repository_maintenance: OffsiteBackupRunOut | None
    targets: list[OffsiteBackupTargetOut]


class OffsiteBackupRunRequest(BaseModel):
    # Empty = every enabled target. Queued in this order.
    targets: list[str] = Field(default_factory=list, max_length=100)


# --- Internal (Athos' worker, bridge token) ---------------------------------


class OffsiteBackupEnqueue(BaseModel):
    trigger: Literal["schedule", "manual"] = "schedule"


class OffsiteBackupRunStart(BaseModel):
    target_name: str = Field(min_length=1, max_length=64)
    trigger: Literal["schedule", "manual"] = "schedule"


class OffsiteBackupRunFinish(BaseModel):
    run_id: uuid.UUID
    status: Literal["ok", "failed"]
    snapshot_id: str | None = Field(default=None, max_length=64)
    files_new: int | None = None
    data_added: int | None = None
    total_bytes: int | None = None
    error: str | None = Field(default=None, max_length=8000)

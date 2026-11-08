"""Metadata only: file contents never travel in API request/response JSON."""
import uuid

from pydantic import BaseModel, Field


class RemoteFileTransferCreate(BaseModel):
    machine_id: uuid.UUID
    local_path: str = Field(min_length=1, max_length=4096)
    remote_path: str = Field(min_length=1, max_length=4096)
    reason: str = Field(min_length=3, max_length=2000)
    message_number: int = Field(gt=0)
    overwrite: bool = False


class RemoteFileTransferOut(BaseModel):
    machine_id: uuid.UUID
    direction: str
    local_path: str
    remote_path: str
    size: int = Field(ge=0, le=200 * 1024 * 1024)
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    overwrite: bool

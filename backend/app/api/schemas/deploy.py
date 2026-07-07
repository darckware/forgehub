"""Pydantic schemas for the Deploy domain."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DeployInstallationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    group_name: str | None = Field(default=None, max_length=100)
    order_index: int = Field(default=0)
    container_name: str | None = Field(default=None, max_length=255)
    compose_file: str | None = None
    restart_command: str | None = None
    ports: list[str] | None = None
    links: list[dict] | None = None
    notes: str | None = None
    product_id: uuid.UUID | None = None


class DeployInstallationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    group_name: str | None = Field(default=None, max_length=100)
    order_index: int | None = None
    container_name: str | None = Field(default=None, max_length=255)
    compose_file: str | None = None
    restart_command: str | None = None
    ports: list[str] | None = None
    links: list[dict] | None = None
    notes: str | None = None
    product_id: uuid.UUID | None = None


class DeployInstallationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    group_name: str | None
    order_index: int
    container_name: str | None
    compose_file: str | None
    restart_command: str | None
    ports: list | None
    links: list | None
    notes: str | None
    product_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class DeployInstallationOutEnriched(DeployInstallationOut):
    """DeployInstallationOut with optional resolved product name for display."""
    product_name: str | None = None


class DeployGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    order_index: int = Field(default=0)


class DeployGroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    order_index: int | None = None


class DeployGroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    order_index: int
    created_at: datetime
    updated_at: datetime


class DockerContainerOut(BaseModel):
    id: str
    name: str
    image: str
    status: str
    ports: str
    state: str
    health: str | None = None


class DockerVolumeOut(BaseModel):
    name: str
    driver: str
    mountpoint: str
    scope: str
    labels: dict = {}
    containers: list[str] = []


class DockerNetworkContainerOut(BaseModel):
    name: str
    ipv4: str


class DockerNetworkOut(BaseModel):
    id: str
    name: str
    driver: str
    scope: str
    internal: bool
    ipv6: bool
    subnets: list[str] = []
    containers: list[DockerNetworkContainerOut] = []


class DockerImageOut(BaseModel):
    id: str
    repository: str
    tag: str
    size: str
    created_since: str
    dangling: bool
    in_use: bool

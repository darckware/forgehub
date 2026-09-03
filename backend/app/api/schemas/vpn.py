from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


VpnNodeRole = Literal["local", "remote"]
VpnAction = Literal["connect", "disconnect", "restart", "test"]
VpnNodeState = Literal["online", "offline", "needs_login", "unavailable"]
VpnPathKind = Literal["direct", "derp", "idle", "unavailable"]


class VpnPosture(BaseModel):
    accept_dns: bool
    accept_routes: bool
    advertise_exit_node: bool
    tailscale_ssh: bool
    exit_node: bool
    restricted: bool


class VpnSourceStatus(BaseModel):
    name: Literal["status", "systemd", "preferences"]
    status: Literal["fresh", "unavailable"]
    checked_at: datetime
    error_code: str | None = None


class VpnNode(BaseModel):
    role: VpnNodeRole
    hostname: str | None = None
    tailscale_ipv4: str | None = None
    state: VpnNodeState
    online: bool = False
    active: bool = False
    last_seen: str | None = None
    rx_bytes: int = 0
    tx_bytes: int = 0
    daemon_state: str = "unavailable"
    posture: VpnPosture | None = None


class VpnConnection(BaseModel):
    kind: VpnPathKind
    relay: str | None = None
    latency_ms: float | None = None


class VpnStatus(BaseModel):
    independent_from_cloudflare: bool = True
    backend_state: str
    nodes: list[VpnNode]
    connection: VpnConnection
    checked_at: datetime
    source_error: str | None = None
    sources: list[VpnSourceStatus] = Field(default_factory=list)


class VpnActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: VpnAction


class VpnActionResult(BaseModel):
    success: bool
    code: str
    summary: str
    operation_id: uuid.UUID


class VpnOperationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_username: str | None = None
    target: VpnNodeRole
    action: VpnAction
    status: Literal["running", "succeeded", "failed"]
    result_code: str | None = None
    summary: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    created_at: datetime


class VpnOperationsOut(BaseModel):
    operations: list[VpnOperationOut]
    limit: int = Field(ge=1, le=100)

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# Remote Access (formerly "VPN", 2026-10-15). The tailnet is read from the
# VPS's own point of view: `server` is this node, `peers` every device it can
# reach. Operation targets are "self" or "peer"; "local"/"remote" (and the
# connect/disconnect actions) only survive in older history rows.
VpnAction = Literal["restart", "test"]
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


class VpnConnection(BaseModel):
    kind: VpnPathKind
    relay: str | None = None


class VpnNode(BaseModel):
    id: str
    name: str | None = None
    hostname: str | None = None
    dns_name: str | None = None
    os: str | None = None
    tags: list[str] = Field(default_factory=list)
    tailscale_ipv4: str | None = None
    state: VpnNodeState
    online: bool = False
    active: bool = False
    last_seen: str | None = None
    key_expiry: str | None = None
    rx_bytes: int = 0
    tx_bytes: int = 0
    connection: VpnConnection | None = None
    daemon_state: str | None = None
    posture: VpnPosture | None = None


class VpnStatus(BaseModel):
    backend_state: str
    server: VpnNode
    peers: list[VpnNode]
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
    target_name: str | None = None
    latency_ms: float | None = None
    path: VpnPathKind | None = None


class VpnOperationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_username: str | None = None
    target: str
    target_name: str | None = None
    action: str
    status: Literal["running", "succeeded", "failed"]
    result_code: str | None = None
    summary: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    created_at: datetime


class VpnOperationsOut(BaseModel):
    operations: list[VpnOperationOut]
    limit: int = Field(ge=1, le=100)


class TailnetPolicyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=2, max_length=500_000)
    note: str | None = Field(default=None, max_length=500)


class TailnetPolicyAnalysisOut(BaseModel):
    client_tags: list[str]
    tags_with_ssh: list[str]
    missing_ssh: list[str]
    snippet: str | None = None
    style: str
    warnings: list[str] = Field(default_factory=list)
    server_tag: str


class TailnetPolicyVersionOut(BaseModel):
    id: uuid.UUID
    note: str | None
    saved_by: str
    created_at: datetime


class TailnetPolicyOut(TailnetPolicyVersionOut):
    content: str
    analysis: TailnetPolicyAnalysisOut | None = None
    parse_error: str | None = None


class TailnetPolicyStateOut(BaseModel):
    current: TailnetPolicyOut | None
    versions: list[TailnetPolicyVersionOut]

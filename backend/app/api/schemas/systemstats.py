"""System-stats domain schemas. See api/routes/systemstats.py."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class MemoryStats(BaseModel):
    total_bytes: int
    used_bytes: int
    available_bytes: int
    percent_used: float


class DiskStats(BaseModel):
    total_bytes: int
    used_bytes: int
    free_bytes: int
    percent_used: float


class NetworkStats(BaseModel):
    interface: str | None
    rx_bytes: int
    tx_bytes: int


class SystemStatsOut(BaseModel):
    memory: MemoryStats
    disk: DiskStats
    network: NetworkStats


# Detailed host metadata is intentionally a separate admin-only contract.
class MonitoringSource(BaseModel):
    status: Literal['fresh', 'unavailable', 'collecting']
    collected_at: datetime | None
    error: str | None
    data: dict[str, Any] | list[Any] | None
    refreshing: bool = False


class ServerMonitoringOut(BaseModel):
    collected_at: datetime
    memory: MonitoringSource
    processes: MonitoringSource
    network: MonitoringSource
    connections: MonitoringSource
    filesystems: MonitoringSource
    directories: MonitoringSource
    access: MonitoringSource
    services: MonitoringSource
    containers: MonitoringSource

"""Mirrors the Nexo Remote Agent's `collector.Report` JSON shape exactly
(internal/collector/report.go in /root/project/nexo, post the final-review
fix wave: DiskUsage is a list, CollectionErrors/Hostname/OS/AgentVersion/
SchemaVersion all exist). Field names match Go's JSON tags, not Go's
exported field names."""
from pydantic import BaseModel


class ServiceStatusIn(BaseModel):
    name: str
    status: str  # "running" | "stopped" | "unknown"


class SoftwareMatchIn(BaseModel):
    name: str


class DiskUsageIn(BaseModel):
    path: str
    used_percent: float


class SystemMetricsIn(BaseModel):
    cpu_percent: float
    mem_percent: float
    disk_usage: list[DiskUsageIn] = []


class BackupStatusIn(BaseModel):
    path: str
    newest_file: str
    newest_mtime: str
    stale: bool


class AgentReportIn(BaseModel):
    collected_at: str
    system: SystemMetricsIn
    listening_ports: list[int] = []
    services: list[ServiceStatusIn] = []
    unauthorized_software: list[SoftwareMatchIn] = []
    backup: BackupStatusIn
    collection_errors: list[str] = []
    hostname: str = ""
    os: str = ""
    agent_version: str = ""
    schema_version: int

"""Pure rule evaluation over an ingested Nexo Remote Agent report -- no DB
access here, so this is unit-testable without the ingestion route or a
database at all. See docs/architecture/NEXO_CLIENT_MONITORING_AND_NETWORK_ADMIN.md
section 3.2 for the rule table this implements."""
from dataclasses import dataclass

from app.api.schemas.agent_report import AgentReportIn

SUPPORTED_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class RuleFinding:
    rule_key: str
    severity: str
    detail: str


def evaluate_report(report: AgentReportIn) -> list[RuleFinding]:
    findings: list[RuleFinding] = []

    # Aggregated into one finding per report, not one per offending disk --
    # otherwise N disks over threshold would create N findings for the same
    # rule_key, and the ingestion route's per-rule_key dedup would silently
    # drop every offender but the first one it flushes within the request.
    disk_offenders = [
        f"{disk.path} at {disk.used_percent:.1f}%"
        for disk in report.system.disk_usage
        if disk.used_percent > 90
    ]
    if disk_offenders:
        findings.append(RuleFinding(
            rule_key="disk_space_low",
            severity="warning",
            detail="; ".join(disk_offenders),
        ))

    if report.backup.stale:
        findings.append(RuleFinding(
            rule_key="backup_stale",
            severity="warning",
            detail=f"newest backup file {report.backup.newest_file or '(none found)'} "
                    f"at {report.backup.newest_mtime}",
        ))

    if report.unauthorized_software:
        names = ", ".join(m.name for m in report.unauthorized_software)
        findings.append(RuleFinding(
            rule_key="unauthorized_remote_tool",
            severity="critical",
            detail=f"unauthorized software detected: {names}",
        ))

    for service in report.services:
        if service.status == "stopped":
            findings.append(RuleFinding(
                rule_key="critical_service_down",
                severity="critical",
                detail=f"service {service.name} is stopped",
            ))

    if report.collection_errors:
        findings.append(RuleFinding(
            rule_key="collection_failed",
            severity="warning",
            detail="; ".join(report.collection_errors),
        ))

    return findings

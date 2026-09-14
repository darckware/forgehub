"""Nexo Remote Agent ingestion endpoint.

POST /api/v1/agent-reports -- authenticated by the X-Device-Token header
(hashed and matched against Workstation.device_token_hash; a revoked or
unknown token is 401). Never reachable by a User/Agent JWT/agt_ principal
-- this is a separate, narrower auth boundary than get_actor_principal,
scoped to exactly one Workstation.
"""
import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException
from sqlalchemy import select

from app.api.schemas.agent_report import AgentReportIn
from app.core.irregularity_rules import SUPPORTED_SCHEMA_VERSION, evaluate_report
from app.core.nexo_installation_state import reconcile_installation_report
from app.db.base import AsyncSessionLocal
from app.db.models.client import Irregularity, Workstation
from app.db.models.notification import Notification

router = APIRouter(prefix="/api/v1/agent-reports", tags=["agent-reports"])


@router.post("", status_code=202)
async def ingest_agent_report(
    report: AgentReportIn,
    x_device_token: str | None = Header(default=None),
):
    if not x_device_token:
        raise HTTPException(401, "X-Device-Token header required")
    if report.schema_version != SUPPORTED_SCHEMA_VERSION:
        raise HTTPException(
            400, f"unsupported schema_version {report.schema_version}, expected {SUPPORTED_SCHEMA_VERSION}"
        )

    token_hash = hashlib.sha256(x_device_token.encode()).hexdigest()

    async with AsyncSessionLocal() as db:
        workstation = (await db.execute(
            select(Workstation)
            .where(Workstation.device_token_hash == token_hash)
            .with_for_update()
        )).scalar_one_or_none()
        if workstation is None or workstation.device_token_revoked_at is not None:
            raise HTTPException(401, "invalid or revoked device token")

        reported_at = datetime.now(timezone.utc)
        workstation.last_report_at = reported_at
        if report.hostname:
            workstation.hostname = report.hostname
        if report.agent_version:
            workstation.last_seen_agent_version = report.agent_version

        findings = evaluate_report(report)
        for finding in findings:
            existing_open = (await db.execute(
                select(Irregularity).where(
                    Irregularity.workstation_id == workstation.id,
                    Irregularity.rule_key == finding.rule_key,
                    Irregularity.status == "open",
                )
            )).scalar_one_or_none()
            if existing_open is not None:
                # Still deduplicated to one row per (workstation, rule_key)
                # while open, but the row must not go stale: a later report
                # naming a *different* offending disk/service under the
                # same rule_key would otherwise leave the original detail
                # text -- and thus the original offender -- permanently
                # displayed, silently hiding the new information. No new
                # Notification here on purpose: only first-creation notifies.
                existing_open.detail = finding.detail
                existing_open.detected_at = datetime.now(timezone.utc)
                continue

            irregularity = Irregularity(
                workstation_id=workstation.id,
                rule_key=finding.rule_key,
                severity=finding.severity,
                detail=finding.detail,
                detected_at=datetime.now(timezone.utc),
            )
            db.add(irregularity)
            await db.flush()

            db.add(Notification(
                source="system",
                severity=finding.severity if finding.severity != "critical" else "error",
                title=f"Irregularidade: {finding.rule_key} ({workstation.hostname or workstation.id})",
                message=finding.detail,
                event_key=f"irregularity:{irregularity.id}",
                occurred_at=datetime.now(timezone.utc),
            ))

        await reconcile_installation_report(db, workstation, report.agent_version, reported_at)
        await db.commit()

    return {"accepted": True, "findings": len(findings)}

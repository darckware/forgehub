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
            select(Workstation).where(Workstation.device_token_hash == token_hash)
        )).scalar_one_or_none()
        if workstation is None or workstation.device_token_revoked_at is not None:
            raise HTTPException(401, "invalid or revoked device token")

        workstation.last_report_at = datetime.now(timezone.utc)
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

        await db.commit()

    return {"accepted": True, "findings": len(findings)}

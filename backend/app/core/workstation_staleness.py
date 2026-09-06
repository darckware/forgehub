"""Detects a Workstation that stopped reporting -- an agent cannot report
its own absence, so this has to be a server-side sweep. See
docs/architecture/NEXO_CLIENT_MONITORING_AND_NETWORK_ADMIN.md section 3.3."""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.client import Irregularity, Workstation
from app.db.models.notification import Notification

logger = logging.getLogger(__name__)

# Nexo's Report does not currently send its own report_interval, so a fixed
# conservative threshold is used until that's added to the agent payload
# (noted as a follow-up in the spec). 15 minutes covers the documented
# default report_interval (5m) at 3x with margin.
STALENESS_THRESHOLD = timedelta(minutes=15)


async def run_workstation_staleness_sweep(db: AsyncSession) -> int:
    cutoff = datetime.now(timezone.utc) - STALENESS_THRESHOLD
    stale_workstations = (await db.execute(
        select(Workstation).where(
            Workstation.device_token_revoked_at.is_(None),
            Workstation.last_report_at.is_not(None),
            Workstation.last_report_at < cutoff,
        )
    )).scalars().all()

    raised = 0
    for workstation in stale_workstations:
        existing_open = (await db.execute(
            select(Irregularity).where(
                Irregularity.workstation_id == workstation.id,
                Irregularity.rule_key == "agent_unreachable",
                Irregularity.status == "open",
            )
        )).scalar_one_or_none()
        if existing_open is not None:
            continue

        irregularity = Irregularity(
            workstation_id=workstation.id,
            rule_key="agent_unreachable",
            severity="critical",
            detail=f"no report since {workstation.last_report_at.isoformat()}",
            detected_at=datetime.now(timezone.utc),
        )
        db.add(irregularity)
        await db.flush()

        db.add(Notification(
            source="system",
            severity="error",
            title=f"Agente inacessível: {workstation.hostname or workstation.id}",
            message=irregularity.detail,
            event_key=f"irregularity:{irregularity.id}",
            occurred_at=datetime.now(timezone.utc),
        ))
        raised += 1

    await db.commit()
    return raised

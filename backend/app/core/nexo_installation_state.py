"""Reconcile authenticated reports within the ingestion transaction."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.client import Workstation
from app.db.models.nexo_installation import (
    NexoAgentBuild,
    WorkstationInstallation,
    WorkstationInstallationEvent,
)


async def reconcile_installation_report(
    db: AsyncSession,
    workstation: Workstation,
    agent_version: str,
    reported_at: datetime,
) -> None:
    """Update the current generation; the caller owns authentication and commit."""
    current = (
        await db.execute(
            select(WorkstationInstallation, NexoAgentBuild)
            .join(NexoAgentBuild, NexoAgentBuild.id == WorkstationInstallation.build_id)
            .where(WorkstationInstallation.workstation_id == workstation.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).one_or_none()
    if current is None:
        return
    installation, build = current
    if reported_at < installation.package_generated_at:
        return

    from_status = installation.status
    to_status = "online" if agent_version == build.agent_version else "outdated"
    if installation.online_at is None:
        installation.online_at = reported_at
        db.add(
            WorkstationInstallationEvent(
                installation_id=installation.id,
                event_type="first_report",
                from_status=from_status,
                to_status=to_status,
                created_at=datetime.now(timezone.utc),
            )
        )

    if to_status == "outdated":
        detail = f"expected agent version {build.agent_version}, reported {agent_version}"
        previous_detail = (
            await db.execute(
                select(WorkstationInstallationEvent.detail)
                .where(
                    WorkstationInstallationEvent.installation_id == installation.id,
                    WorkstationInstallationEvent.event_type == "version_mismatch",
                    WorkstationInstallationEvent.created_at >= installation.package_generated_at,
                )
                .order_by(WorkstationInstallationEvent.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if from_status != "outdated" or previous_detail != detail:
            db.add(
                WorkstationInstallationEvent(
                    installation_id=installation.id,
                    event_type="version_mismatch",
                    from_status=from_status,
                    to_status=to_status,
                    detail=detail,
                    created_at=datetime.now(timezone.utc),
                )
            )

    installation.status = to_status
    installation.last_error = None

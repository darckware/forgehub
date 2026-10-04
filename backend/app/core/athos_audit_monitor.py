"""Pure health classification for Athos's weekly ecosystem audit cron."""

from datetime import datetime, timedelta, timezone

from app.api.routes.foundation import CronJobOut, CronStoreErrorOut
from app.api.schemas.audit import AthosAuditMonitorOut

_JOB_NAME = "ecosystem-weekly-audit"
_SCRIPT = "ecosystem_weekly_audit.sh"
_SCHEDULE = "0 19 * * 0"
_MAX_AUDIT_AGE = timedelta(days=8)


def inspect_athos_audit_job(
    jobs: list[CronJobOut],
    store_errors: list[CronStoreErrorOut],
    last_cron_run_at: datetime | None,
    now: datetime,
) -> AthosAuditMonitorOut:
    """Report scheduler health independently from individual checklist results."""
    athos_jobs = [job for job in jobs if job.profile == "athos"]
    matches = [job for job in athos_jobs if job.name == _JOB_NAME or job.script == _SCRIPT]
    job = next((candidate for candidate in matches if candidate.name == _JOB_NAME), None)
    job = job or (matches[0] if matches else None)
    errors = [error for error in store_errors if error.profile == "athos"]
    issues: list[str] = []
    failed = False

    if errors:
        failed = True
        issues.extend(f"Athos cron store error: {error.error}" for error in errors)
    if len(matches) > 1:
        issues.append("Duplicate Athos weekly audit jobs")
    if job is None:
        issues.append("Athos weekly audit job is not configured")
    else:
        if job.name != _JOB_NAME:
            issues.append(f"Unexpected job name: {job.name}")
        if job.script != _SCRIPT:
            issues.append(f"Unexpected job script: {job.script or 'missing'}")
        if job.schedule_display != _SCHEDULE:
            issues.append(f"Unexpected job schedule: {job.schedule_display or 'missing'}")
        if not job.enabled or job.status != "active":
            issues.append("Athos weekly audit job is disabled or paused")
        if job.health in ("overdue", "never_ran"):
            issues.append(f"Athos weekly audit job health: {job.health}")
        if getattr(job, "script_state", "ok") in ("missing", "broken"):
            issues.append("Athos weekly audit script is missing or broken")
        if job.last_status in ("error", "failed", "fail") or job.health == "error":
            failed = True
            issues.append(f"Athos weekly audit last status: {job.last_status or job.health}")
        if last_cron_run_at is None:
            issues.append("No cron audit run has been recorded in ForgeHub")
        else:
            run_at = last_cron_run_at.replace(tzinfo=timezone.utc) if last_cron_run_at.tzinfo is None else last_cron_run_at
            current = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now
            if current - run_at > _MAX_AUDIT_AGE:
                issues.append("Last cron audit run is older than 8 days")

    state = "failed" if failed else "not_configured" if job is None else "degraded" if issues else "healthy"
    return AthosAuditMonitorOut(
        state=state,
        job_id=job.id if job else None,
        job_name=job.name if job else None,
        script=job.script if job else None,
        schedule=job.schedule_display if job else None,
        enabled=job.enabled if job else None,
        health=job.health if job else None,
        last_run_at=job.last_run_at if job else None,
        last_status=job.last_status if job else None,
        next_run_at=job.next_run_at if job else None,
        last_cron_run_at=last_cron_run_at,
        issues=issues,
    )

"""Pure evidence validity, independent of historical check verdicts.

Evidence stays valid for one period of the check's frequency plus a day of
grace (a weekly check: 8 days, what every check had before frequencies
existed), so a monthly check is not reported stale a week after it ran.
"""
from datetime import datetime, timedelta, timezone
from typing import Literal

EVIDENCE_VALIDITY = timedelta(days=8)
_VALIDITY_BY_FREQUENCY = {
    "daily": timedelta(days=2),
    "weekly": EVIDENCE_VALIDITY,
    "monthly": timedelta(days=32),
    "quarterly": timedelta(days=93),
}
EvidenceState = Literal["fresh", "stale", "never"]


def evidence_validity(frequency: str | None) -> timedelta:
    return _VALIDITY_BY_FREQUENCY.get(frequency or "weekly", EVIDENCE_VALIDITY)


def evidence_freshness(
    recorded_at: datetime | None, now: datetime, frequency: str | None = "weekly"
) -> tuple[EvidenceState, datetime | None]:
    if recorded_at is None:
        return "never", None
    recorded_at = recorded_at.replace(tzinfo=timezone.utc) if recorded_at.tzinfo is None else recorded_at
    now = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now
    expires_at = recorded_at + evidence_validity(frequency)
    return ("fresh" if recorded_at <= now < expires_at else "stale"), expires_at

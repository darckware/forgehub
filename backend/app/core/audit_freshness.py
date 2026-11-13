"""Pure evidence validity, independent of historical check verdicts."""
from datetime import datetime, timedelta, timezone
from typing import Literal

EVIDENCE_VALIDITY = timedelta(days=8)
EvidenceState = Literal["fresh", "stale", "never"]


def evidence_freshness(recorded_at: datetime | None, now: datetime) -> tuple[EvidenceState, datetime | None]:
    if recorded_at is None:
        return "never", None
    recorded_at = recorded_at.replace(tzinfo=timezone.utc) if recorded_at.tzinfo is None else recorded_at
    now = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now
    expires_at = recorded_at + EVIDENCE_VALIDITY
    return ("fresh" if recorded_at <= now < expires_at else "stale"), expires_at

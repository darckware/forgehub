"""Rendering stored instants in the operator's own timezone.

Everything is *stored* in UTC and stays that way -- timezone-aware columns,
`Z`-suffixed in the API, converted by the browser for the UI. That part is
correct and this module does not touch it.

What was wrong is text ForgeHub writes for a person to read: the canonical
header stamped on every dispatch result printed `2026-08-13T18:56:27+00:00`
when the operator's wall clock said 15:56 (2026-08-13, Marcelo: "registrado
com o fuso errado, precisa aplica america/sao_paulo -3h"). A timestamp meant
for a human that silently reads three hours into the future is worse than no
timestamp: it can't be matched against anything else on the machine.

`settings.TIMEZONE` (America/Sao_Paulo by default, editable at Settings ->
System defaults) already existed for exactly this, but only
system_control.py used it, for backup filenames. This makes it shared.
"""
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings


def local_tz() -> ZoneInfo | None:
    """The configured zone, or None if it can't be resolved.

    Never raises: a typo in an operator-editable config file must not take
    down a dispatch. Callers fall back to the instant as-is, which is wrong
    by an offset but still present -- the same trade-off _now_local already
    made for backup filenames."""
    try:
        return ZoneInfo(settings.TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def to_local(value: datetime | None) -> datetime | None:
    """A stored (UTC) instant as wall-clock time in settings.TIMEZONE.

    A naive value is assumed to be UTC, which is what every column in this
    project stores; treating it as local would shift it by the offset in the
    wrong direction and produce a time that never happened.
    """
    if value is None:
        return None
    tz = local_tz()
    if tz is None:
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo("UTC"))
    return value.astimezone(tz)


def format_local(value: datetime | None, fmt: str = "%Y-%m-%d %H:%M:%S %Z") -> str:
    """Human-facing rendering of a stored instant. Empty string for None --
    the absence of a timestamp is meaningful (it never ran) and must not be
    dressed up as a date."""
    local = to_local(value)
    return local.strftime(fmt) if local is not None else ""

"""Script library helpers (Remote Access plan step 1, 2026-10-16).

* `render_script`: the library script ready to run -- each declared parameter
  becomes a variable set before the content, its value quoted for the shell
  (PowerShell single quotes, POSIX `shlex.quote`). Values are never spliced
  into the script text, so a value can't become code.
* `compatible`: whether a script's platform fits a machine's OS.
* `next_run`: when a schedule fires next (once / weekly in its timezone).
"""
from __future__ import annotations

import re
import shlex
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

PARAM_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,40}$")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class ScriptError(ValueError):
    pass


def shell_for(platform: str) -> str:
    return "powershell" if platform == "windows" else "sh"


def compatible(platform: str, os_family: str | None) -> bool:
    """A Windows script runs on Windows; a Linux script on Linux (or a
    machine whose OS was never stated -- every pre-2026-10-15 server); a
    macOS script on macOS."""
    if platform == "linux":
        return os_family in ("linux", None)
    return os_family == platform


def validate_parameters(parameters: list) -> list[dict]:
    out, seen = [], set()
    for p in parameters or []:
        if not isinstance(p, dict):
            raise ScriptError("Each parameter must be an object")
        name = str(p.get("name", "")).strip()
        if not PARAM_NAME_RE.match(name):
            raise ScriptError(f"Invalid parameter name '{name}' (use UPPER_CASE letters, digits, _)")
        if name in seen:
            raise ScriptError(f"Parameter '{name}' declared twice")
        seen.add(name)
        default = p.get("default")
        out.append({
            "name": name,
            "label": str(p.get("label") or name)[:120],
            "required": bool(p.get("required", False)),
            "default": None if default in (None, "") else str(default),
            "secret": bool(p.get("secret", False)),
        })
    return out


def resolve_values(parameters: list[dict], values: dict | None) -> tuple[dict[str, str], list[str]]:
    """(name -> value, secret values to mask). Unknown names are refused."""
    values = {k: ("" if v is None else str(v)) for k, v in (values or {}).items()}
    declared = {p["name"]: p for p in parameters}
    if unknown := set(values) - set(declared):
        raise ScriptError(f"Unknown parameter(s): {', '.join(sorted(unknown))}")
    resolved, secrets = {}, []
    for p in parameters:
        value = values.get(p["name"])
        if value in (None, ""):
            value = p["default"]
        if value in (None, ""):
            if p["required"]:
                raise ScriptError(f"Parameter '{p['label']}' is required")
            value = ""
        if "\x00" in value:
            raise ScriptError(f"Parameter '{p['label']}' has an invalid character")
        resolved[p["name"]] = value
        if p["secret"] and value:
            secrets.append(value)
    return resolved, secrets


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def render_script(platform: str, content: str, values: dict[str, str]) -> str:
    if not values:
        return content
    if platform == "windows":
        prelude = "".join(f"${name} = {_ps_quote(value)}\n" for name, value in values.items())
    else:
        prelude = "".join(f"{name}={shlex.quote(value)}\n" for name, value in values.items())
    return prelude + content


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ScriptError(f"Unknown timezone '{name}'") from exc


def validate_schedule(kind: str, run_at: datetime | None, weekdays: list | None,
                      time_of_day: str | None, tz: str) -> None:
    _zone(tz)
    if kind == "once":
        if run_at is None:
            raise ScriptError("A one-time schedule needs a date and time")
    elif kind == "weekly":
        if not weekdays or any(d not in range(1, 8) for d in weekdays):
            raise ScriptError("Pick at least one weekday")
        if not time_of_day or not TIME_RE.match(time_of_day):
            raise ScriptError("Time must be HH:MM")
    else:
        raise ScriptError("Unknown schedule kind")


def next_run(kind: str, run_at: datetime | None, weekdays: list | None, time_of_day: str | None,
             tz: str, after: datetime) -> datetime | None:
    """Next fire time strictly after `after` (UTC-aware), or None when a
    one-time schedule is in the past."""
    if kind == "once":
        if run_at is None:
            return None
        run_at = run_at if run_at.tzinfo else run_at.replace(tzinfo=_zone(tz))
        return run_at.astimezone(timezone.utc) if run_at > after else None
    zone = _zone(tz)
    hour, minute = (int(x) for x in (time_of_day or "00:00").split(":"))
    local_after = after.astimezone(zone)
    for offset in range(0, 8):
        day = (local_after + timedelta(days=offset)).date()
        if day.isoweekday() not in (weekdays or []):
            continue
        candidate = datetime(day.year, day.month, day.day, hour, minute, tzinfo=zone)
        if candidate > local_after:
            return candidate.astimezone(timezone.utc)
    return None

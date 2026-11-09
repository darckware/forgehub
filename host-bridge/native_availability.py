"""Read only bounded official Codex quota events; never read authentication contents."""
from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime
from pathlib import Path

MAX_AGE_SECONDS = 300
MAX_FILES = 24
MAX_ENTRIES = 1200
MAX_BYTES = 2_000_000
MAX_LINE_BYTES = 64000
MAX_SECONDS = 0.5


def observe_codex_availability(home: Path, now: datetime) -> dict:
    """home is the runner's actual CODEX_HOME, supplied by the bridge, not a request path.

    Only events newer than current auth metadata and younger than five minutes qualify.
    Unknown latest observations supersede older positive observations (fail closed).
    """
    unknown = {"available": None, "observed_at": None, "reason": "No fresh native quota observation"}
    if now.tzinfo is None:
        return unknown
    deadline = time.monotonic() + MAX_SECONDS
    latest = None
    try:
        root = home.resolve(strict=True)
        auth = root / "auth.json"
        if auth.is_symlink():
            return unknown
        auth_stamp = auth.stat().st_mtime
        sessions = root / "sessions"
        if sessions.is_symlink():
            return unknown
        entries = 0
        paths = []
        oldest_mtime = max(auth_stamp, now.timestamp() - MAX_AGE_SECONDS)
        for directory, dirs, files in os.walk(sessions, followlinks=False):
            entries += len(dirs) + len(files)
            if entries > MAX_ENTRIES or time.monotonic() > deadline:
                return unknown
            dirs[:] = sorted(d for d in dirs if not (Path(directory) / d).is_symlink())
            for name in files:
                path = Path(directory) / name
                if name.endswith(".jsonl") and not path.is_symlink():
                    modified_at = path.stat().st_mtime
                    # Historical transcripts cannot contain a current official observation.
                    # Do not let their large tails consume the current-session byte budget.
                    if modified_at >= oldest_mtime:
                        paths.append((modified_at, path))
        budget = MAX_BYTES
        for _, path in sorted(paths, reverse=True)[:MAX_FILES]:
            if time.monotonic() > deadline or budget <= 0:
                return unknown
            # Tail sessions: bounded reads, no full transcript, no transcript in return values.
            size = path.stat().st_size
            count = min(size, budget, 256000)
            budget -= count
            with path.open("rb") as handle:
                if size > count:
                    handle.seek(size - count)
                data = handle.read(count)
                if size > count:
                    # The first line may begin before the tail. Stay within the byte budget.
                    data = data.partition(b"\n")[2]
            for line in data.splitlines():
                if len(line) > MAX_LINE_BYTES or time.monotonic() > deadline:
                    continue
                try:
                    event = json.loads(line)
                    payload = event.get("payload", {})
                    if event.get("type") != "event_msg" or payload.get("type") != "token_count":
                        continue
                    stamp = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
                    age = (now - stamp).total_seconds()
                    if stamp.timestamp() <= auth_stamp or not 0 <= age <= MAX_AGE_SECONDS:
                        continue
                    limits = payload.get("rate_limits")
                    values = []
                    for key in ("primary", "secondary"):
                        window = limits.get(key, {}) if isinstance(limits, dict) else {}
                        used = window.get("used_percent")
                        minutes = window.get("window_minutes")
                        if (isinstance(used, bool) or not isinstance(used, (int, float))
                                or not math.isfinite(used) or not 0 <= used <= 100
                                or isinstance(minutes, bool) or not isinstance(minutes, (int, float))
                                or not math.isfinite(minutes) or minutes <= 0):
                            values.append(None)
                        else:
                            values.append(used)
                    # Distinct ordered horizons are required, not two copies of one window.
                    if None not in values and limits["secondary"]["window_minutes"] <= limits["primary"]["window_minutes"]:
                        values = [None, None]
                    available = None if None in values else all(v < 100 for v in values)
                    sample = {"available": available, "observed_at": stamp.isoformat(),
                              "reason": "Native quota available" if available is True else
                              "Native quota exhausted" if available is False else "Native quota windows unknown"}
                    if latest is None or stamp > latest[0]:
                        latest = stamp, sample
                    elif stamp == latest[0] and latest[1]["available"] != available:
                        latest = stamp, {**sample, "available": None, "reason": "Native quota observations conflict"}
                except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
                    continue
        # An authentication change during traversal invalidates the complete observation.
        if auth.stat().st_mtime != auth_stamp:
            return unknown
    except (OSError, ValueError):
        return unknown
    return latest[1] if latest else unknown

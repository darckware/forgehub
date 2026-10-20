"""Operational state of a cron job's profile-owned script."""

from pathlib import Path
from typing import Literal


ScriptState = Literal["ok", "missing", "broken", "none"]


def classify_script(path: Path | None) -> ScriptState:
    if path is None:
        return "none"
    try:
        if path.is_symlink() and not path.exists():
            return "broken"
        if not path.exists():
            return "missing"
        if not path.is_file() or not (path.stat().st_mode & 0o444):
            return "broken"
        return "ok"
    except OSError:
        return "broken"

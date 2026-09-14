"""Resolve governed agent runtime executables without host-specific hardcodes."""

from __future__ import annotations

import os
import shutil
from collections.abc import Mapping
from pathlib import Path


def validate_working_directory(value: str) -> Path:
    path = Path(value)
    if not value.strip() or not path.is_absolute():
        raise ValueError("Working directory must be an explicit absolute path")
    if not path.is_dir():
        raise ValueError("Working directory does not exist or is not a directory")
    if not os.access(path, os.R_OK | os.X_OK):
        raise ValueError("Working directory is not accessible to the agent runner")
    return path


def resolve_runtime_executable(
    runtime: str,
    *,
    env: Mapping[str, str] | None = None,
) -> str:
    """Return an executable configured explicitly or discoverable on PATH."""
    runtime_env = os.environ if env is None else env
    variable = f"FORGEHUB_{runtime.upper()}_BIN"
    configured = runtime_env.get(variable, "").strip()
    if configured:
        candidate = Path(configured)
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
        raise RuntimeError(f"{variable} does not point to an executable file")

    discovered = shutil.which(runtime, path=runtime_env.get("PATH"))
    if discovered:
        return discovered
    raise RuntimeError(f"{runtime} executable was not found on PATH")

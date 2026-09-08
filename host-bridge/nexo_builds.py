"""Build the Nexo remote agent from the host's allowlisted source checkout.

This module deliberately has no inputs for source paths, revisions, commands,
or artifact names.  The bridge is the trust boundary between ForgeHub and the
host toolchain, so callers can select only a supported target platform.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path
from typing import Literal


NEXO_SOURCE_PATH = Path(os.environ.get("NEXO_SOURCE_PATH", "/root/project/nexo"))
NEXO_ARTIFACT_ROOT = Path(
    os.environ.get("NEXO_ARTIFACT_ROOT", "/root/forgehub-data/nexo-agent-artifacts")
)
SUPPORTED_OS_KINDS = frozenset({"linux", "windows"})
BUILD_TIMEOUT_SECONDS = 600
MAX_LOG_EXCERPT_LENGTH = 2_000
_SHA_RE = re.compile(r"^[0-9a-f]{7,64}$")


class NexoBuildError(RuntimeError):
    """A build failure whose diagnostic text is safe to expose to the caller."""


def _require_os_kind(os_kind: str) -> Literal["linux", "windows"]:
    if os_kind not in SUPPORTED_OS_KINDS:
        raise ValueError("Unsupported Nexo build platform")
    return os_kind  # type: ignore[return-value]


def artifact_name(os_kind: str, git_sha: str) -> str:
    """Return the fixed artifact filename after validating fixed path segments."""
    _require_os_kind(os_kind)
    if not _SHA_RE.fullmatch(git_sha):
        raise ValueError("Invalid Nexo source revision")
    return "nexo-remote-agent.exe" if os_kind == "windows" else "nexo-remote-agent"


def build_environment(os_kind: str) -> dict[str, str]:
    """Return the complete, allowlisted Go target environment."""
    _require_os_kind(os_kind)
    return {"GOOS": os_kind, "GOARCH": "amd64", "CGO_ENABLED": "0"}


def build_command(os_kind: str, agent_version: str, artifact_path: Path) -> list[str]:
    """Return the static Go command for one supported target platform."""
    _require_os_kind(os_kind)
    return [
        "go",
        "build",
        "-trimpath",
        "-ldflags",
        f"-X main.Version={agent_version}",
        "-o",
        str(artifact_path),
        "./cmd/remote-agent",
    ]


def _redact_log(value: str) -> str:
    """Remove common credential formats before diagnostics leave the host."""
    value = re.sub(
        r"(?i)(authorization\s*:\s*bearer\s+)[^\s,;]+",
        r"\1[REDACTED]",
        value,
    )
    value = re.sub(
        r"(?i)((?:api[_-]?key|auth(?:orization)?[_-]?token|token|password|secret)\s*[=:]\s*)[^\s,;]+",
        r"\1[REDACTED]",
        value,
    )
    value = re.sub(r"\b(?:sk|key)-[A-Za-z0-9_-]{16,}\b", "[REDACTED]", value)
    return value


def _log_excerpt(stdout: str | bytes | None, stderr: str | bytes | None, *, budget: int) -> str:
    def _as_text(value: str | bytes | None) -> str:
        if isinstance(value, bytes):
            return value.decode(errors="replace")
        return value or ""

    return _redact_log("\n".join(part for part in (_as_text(stdout), _as_text(stderr)) if part))[:budget]


def _failure(message: str, stdout: str | bytes | None = None, stderr: str | bytes | None = None) -> NexoBuildError:
    excerpt = _log_excerpt(stdout, stderr, budget=max(0, MAX_LOG_EXCERPT_LENGTH - len(message) - 2))
    return NexoBuildError(f"{message}: {excerpt}" if excerpt else message)


def _run_git(*arguments: str) -> str:
    command = ["git", "-C", str(NEXO_SOURCE_PATH), *arguments]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise _failure("Timed out inspecting Nexo source", exc.output, exc.stderr) from exc
    if result.returncode != 0:
        raise _failure("Unable to inspect Nexo source", result.stdout, result.stderr)
    return result.stdout.strip()


def inspect_source() -> dict[str, str]:
    """Read the fixed checkout's revision and immutable build version."""
    git_sha = _run_git("rev-parse", "HEAD")
    if not _SHA_RE.fullmatch(git_sha):
        raise NexoBuildError("Nexo source returned an invalid Git revision")
    agent_version = _run_git("describe", "--tags", "--always", "--dirty")
    if agent_version.endswith("-dirty"):
        raise NexoBuildError("Nexo source is dirty; catalog builds require a clean checkout")
    if not agent_version:
        raise NexoBuildError("Nexo source returned an empty agent version")
    return {"git_sha": git_sha, "agent_version": agent_version}


def _sha256_and_size(artifact_path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with artifact_path.open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def build_agent(os_kind: Literal["linux", "windows"]) -> dict[str, str | int]:
    """Compile the fixed Nexo checkout for a single allowlisted platform."""
    os_kind = _require_os_kind(os_kind)
    source = inspect_source()
    artifact_path = (
        NEXO_ARTIFACT_ROOT
        / source["git_sha"]
        / os_kind
        / artifact_name(os_kind, source["git_sha"])
    )
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    command = build_command(os_kind, source["agent_version"], artifact_path)
    environment = {**os.environ, **build_environment(os_kind)}
    try:
        result = subprocess.run(
            command,
            cwd=NEXO_SOURCE_PATH,
            env=environment,
            capture_output=True,
            text=True,
            timeout=BUILD_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise _failure("Nexo agent build timed out", exc.output, exc.stderr) from exc
    if result.returncode != 0:
        raise _failure("Nexo agent build failed", result.stdout, result.stderr)
    if not artifact_path.is_file():
        raise NexoBuildError("Nexo agent build completed without an artifact")

    sha256, artifact_size = _sha256_and_size(artifact_path)
    return {
        **source,
        "os_kind": os_kind,
        "artifact_path": str(artifact_path.relative_to(NEXO_ARTIFACT_ROOT)),
        "artifact_size": artifact_size,
        "sha256": sha256,
        "log_excerpt": _log_excerpt(result.stdout, result.stderr, budget=MAX_LOG_EXCERPT_LENGTH),
    }

"""Build the Nexo remote agent from the host's allowlisted source checkout.

This module deliberately has no inputs for source paths, revisions, commands,
or artifact names.  The bridge is the trust boundary between ForgeHub and the
host toolchain, so callers can select only a supported target platform.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
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
_TRUSTED_GO_ENVIRONMENT_KEYS = ("PATH", "HOME", "TMPDIR", "GOCACHE")
_METADATA_SUFFIX = ".metadata.json"


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


def trusted_build_environment(os_kind: str) -> dict[str, str]:
    """Provide Go only the host paths it needs, never bridge request secrets."""
    environment = {
        key: os.environ[key]
        for key in _TRUSTED_GO_ENVIRONMENT_KEYS
        if key in os.environ
    }
    environment["GOENV"] = "off"
    environment.update(build_environment(os_kind))
    return environment


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
    if _run_git("status", "--porcelain", "--untracked-files=all"):
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


def _artifact_metadata(
    source: dict[str, str],
    os_kind: Literal["linux", "windows"],
    artifact_path: Path,
) -> dict[str, str | int]:
    if not artifact_path.is_file():
        raise NexoBuildError("Nexo artifact path is not a regular file")
    sha256, artifact_size = _sha256_and_size(artifact_path)
    return {
        **source,
        "os_kind": os_kind,
        "artifact_size": artifact_size,
        "sha256": sha256,
    }


def _metadata_path(artifact_path: Path) -> Path:
    return artifact_path.parent / f"{artifact_path.name}{_METADATA_SUFFIX}"


def _read_metadata(metadata_path: Path) -> dict[str, str | int]:
    try:
        metadata = json.loads(metadata_path.read_text())
    except (OSError, ValueError) as exc:
        raise NexoBuildError("Nexo artifact metadata is missing or invalid") from exc
    required_fields = {"git_sha", "agent_version", "os_kind", "artifact_size", "sha256"}
    if not isinstance(metadata, dict) or not required_fields <= metadata.keys():
        raise NexoBuildError("Nexo artifact metadata is missing required fields")
    return metadata


def _artifact_response(metadata: dict[str, str | int], artifact_path: Path, log_excerpt: str) -> dict[str, str | int]:
    actual_metadata = _artifact_metadata(
        {"git_sha": str(metadata["git_sha"]), "agent_version": str(metadata["agent_version"])},
        str(metadata["os_kind"]),
        artifact_path,
    )
    for key in ("git_sha", "agent_version", "os_kind", "artifact_size", "sha256"):
        if actual_metadata[key] != metadata[key]:
            raise NexoBuildError("Nexo artifact does not match its immutable metadata")
    return {
        **actual_metadata,
        "artifact_path": str(artifact_path.relative_to(NEXO_ARTIFACT_ROOT)),
        "log_excerpt": log_excerpt,
    }


def _existing_artifact_response(
    source: dict[str, str],
    os_kind: Literal["linux", "windows"],
    artifact_path: Path,
) -> dict[str, str | int]:
    metadata = _read_metadata(_metadata_path(artifact_path))
    if metadata["git_sha"] != source["git_sha"] or metadata["os_kind"] != os_kind:
        raise NexoBuildError("Nexo artifact metadata does not match the requested build")
    return _artifact_response(metadata, artifact_path, "")


def _write_metadata_temporary(metadata: dict[str, str | int], artifact_path: Path) -> Path:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{artifact_path.name}-metadata-",
        suffix=".json",
        dir=artifact_path.parent,
    )
    with os.fdopen(descriptor, "w") as temporary_file:
        json.dump(metadata, temporary_file, sort_keys=True, separators=(",", ":"))
        temporary_file.flush()
        os.fsync(temporary_file.fileno())
    return Path(temporary_name)


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
    if artifact_path.exists():
        return _existing_artifact_response(source, os_kind, artifact_path)

    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{artifact_name(os_kind, source['git_sha'])}-",
        dir=artifact_path.parent,
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    command = build_command(os_kind, source["agent_version"], temporary_path)
    try:
        try:
            result = subprocess.run(
                command,
                cwd=NEXO_SOURCE_PATH,
                env=trusted_build_environment(os_kind),
                capture_output=True,
                text=True,
                timeout=BUILD_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise _failure("Nexo agent build timed out", exc.output, exc.stderr) from exc
        if result.returncode != 0:
            raise _failure("Nexo agent build failed", result.stdout, result.stderr)
        if not temporary_path.is_file():
            raise NexoBuildError("Nexo agent build completed without an artifact")
        if inspect_source() != source:
            raise NexoBuildError("Nexo source changed while the agent was being built")

        metadata = _artifact_metadata(source, os_kind, temporary_path)
        temporary_metadata_path = _write_metadata_temporary(metadata, artifact_path)
        try:
            try:
                os.link(temporary_path, artifact_path)
            except FileExistsError:
                return _existing_artifact_response(source, os_kind, artifact_path)

            try:
                os.link(temporary_metadata_path, _metadata_path(artifact_path))
            except FileExistsError:
                return _existing_artifact_response(source, os_kind, artifact_path)
            return _artifact_response(
                metadata,
                artifact_path,
                _log_excerpt(result.stdout, result.stderr, budget=MAX_LOG_EXCERPT_LENGTH),
            )
        finally:
            temporary_metadata_path.unlink(missing_ok=True)
    finally:
        temporary_path.unlink(missing_ok=True)

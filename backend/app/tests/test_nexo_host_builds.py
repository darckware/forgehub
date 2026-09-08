"""Unit tests for the fixed, host-only Nexo agent build boundary."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest


HOST_BRIDGE_DIR = Path(__file__).resolve().parents[3] / "host-bridge"
if str(HOST_BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(HOST_BRIDGE_DIR))

from nexo_builds import (  # noqa: E402
    NexoBuildError,
    artifact_name,
    build_agent,
    build_command,
    build_environment,
    inspect_source,
)


@pytest.fixture(scope="session", autouse=True)
def clean_stale_agent_fixtures():
    """Override the database cleanup fixture: these bridge units use no DB."""
    yield


@pytest.fixture(autouse=True)
def test_suite_agent():
    """Override the database-backed agent fixture for this self-contained module."""
    yield


def test_build_command_is_fixed_for_windows(tmp_path):
    """Changing the target or ldflags would make produced agents unusable."""
    command = build_command("windows", "abc123", tmp_path / "agent.exe")

    assert command == [
        "go",
        "build",
        "-trimpath",
        "-ldflags",
        "-X main.Version=abc123",
        "-o",
        str(tmp_path / "agent.exe"),
        "./cmd/remote-agent",
    ]
    assert build_environment("windows") == {
        "GOOS": "windows",
        "GOARCH": "amd64",
        "CGO_ENABLED": "0",
    }


def test_platform_rejects_command_like_input():
    """Accepting platform text as a command fragment would break the allowlist."""
    with pytest.raises(ValueError):
        artifact_name("linux;rm -rf /", "abc123")


def test_inspect_source_reads_revision_and_version_from_the_fixed_repository(monkeypatch, tmp_path):
    """Using caller-supplied source metadata would undermine catalog provenance."""
    import nexo_builds

    monkeypatch.setattr(nexo_builds, "NEXO_SOURCE_PATH", tmp_path / "nexo")
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[-2:] == ["rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, "a" * 40 + "\n", "")
        return subprocess.CompletedProcess(command, 0, "v1.2.3\n", "")

    monkeypatch.setattr(nexo_builds.subprocess, "run", fake_run)

    assert inspect_source() == {"git_sha": "a" * 40, "agent_version": "v1.2.3"}
    assert calls == [
        ["git", "-C", str(tmp_path / "nexo"), "rev-parse", "HEAD"],
        ["git", "-C", str(tmp_path / "nexo"), "describe", "--tags", "--always", "--dirty"],
    ]


def test_inspect_source_rejects_a_dirty_repository(monkeypatch, tmp_path):
    """Catalog builds must not claim a reproducible revision for dirty source."""
    import nexo_builds

    monkeypatch.setattr(nexo_builds, "NEXO_SOURCE_PATH", tmp_path / "nexo")

    def fake_run(command, **kwargs):
        output = "b" * 40 if command[-2:] == ["rev-parse", "HEAD"] else "v1.2.3-dirty"
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr(nexo_builds.subprocess, "run", fake_run)

    with pytest.raises(NexoBuildError, match="dirty"):
        inspect_source()


def test_failed_build_redacts_and_bounds_compiler_output(monkeypatch, tmp_path):
    """Compiler diagnostics must not leak credentials into bridge responses or logs."""
    import nexo_builds

    source_path = tmp_path / "nexo"
    artifact_root = tmp_path / "artifacts"
    monkeypatch.setattr(nexo_builds, "NEXO_SOURCE_PATH", source_path)
    monkeypatch.setattr(nexo_builds, "NEXO_ARTIFACT_ROOT", artifact_root)

    def fake_run(command, **kwargs):
        if command[0] == "git":
            output = "c" * 40 if command[-2:] == ["rev-parse", "HEAD"] else "v1.2.3"
            return subprocess.CompletedProcess(command, 0, output, "")
        return subprocess.CompletedProcess(
            command,
            1,
            "api_key=super-secret-token\n" + "x" * 2_500,
            "Authorization: Bearer another-secret",
        )

    monkeypatch.setattr(nexo_builds.subprocess, "run", fake_run)

    with pytest.raises(NexoBuildError) as exc_info:
        build_agent("linux")

    message = str(exc_info.value)
    assert "super-secret-token" not in message
    assert "another-secret" not in message
    assert "[REDACTED]" in message
    assert len(message) <= 2_000


def test_build_agent_writes_a_hashed_artifact_under_the_fixed_root(monkeypatch, tmp_path):
    """Changing the source-root layout or checksum would break downstream ingestion."""
    import nexo_builds

    source_path = tmp_path / "nexo"
    artifact_root = tmp_path / "artifacts"
    monkeypatch.setattr(nexo_builds, "NEXO_SOURCE_PATH", source_path)
    monkeypatch.setattr(nexo_builds, "NEXO_ARTIFACT_ROOT", artifact_root)
    calls: list[tuple[list[str], dict]] = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if command[0] == "git":
            output = "d" * 40 if command[-2:] == ["rev-parse", "HEAD"] else "v1.2.3"
            return subprocess.CompletedProcess(command, 0, output, "")
        artifact_path = Path(command[command.index("-o") + 1])
        artifact_path.write_bytes(b"agent-bytes")
        return subprocess.CompletedProcess(command, 0, "build complete", "")

    monkeypatch.setattr(nexo_builds.subprocess, "run", fake_run)

    result = build_agent("linux")

    artifact_path = artifact_root / ("d" * 40) / "linux" / "nexo-remote-agent"
    assert result == {
        "git_sha": "d" * 40,
        "agent_version": "v1.2.3",
        "os_kind": "linux",
        "artifact_path": ("d" * 40) + "/linux/nexo-remote-agent",
        "artifact_size": 11,
        "sha256": hashlib.sha256(b"agent-bytes").hexdigest(),
        "log_excerpt": "build complete",
    }
    command, kwargs = calls[-1]
    assert command == [
        "go",
        "build",
        "-trimpath",
        "-ldflags",
        "-X main.Version=v1.2.3",
        "-o",
        str(artifact_path),
        "./cmd/remote-agent",
    ]
    assert kwargs["cwd"] == source_path
    assert kwargs["timeout"] == 600
    assert "shell" not in kwargs

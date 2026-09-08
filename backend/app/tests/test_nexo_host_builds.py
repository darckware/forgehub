"""Unit tests for the fixed, host-only Nexo agent build boundary."""

from __future__ import annotations

import hashlib
import json
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
        if command[-1] == "--dirty":
            return subprocess.CompletedProcess(command, 0, "v1.2.3\n", "")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(nexo_builds.subprocess, "run", fake_run)

    assert inspect_source() == {"git_sha": "a" * 40, "agent_version": "v1.2.3"}
    assert calls == [
        ["git", "-C", str(tmp_path / "nexo"), "rev-parse", "HEAD"],
        ["git", "-C", str(tmp_path / "nexo"), "describe", "--tags", "--always", "--dirty"],
        ["git", "-C", str(tmp_path / "nexo"), "status", "--porcelain", "--untracked-files=all"],
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


def test_inspect_source_rejects_untracked_files(monkeypatch, tmp_path):
    """Untracked source could change an agent binary without changing its SHA."""
    import nexo_builds

    monkeypatch.setattr(nexo_builds, "NEXO_SOURCE_PATH", tmp_path / "nexo")

    def fake_run(command, **kwargs):
        if command[-2:] == ["rev-parse", "HEAD"]:
            output = "e" * 40
        elif command[-1] == "--dirty":
            output = "v1.2.3"
        else:
            output = "?? cmd/remote-agent/injected.go\n"
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
            if command[-2:] == ["rev-parse", "HEAD"]:
                output = "c" * 40
            elif command[-1] == "--dirty":
                output = "v1.2.3"
            else:
                output = ""
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
            if command[-2:] == ["rev-parse", "HEAD"]:
                output = "d" * 40
            elif command[-1] == "--dirty":
                output = "v1.2.3"
            else:
                output = ""
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
    command, kwargs = next((call, options) for call, options in calls if call[0] == "go")
    assert command[:5] == [
        "go",
        "build",
        "-trimpath",
        "-ldflags",
        "-X main.Version=v1.2.3",
    ]
    assert command[-1] == "./cmd/remote-agent"
    assert command[5] == "-o"
    assert Path(command[6]).parent == artifact_path.parent
    assert Path(command[6]) != artifact_path
    assert kwargs["cwd"] == source_path
    assert kwargs["timeout"] == 600
    assert "shell" not in kwargs


def test_build_agent_reuses_existing_sha_platform_artifact(monkeypatch, tmp_path):
    """A second request for the same SHA/platform must never replace its binary."""
    import nexo_builds

    source_path = tmp_path / "nexo"
    artifact_root = tmp_path / "artifacts"
    artifact_path = artifact_root / ("f" * 40) / "linux" / "nexo-remote-agent"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(b"first-published-agent")
    (artifact_path.parent / f"{artifact_path.name}.metadata.json").write_text(
        json.dumps(
            {
                "git_sha": "f" * 40,
                "agent_version": "v1.2.3",
                "os_kind": "linux",
                "artifact_size": len(b"first-published-agent"),
                "sha256": hashlib.sha256(b"first-published-agent").hexdigest(),
            }
        )
    )
    monkeypatch.setattr(nexo_builds, "NEXO_SOURCE_PATH", source_path)
    monkeypatch.setattr(nexo_builds, "NEXO_ARTIFACT_ROOT", artifact_root)

    def fake_run(command, **kwargs):
        if command[0] == "go":
            pytest.fail("an existing immutable artifact must be reused")
        if command[-2:] == ["rev-parse", "HEAD"]:
            output = "f" * 40
        elif command[-1] == "--dirty":
            output = "v1.2.3"
        else:
            output = ""
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr(nexo_builds.subprocess, "run", fake_run)

    result = build_agent("linux")

    assert artifact_path.read_bytes() == b"first-published-agent"
    assert result["artifact_size"] == len(b"first-published-agent")
    assert result["sha256"] == hashlib.sha256(b"first-published-agent").hexdigest()


def test_build_agent_revalidates_source_before_publishing(monkeypatch, tmp_path):
    """A source change during compilation must not be published under the old SHA."""
    import nexo_builds

    source_path = tmp_path / "nexo"
    artifact_root = tmp_path / "artifacts"
    monkeypatch.setattr(nexo_builds, "NEXO_SOURCE_PATH", source_path)
    monkeypatch.setattr(nexo_builds, "NEXO_ARTIFACT_ROOT", artifact_root)
    build_started = False

    def fake_run(command, **kwargs):
        nonlocal build_started
        if command[0] == "go":
            build_started = True
            Path(command[command.index("-o") + 1]).write_bytes(b"changed-source-agent")
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[-2:] == ["rev-parse", "HEAD"]:
            output = ("b" if build_started else "a") * 40
        elif command[-1] == "--dirty":
            output = "v1.2.3"
        else:
            output = ""
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr(nexo_builds.subprocess, "run", fake_run)

    with pytest.raises(NexoBuildError, match="changed"):
        build_agent("linux")

    assert not (artifact_root / ("a" * 40) / "linux" / "nexo-remote-agent").exists()


def test_build_agent_uses_only_the_trusted_go_environment(monkeypatch, tmp_path):
    """Inherited bridge secrets and Go control flags must not influence compiler execution."""
    import nexo_builds

    source_path = tmp_path / "nexo"
    artifact_root = tmp_path / "artifacts"
    monkeypatch.setattr(nexo_builds, "NEXO_SOURCE_PATH", source_path)
    monkeypatch.setattr(nexo_builds, "NEXO_ARTIFACT_ROOT", artifact_root)
    monkeypatch.setenv("PATH", "/trusted/bin")
    monkeypatch.setenv("HOME", "/trusted/home")
    monkeypatch.setenv("TMPDIR", "/trusted/tmp")
    monkeypatch.setenv("GOCACHE", "/trusted/cache")
    monkeypatch.setenv("FORGEHUB_BRIDGE_TOKEN", "bridge-secret")
    monkeypatch.setenv("GOFLAGS", "-mod=vendor")
    monkeypatch.setenv("GOWORK", "/tmp/unsafe.work")
    monkeypatch.setenv("GOENV", "/tmp/unsafe.env")
    monkeypatch.setenv("GOTOOLCHAIN", "go1.99.0")
    captured_environment: dict[str, str] | None = None

    def fake_run(command, **kwargs):
        nonlocal captured_environment
        if command[0] == "git":
            if command[-2:] == ["rev-parse", "HEAD"]:
                output = "1" * 40
            elif command[-1] == "--dirty":
                output = "v1.2.3"
            else:
                output = ""
            return subprocess.CompletedProcess(command, 0, output, "")
        captured_environment = kwargs["env"]
        Path(command[command.index("-o") + 1]).write_bytes(b"isolated-agent")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(nexo_builds.subprocess, "run", fake_run)

    build_agent("linux")

    assert captured_environment == {
        "PATH": "/trusted/bin",
        "HOME": "/trusted/home",
        "TMPDIR": "/trusted/tmp",
        "GOCACHE": "/trusted/cache",
        "GOOS": "linux",
        "GOARCH": "amd64",
        "CGO_ENABLED": "0",
        "GOENV": "off",
    }


def test_build_agent_reuses_published_version_when_tags_change(monkeypatch, tmp_path):
    """Moving a tag at one SHA must not relabel an already-published binary."""
    import nexo_builds

    source_path = tmp_path / "nexo"
    artifact_root = tmp_path / "artifacts"
    monkeypatch.setattr(nexo_builds, "NEXO_SOURCE_PATH", source_path)
    monkeypatch.setattr(nexo_builds, "NEXO_ARTIFACT_ROOT", artifact_root)
    agent_version = "v1.0.0"
    go_builds = 0

    def fake_run(command, **kwargs):
        nonlocal go_builds
        if command[0] == "go":
            go_builds += 1
            Path(command[command.index("-o") + 1]).write_bytes(b"versioned-agent")
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[-2:] == ["rev-parse", "HEAD"]:
            output = "2" * 40
        elif command[-1] == "--dirty":
            output = agent_version
        else:
            output = ""
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr(nexo_builds.subprocess, "run", fake_run)

    first = build_agent("linux")
    agent_version = "v1.1.0"
    reused = build_agent("linux")

    metadata_path = artifact_root / ("2" * 40) / "linux" / "nexo-remote-agent.metadata.json"
    assert json.loads(metadata_path.read_text()) == {
        "agent_version": "v1.0.0",
        "artifact_size": len(b"versioned-agent"),
        "git_sha": "2" * 40,
        "os_kind": "linux",
        "sha256": hashlib.sha256(b"versioned-agent").hexdigest(),
    }
    assert first["agent_version"] == reused["agent_version"] == "v1.0.0"
    assert go_builds == 1

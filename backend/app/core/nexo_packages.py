"""Materialize workstation-specific Nexo packages from verified build artifacts."""

from __future__ import annotations

import hashlib
import json
import re
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import yaml

from app.core import nexo_builds
from app.core.config import settings
from app.db.models.client import Workstation
from app.db.models.nexo_installation import NexoAgentBuild


_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


class NexoPackageError(RuntimeError):
    """A package validation/materialization error safe to return to an admin."""


@dataclass(frozen=True)
class PackageMetadata:
    path: Path
    filename: str
    size: int
    sha256: str
    generated_at: datetime


def _write_entry(archive: ZipFile, name: str, content: bytes, mode: int) -> None:
    info = ZipInfo(name, date_time=_ZIP_TIMESTAMP)
    info.create_system = 3
    info.compress_type = ZIP_DEFLATED
    info.external_attr = (stat.S_IFREG | mode) << 16
    archive.writestr(info, content)


def _sha256_and_size(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
                size += len(chunk)
    except OSError as exc:
        raise NexoPackageError("Nexo build artifact could not be read") from exc
    return digest.hexdigest(), size


def _read_artifact_bytes(path: Path) -> bytes:
    try:
        with path.open("rb") as source:
            return source.read()
    except OSError as exc:
        raise NexoPackageError("Nexo build artifact could not be read") from exc


def _validated_artifact(build: NexoAgentBuild) -> bytes:
    if (
        build.status != "ready"
        or build.artifact_path is None
        or build.artifact_size is None
        or build.sha256 is None
    ):
        raise NexoPackageError("Nexo build is not ready")
    if not _SHA_PATTERN.fullmatch(build.git_sha):
        raise NexoPackageError("Nexo build metadata is invalid")
    try:
        artifact_path, _ = nexo_builds.resolve_artifact_path(build.artifact_path)
    except nexo_builds.NexoBuildBridgeError as exc:
        raise NexoPackageError(exc.detail) from exc
    binary = _read_artifact_bytes(artifact_path)
    if hashlib.sha256(binary).hexdigest() != build.sha256 or len(binary) != build.artifact_size:
        raise NexoPackageError("Nexo build artifact failed integrity verification")
    return binary


def _validated_ingestion_url() -> str:
    value = settings.NEXO_INGESTION_URL.strip()
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise NexoPackageError("NEXO_INGESTION_URL must be a valid HTTPS URL")
    return value


def _agent_config(os_kind: str, raw_token: str) -> dict[str, object]:
    linux = os_kind == "linux"
    return {
        "endpoint_url": _validated_ingestion_url(),
        "device_token": raw_token,
        "report_interval": "5m",
        "critical_services": ["sshd", "nginx"] if linux else [],
        "unauthorized_software": ["AnyDesk", "HopToDesk", "TeamViewer"],
        "backup_paths": ["/backup"] if linux else [r"C:\Backup"],
        "backup_max_age": "24h",
        "disk_paths": ["/", "/backup"] if linux else ["C:\\"],
    }


_LINUX_INSTALLER = b"""#!/bin/sh
set -eu
install -d -o root -g root -m 700 /etc/nexo
install -o root -g root -m 755 nexo-remote-agent /usr/local/bin/nexo-remote-agent
install -o root -g root -m 600 agent.yaml /etc/nexo/agent.yaml
install -o root -g root -m 644 /dev/stdin /etc/systemd/system/nexo-remote-agent.service <<'UNIT'
[Unit]
Description=Nexo Remote Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/nexo-remote-agent -config /etc/nexo/agent.yaml
Restart=on-failure
User=root

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now nexo-remote-agent.service
"""


_WINDOWS_INSTALLER = rb"""$ErrorActionPreference = "Stop"
$InstallDir = "C:\Program Files\Nexo"
$ServiceName = "NexoRemoteAgent"
$Nssm = (Get-Command nssm.exe -ErrorAction Stop).Source

function Assert-NativeSuccess {
    param([string]$Operation)
    if ($LASTEXITCODE -ne 0) {
        throw "$Operation failed with exit code $LASTEXITCODE"
    }
}

$ExistingService = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($null -ne $ExistingService) {
    if ($ExistingService.Status -ne 'Stopped') {
        & $Nssm stop $ServiceName | Out-Null
        Assert-NativeSuccess "Stopping $ServiceName"
        $ExistingService.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(30))
    }
    & $Nssm remove $ServiceName confirm | Out-Null
    Assert-NativeSuccess "Removing $ServiceName"
}

New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
Copy-Item -LiteralPath ".\nexo-remote-agent.exe" -Destination "$InstallDir\nexo-remote-agent.exe" -Force
Copy-Item -LiteralPath ".\agent.yaml" -Destination "$InstallDir\agent.yaml" -Force
& icacls.exe "$InstallDir\agent.yaml" /inheritance:r /grant:r "*S-1-5-18:F" "*S-1-5-32-544:F"
Assert-NativeSuccess "Protecting agent.yaml"
& $Nssm install $ServiceName "$InstallDir\nexo-remote-agent.exe"
Assert-NativeSuccess "Installing $ServiceName"
& $Nssm set $ServiceName AppParameters "-config `"$InstallDir\agent.yaml`""
Assert-NativeSuccess "Configuring $ServiceName arguments"
& $Nssm set $ServiceName Start SERVICE_AUTO_START
Assert-NativeSuccess "Configuring $ServiceName startup"
& $Nssm start $ServiceName
Assert-NativeSuccess "Starting $ServiceName"
"""


_README = b"""Nexo Remote Agent workstation package

This archive contains a one-time workstation credential. Keep it private.
Run install.sh as root on Linux or install.ps1 in an elevated PowerShell on Windows.
Generate a new package if this download is interrupted or misplaced.
"""


def materialize_package(
    workstation: Workstation,
    build: NexoAgentBuild,
    raw_token: str,
    destination: Path,
) -> PackageMetadata:
    """Validate a build and create a fixed-content ZIP without mutating storage state."""
    if workstation.os_kind not in {"linux", "windows"}:
        raise NexoPackageError("Workstation platform is invalid")
    if workstation.os_kind != build.os_kind:
        raise NexoPackageError("Nexo build does not match workstation platform")
    if not raw_token.startswith("nxw_") or len(raw_token) < 20:
        raise NexoPackageError("Workstation device token is invalid")

    binary = _validated_artifact(build)
    config = _agent_config(workstation.os_kind, raw_token)
    generated_at = datetime.now(timezone.utc)
    filename = (
        f"nexo-agent-{str(workstation.id)[:8]}-{workstation.os_kind}-"
        f"{build.git_sha[:8]}.zip"
    )
    destination = Path(destination)
    package_path = destination if destination.suffix == ".zip" else destination / filename
    package_path.parent.mkdir(parents=True, exist_ok=True)

    binary_name = (
        "nexo-remote-agent.exe"
        if workstation.os_kind == "windows"
        else "nexo-remote-agent"
    )
    script_name = "install.ps1" if workstation.os_kind == "windows" else "install.sh"
    script = _WINDOWS_INSTALLER if workstation.os_kind == "windows" else _LINUX_INSTALLER
    manifest = {
        "workstation_id": str(workstation.id),
        "os_kind": workstation.os_kind,
        "agent_version": build.agent_version,
        "git_sha": build.git_sha,
        "binary_sha256": build.sha256,
        "generated_at": generated_at.isoformat(),
        "config_schema_version": 1,
    }

    try:
        with ZipFile(package_path, "w") as archive:
            _write_entry(archive, binary_name, binary, 0o755)
            _write_entry(
                archive,
                "agent.yaml",
                yaml.safe_dump(config, sort_keys=False).encode("utf-8"),
                0o600,
            )
            _write_entry(archive, script_name, script, 0o755)
            _write_entry(
                archive,
                "manifest.json",
                (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode(),
                0o644,
            )
            _write_entry(archive, "README.txt", _README, 0o644)
        package_sha256, package_size = _sha256_and_size(package_path)
    except (OSError, ValueError) as exc:
        raise NexoPackageError("Nexo package could not be materialized") from exc

    return PackageMetadata(
        path=package_path,
        filename=filename,
        size=package_size,
        sha256=package_sha256,
        generated_at=generated_at,
    )

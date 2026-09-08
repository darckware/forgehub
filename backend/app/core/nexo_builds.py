"""Verified client for the host bridge's fixed Nexo build operations."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.api.schemas.nexo_installation import NexoSource
from app.core.config import settings


BUILD_TIMEOUT_SECONDS = 630.0
MAX_FAILURE_DETAIL = 2_000


class NexoBuildBridgeError(RuntimeError):
    """A bridge/storage failure with a safe HTTP projection."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail[:MAX_FAILURE_DETAIL])
        self.status_code = status_code
        self.detail = detail[:MAX_FAILURE_DETAIL]


class VerifiedNexoBuild(BaseModel):
    git_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    agent_version: str = Field(min_length=1, max_length=50)
    os_kind: Literal["linux", "windows"]
    artifact_path: str = Field(min_length=1, max_length=500)
    artifact_size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    log_excerpt: str = Field(max_length=MAX_FAILURE_DETAIL)


async def _bridge_request(method: str, path: str, *, timeout: float) -> dict:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method,
                f"{settings.CHAT_BRIDGE_URL.rstrip('/')}{path}",
                headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
            )
    except httpx.TimeoutException as exc:
        raise NexoBuildBridgeError(504, "Nexo build bridge timed out") from exc
    except httpx.RequestError as exc:
        raise NexoBuildBridgeError(502, "Nexo build bridge is unavailable") from exc

    if response.status_code != 200:
        raise NexoBuildBridgeError(
            502,
            f"Nexo build bridge returned HTTP {response.status_code}",
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise NexoBuildBridgeError(
            502, "Nexo build bridge returned invalid JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise NexoBuildBridgeError(
            502, "Nexo build bridge returned an invalid response"
        )
    return payload


async def inspect_nexo_source() -> NexoSource:
    payload = await _bridge_request("GET", "/v1/nexo/source", timeout=30.0)
    try:
        return NexoSource.model_validate(payload)
    except ValidationError as exc:
        raise NexoBuildBridgeError(
            502, "Nexo build bridge returned invalid source metadata"
        ) from exc


def resolve_artifact_path(artifact_key: str) -> tuple[Path, str]:
    """Resolve a bridge key beneath the backend mount and return its canonical key."""
    relative_path = Path(artifact_key)
    if relative_path.is_absolute():
        raise NexoBuildBridgeError(
            502, "Nexo build bridge returned an invalid artifact key"
        )
    artifact_root = settings.NEXO_ARTIFACT_ROOT.resolve()
    artifact_path = (artifact_root / relative_path).resolve()
    try:
        canonical_key = artifact_path.relative_to(artifact_root).as_posix()
    except ValueError as exc:
        raise NexoBuildBridgeError(
            502, "Nexo build bridge returned an invalid artifact key"
        ) from exc
    if not artifact_path.is_file():
        raise NexoBuildBridgeError(502, "Nexo build artifact is missing")
    return artifact_path, canonical_key


def _sha256_and_size(artifact_path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    try:
        with artifact_path.open("rb") as artifact:
            for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
                digest.update(chunk)
                size += len(chunk)
    except OSError as exc:
        raise NexoBuildBridgeError(
            502, "Nexo build artifact could not be read"
        ) from exc
    return digest.hexdigest(), size


async def build_platform(os_kind: Literal["linux", "windows"]) -> VerifiedNexoBuild:
    payload = await _bridge_request(
        "POST",
        f"/v1/nexo/build/{os_kind}",
        timeout=BUILD_TIMEOUT_SECONDS,
    )
    try:
        build = VerifiedNexoBuild.model_validate(payload)
    except ValidationError as exc:
        raise NexoBuildBridgeError(
            502, "Nexo build bridge returned invalid build metadata"
        ) from exc
    if build.os_kind != os_kind:
        raise NexoBuildBridgeError(502, "Nexo build bridge returned the wrong platform")

    artifact_path, canonical_key = resolve_artifact_path(build.artifact_path)
    sha256, artifact_size = await asyncio.to_thread(_sha256_and_size, artifact_path)
    if artifact_size != build.artifact_size or sha256 != build.sha256:
        raise NexoBuildBridgeError(
            502, "Nexo build artifact failed integrity verification"
        )
    return build.model_copy(update={"artifact_path": canonical_key})

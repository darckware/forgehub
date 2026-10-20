"""Agent-avatar validation contract."""

import base64

import pytest
from pydantic import ValidationError

from app.api.schemas.agent import AgentUpdate


def _data_url(mime: str, payload: bytes) -> str:
    return f"data:{mime};base64,{base64.b64encode(payload).decode('ascii')}"


def test_agent_avatar_accepts_supported_image_signature() -> None:
    avatar = _data_url("image/png", b"\x89PNG\r\n\x1a\nsmall-image")

    update = AgentUpdate(avatar_data_url=avatar)

    assert update.avatar_data_url == avatar


def test_agent_avatar_null_clears_existing_photo() -> None:
    assert AgentUpdate(avatar_data_url=None).avatar_data_url is None


@pytest.mark.parametrize(
    ("mime", "payload"),
    [
        ("image/gif", b"GIF89a"),
        ("image/png", b"not-a-png"),
        ("image/jpeg", b"not-a-jpeg"),
        ("image/webp", b"not-a-webp"),
    ],
)
def test_agent_avatar_rejects_unsupported_or_mismatched_image(
    mime: str, payload: bytes,
) -> None:
    with pytest.raises(ValidationError):
        AgentUpdate(avatar_data_url=_data_url(mime, payload))


def test_agent_avatar_rejects_malformed_base64() -> None:
    with pytest.raises(ValidationError):
        AgentUpdate(avatar_data_url="data:image/png;base64,%%%")


def test_agent_avatar_rejects_more_than_512_kib_decoded() -> None:
    oversized_png = b"\x89PNG\r\n\x1a\n" + b"x" * (512 * 1024)

    with pytest.raises(ValidationError):
        AgentUpdate(avatar_data_url=_data_url("image/png", oversized_png))

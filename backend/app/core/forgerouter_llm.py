"""One chat completion through ForgeRouter, billed to a given agent's own key.

Shared by ForgeHub's small LLM utilities that must not be Hermes turns (no tools, no memory side
effects, seconds instead of a full agent run): client-demand translation (core/translation.py) and
the Maia's per-message context pass (core/personal_context.py). The key is read from ForgeRouter's
own registry first -- ForgeRouter issued it and is what validates it, while ForgeHub's encrypted copy
can lag behind a rotation (2026-10-14) -- and the copy is only the fallback when the registry can't
be read.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import forgerouter_sync
from app.core.config import settings
from app.core.secrets import decrypt_secret
from app.db.models.agent import Agent

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(120.0, connect=5.0)

#: Swapped by tests for an `httpx.MockTransport`.
transport: httpx.AsyncBaseTransport | None = None


class LlmError(Exception):
    """`kind` is "not_configured" (no key for the agent) or "failed" (ForgeRouter/reply problem)."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


async def agent_api_key(db: AsyncSession, slug: str) -> str:
    agent = (await db.execute(select(Agent).where(Agent.profile_slug == slug))).scalars().first()
    if agent is not None:
        try:
            keys = {k.name.strip().lower(): k.api_key for k in await forgerouter_sync.read_forgerouter_agent_keys()}
        except Exception:  # registry unreachable: fall back to the copy
            logger.warning("ForgeRouter registry unreachable; using ForgeHub's copy of %s's key", agent.name)
            keys = {}
        live = keys.get(agent.name.strip().lower())
        if live:
            return live
        if agent.forgerouter_api_key_encrypted:
            return decrypt_secret(agent.forgerouter_api_key_encrypted)
    raise LlmError("not_configured", f"No ForgeRouter key for agent '{slug}'.")


async def chat(db: AsyncSession, slug: str, model: str, messages: list[dict[str, Any]], temperature: float = 0) -> str:
    """The assistant's text reply. Raises LlmError."""
    api_key = await agent_api_key(db, slug)
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, transport=transport) as client:
            resp = await client.post(
                f"{settings.FORGEROUTER_URL.rstrip('/')}/v1/chat/completions",
                json={"model": model, "messages": messages, "temperature": temperature},
                headers={"Authorization": f"Bearer {api_key}"},
            )
    except httpx.HTTPError as exc:
        raise LlmError("failed", f"ForgeRouter unreachable: {exc.__class__.__name__}") from exc
    if resp.status_code >= 400:
        raise LlmError("failed", f"ForgeRouter error {resp.status_code}: {resp.text[:300]}")
    try:
        return resp.json()["choices"][0]["message"]["content"] or ""
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise LlmError("failed", "Unexpected ForgeRouter response") from exc

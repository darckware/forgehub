"""Translate a few texts into the reader's language through ForgeRouter.

Backs "Traduzir" on the client demands screen (2026-10-14): e-mails reach
Darckware in whatever language the sender wrote. One OpenAI-compatible
chat completion against ForgeRouter, billed to the agent named by
`settings.CLIENT_OPS_TRANSLATOR_AGENT` (its imported ForgeRouter key) --
deliberately not a Hermes turn through the bridge: a translation needs no
tools, should take seconds rather than a full agent turn, and must not end
up in the agent's memory. Nothing is stored; the screen keeps the result.
"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.secrets import decrypt_secret
from app.db.models.agent import Agent

_TIMEOUT = httpx.Timeout(120.0, connect=5.0)

#: i18next code -> language name the model is told to write in.
LANGUAGE_NAMES = {
    "pt": "Brazilian Portuguese",
    "pt-br": "Brazilian Portuguese",
    "en": "English",
    "es": "Spanish",
}

#: Swapped by tests for an `httpx.MockTransport`.
transport: httpx.AsyncBaseTransport | None = None


def _error(status_code: int, code: str, message: str) -> HTTPException:
    # Same detail shape as darckware_client.client_ops_error, so the Clients
    # screens translate it from `clientOps.errors.<code>`.
    return HTTPException(status_code=status_code, detail={"code": code, "message": message, "params": {}})


def language_name(code: str) -> str:
    return LANGUAGE_NAMES.get(code.lower()) or LANGUAGE_NAMES.get(code.split("-")[0].lower()) or code


async def _api_key(db: AsyncSession) -> str:
    slug = settings.CLIENT_OPS_TRANSLATOR_AGENT
    agent = (await db.execute(select(Agent).where(Agent.profile_slug == slug))).scalars().first()
    if agent is None or not agent.forgerouter_api_key_encrypted:
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "translator_not_configured",
            f"Translation needs a ForgeRouter key on agent '{slug}'.",
        )
    return decrypt_secret(agent.forgerouter_api_key_encrypted)


def _parse(reply: str, expected: int) -> list[str]:
    """The model answers a JSON array; tolerate a ```json fence around it."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", reply.strip())
    try:
        data: Any = json.loads(cleaned)
    except ValueError as exc:
        raise _error(status.HTTP_502_BAD_GATEWAY, "translation_failed", "Unreadable translation reply") from exc
    if not isinstance(data, list) or len(data) != expected or not all(isinstance(s, str) for s in data):
        raise _error(status.HTTP_502_BAD_GATEWAY, "translation_failed", "Translation reply has the wrong shape")
    return data


async def translate_texts(db: AsyncSession, texts: list[str], target_language: str) -> list[str]:
    """Translate each text into `target_language`, same order and count.
    Empty texts come back empty without a model call."""
    if not any(t.strip() for t in texts):
        return list(texts)
    api_key = await _api_key(db)
    language = language_name(target_language)
    system = (
        f"You translate texts into {language}. You receive a JSON array of strings and answer "
        "ONLY with a JSON array of the same length, each item the translation of the item at the "
        "same position. Keep line breaks, names, e-mail addresses, URLs, numbers and code as they "
        "are. A text already in the target language is returned unchanged. Do not add notes."
    )
    body = {
        "model": settings.CLIENT_OPS_TRANSLATOR_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(texts, ensure_ascii=False)},
        ],
        "temperature": 0,
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, transport=transport) as client:
            resp = await client.post(
                f"{settings.FORGEROUTER_URL.rstrip('/')}/v1/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {api_key}"},
            )
    except httpx.HTTPError as exc:
        raise _error(status.HTTP_502_BAD_GATEWAY, "translation_failed", f"ForgeRouter unreachable: {exc.__class__.__name__}") from exc
    if resp.status_code >= 400:
        raise _error(status.HTTP_502_BAD_GATEWAY, "translation_failed", f"ForgeRouter error {resp.status_code}: {resp.text[:300]}")
    try:
        reply = resp.json()["choices"][0]["message"]["content"] or ""
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise _error(status.HTTP_502_BAD_GATEWAY, "translation_failed", "Unexpected ForgeRouter response") from exc
    return _parse(reply, len(texts))

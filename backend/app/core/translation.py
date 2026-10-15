"""Translate a few texts into the reader's language through ForgeRouter.

Backs "Traduzir" on the client demands screen (2026-10-14): e-mails reach
Darckware in whatever language the sender wrote. One OpenAI-compatible
chat completion (core/forgerouter_llm.py), billed to the agent named by
`settings.CLIENT_OPS_TRANSLATOR_AGENT` -- deliberately not a Hermes turn
through the bridge: a translation needs no tools, should take seconds rather
than a full agent turn, and must not end up in the agent's memory. Nothing is
stored; the screen keeps the result.
"""
from __future__ import annotations

import json
import re
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import forgerouter_llm
from app.core.config import settings

#: i18next code -> language name the model is told to write in.
LANGUAGE_NAMES = {
    "pt": "Brazilian Portuguese",
    "pt-br": "Brazilian Portuguese",
    "en": "English",
    "es": "Spanish",
}


def _error(status_code: int, code: str, message: str) -> HTTPException:
    # Same detail shape as darckware_client.client_ops_error, so the Clients
    # screens translate it from `clientOps.errors.<code>`.
    return HTTPException(status_code=status_code, detail={"code": code, "message": message, "params": {}})


def language_name(code: str) -> str:
    return LANGUAGE_NAMES.get(code.lower()) or LANGUAGE_NAMES.get(code.split("-")[0].lower()) or code


def parse_json_reply(reply: str) -> Any:
    """The model answers JSON; tolerate a ```json fence around it. Raises ValueError."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", reply.strip())
    return json.loads(cleaned)


def _parse(reply: str, expected: int) -> list[str]:
    try:
        data: Any = parse_json_reply(reply)
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
    language = language_name(target_language)
    system = (
        f"You translate texts into {language}. You receive a JSON array of strings and answer "
        "ONLY with a JSON array of the same length, each item the translation of the item at the "
        "same position. Keep line breaks, names, e-mail addresses, URLs, numbers and code as they "
        "are. A text already in the target language is returned unchanged. Do not add notes."
    )
    try:
        reply = await forgerouter_llm.chat(
            db,
            settings.CLIENT_OPS_TRANSLATOR_AGENT,
            settings.CLIENT_OPS_TRANSLATOR_MODEL,
            [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(texts, ensure_ascii=False)},
            ],
        )
    except forgerouter_llm.LlmError as exc:
        if exc.kind == "not_configured":
            raise _error(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "translator_not_configured",
                f"Translation needs a ForgeRouter key on agent '{settings.CLIENT_OPS_TRANSLATOR_AGENT}'.",
            ) from exc
        raise _error(status.HTTP_502_BAD_GATEWAY, "translation_failed", str(exc)) from exc
    return _parse(reply, len(texts))

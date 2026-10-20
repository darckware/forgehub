"""Google reCAPTCHA v2 server-side verification for the login screen.

Same convention as darckware's app/core/recaptcha.py: fail-open when no
secret key is configured (dev/local, or before the key pair is provisioned
in the Google reCAPTCHA admin console for forgehub.darckware.net), so login
never breaks by omission -- once RECAPTCHA_SECRET_KEY is set, a missing or
invalid token is rejected.
"""
from __future__ import annotations

import httpx

from app.core.config import settings


async def verify_recaptcha(token: str | None) -> bool:
    secret = settings.RECAPTCHA_SECRET_KEY.strip() if settings.RECAPTCHA_SECRET_KEY else ""
    if not secret:
        return True

    if not token:
        return False

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                "https://www.google.com/recaptcha/api/siteverify",
                data={"secret": secret, "response": token},
            )
            if resp.status_code == 200:
                return bool(resp.json().get("success", False))
            return False
    except Exception:
        return False

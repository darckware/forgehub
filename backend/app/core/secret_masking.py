"""Masks secrets in commands and command output before they are stored or
shown (Remote Access phase 4). Two layers:

* `known`: exact values the caller knows are secret (a password it just
  generated, a token it injected) -- always masked, wherever they appear.
* patterns for what a person typing a command tends to put in it: private-key
  blocks, `password=...`/`token: ...`, `ConvertTo-SecureString '...'`,
  `net user <name> <password>`, `Bearer ...`.

Masking is best-effort for the patterns and exact for `known`; the rule that
keeps secrets out for real is that ForgeHub-generated secrets always travel
in `known`.
"""
import re

MASK = "********"

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), MASK),
    (
        re.compile(
            r"(?i)\b((?:password|passwd|pwd|passphrase|secret|token|api[_-]?key)\w*\s*[=:]\s*)"
            r"(\"[^\"]*\"|'[^']*'|[^\s;&|]+)"
        ),
        r"\1" + MASK,
    ),
    (re.compile(r"(?i)(ConvertTo-SecureString\s+(?:-String\s+)?)(\"[^\"]*\"|'[^']*'|\S+)"), r"\1" + MASK),
    (re.compile(r"(?i)\b(net\s+user\s+\S+\s+)(?!/)(\S+)"), r"\1" + MASK),
    (re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]{8,}"), r"\1" + MASK),
]


def mask_secrets(text: str | None, known: list[str] | tuple[str, ...] = ()) -> str | None:
    if not text:
        return text
    # Longest first, so a secret that contains another is masked whole.
    for value in sorted({k for k in known if k and len(k) >= 4}, key=len, reverse=True):
        text = text.replace(value, MASK)
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text

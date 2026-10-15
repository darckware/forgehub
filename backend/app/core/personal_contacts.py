"""Rules of the personal contacts domain, shared by the routes, the importer and the tests.

Ported from the Maia's file-based module (``app/mcp/personal_contacts.py`` before 2026-10-14) so the
behavior the Maia and Marcelo already rely on carries over unchanged: how a phone is normalized, how a
spoken category ("Trabalho (SEMED)") becomes a key, the birthday format, and how the old
``contatos/<telefone>.md`` fichas are read (for the one-off import).
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")

_CATEGORY_ALIASES = {
    "família": "familia", "esposa": "familia", "filha": "familia", "filho": "familia",
    "parente": "parentes", "amigo": "amigos", "amiga": "amigos", "amizade": "amigos",
    "trabalho": "trabalho_semed", "semed": "trabalho_semed", "trabalho semed": "trabalho_semed",
    "trabalho (semed)": "trabalho_semed", "cliente": "cliente_darckware", "darckware": "cliente_darckware",
    "cliente darckware": "cliente_darckware", "outro": "outros", "a classificar": "a_classificar",
}

BIRTHDAY_RE = re.compile(r"\d{2}/\d{2}(/\d{4})?")
_PLACEHOLDER = "(a preencher"


class ContactRuleError(ValueError):
    """A rule violation whose message is safe to show to Marcelo or the Maia."""


def digits(value: str | None) -> str:
    return re.sub(r"\D", "", str(value or ""))


def normalize_phone(value: str | None) -> str:
    """Digits with the country code: a Brazilian number typed without 55 gets it. A value starting
    with "+" already carries its country code (the WhatsApp plugin sends the JID's number that way),
    so a foreign number of 11 digits, like a US one, is never mistaken for a Brazilian one."""
    d = digits(value)
    if len(d) in (10, 11) and not str(value or "").strip().startswith("+"):  # DDD + number, without 55
        d = "55" + d
    return d


def require_phone(value: str | None) -> str:
    phone = normalize_phone(value)
    if not 11 <= len(phone) <= 15:
        raise ContactRuleError("Telefone inválido: informe com DDD (ex.: +55 21 99999-9999).")
    return phone


def format_phone(value: str | None) -> str:
    d = normalize_phone(value)
    if len(d) == 13 and d.startswith("55"):
        return f"+55 {d[2:4]} {d[4:9]}-{d[9:]}"
    if len(d) == 12 and d.startswith("55"):
        return f"+55 {d[2:4]} {d[4:8]}-{d[8:]}"
    return f"+{d}" if d else ""


def normalize_category(value: str | None) -> str | None:
    """Accepts the label as Marcelo says it ("Trabalho (SEMED)", "Família") and returns the key."""
    if value is None:
        return None
    v = str(value).strip().lower()
    if v in _CATEGORY_ALIASES:
        return _CATEGORY_ALIASES[v]
    v = unicodedata.normalize("NFKD", v)
    v = "".join(c for c in v if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", v).strip("_")


def check_birthday(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if value and not BIRTHDAY_RE.fullmatch(value):
        raise ContactRuleError("Aniversário no formato dd/mm ou dd/mm/aaaa.")
    return value


def merge_other_data(current: dict[str, Any], changes: dict[str, Any] | None) -> dict[str, Any]:
    """Same rule as the old "Outros dados" section: an empty value removes the field."""
    merged = dict(current or {})
    for key, value in (changes or {}).items():
        key = str(key).strip().replace("*", "").replace(":", "")
        if not key:
            continue
        if value is not None and (not isinstance(value, str) or value.strip()):
            merged[key] = value.strip().replace("\n", " ") if isinstance(value, str) else value
        else:
            merged.pop(key, None)
    return merged


def split_blacklist_marker(changes: dict[str, Any] | None) -> tuple[dict[str, Any] | None, bool | None]:
    """The file-era way to block someone was ``outros_dados={"tipo": "blacklist"}`` (and the Maia's skill
    still says so). Keep honoring it: that key becomes the ``blocked`` flag instead of a dead note.
    Returns (other_data without the marker, blocked or None when the marker wasn't there)."""
    if not changes or "tipo" not in changes:
        return changes, None
    value = changes.get("tipo")
    if not isinstance(value, str) or value.strip().lower() != "blacklist":
        return changes, None
    rest = {k: v for k, v in changes.items() if k != "tipo"}
    return rest, True


def upcoming_birthday(birthday: str, today: date, days: int) -> dict[str, Any] | None:
    m = re.fullmatch(r"(\d{2})/(\d{2})(?:/(\d{4}))?", (birthday or "").strip())
    if not m:
        return None
    day, month, year = int(m.group(1)), int(m.group(2)), m.group(3)
    try:
        when = date(today.year, month, day)
        if when < today:
            when = date(today.year + 1, month, day)
    except ValueError:  # 29/02 in a non-leap year
        return None
    left = (when - today).days
    if left > days:
        return None
    return {"data": when.strftime("%d/%m/%Y"), "faltam_dias": left, "idade": (when.year - int(year)) if year else None}


# ---------------------------------------------------------------------------
# Reading the old knowledge-base files (one-off import, 2026-10-14)
# ---------------------------------------------------------------------------

_TABLE_KEYS = ("nome", "telefone", "categoria", "relacao", "aniversario", "observacoes", "ultimo_contato")
_HISTORY_RE = re.compile(r"^- \*\*(\d{2}/\d{2}/\d{4} \d{2}:\d{2})\*\* · (.+?):(?: (.*))?$")
#: A history line with nothing after the author (a sticker, photo or audio the old plugin saw as empty).
EMPTY_MESSAGE = "(mensagem sem texto)"


@dataclass
class LegacyMessage:
    at: datetime
    author: str
    direction: str
    text: str


@dataclass
class LegacyContact:
    phone: str
    name: str = ""
    category: str = "a_classificar"
    relation: str = ""
    birthday: str = ""
    observations: str = ""
    who_is: str = ""
    how_to_treat: str = ""
    other_data: dict[str, Any] = field(default_factory=dict)
    blocked: bool = False
    last_contact_at: datetime | None = None
    messages: list[LegacyMessage] = field(default_factory=list)


def parse_local_datetime(value: str) -> datetime | None:
    try:
        return datetime.strptime(value.strip(), "%d/%m/%Y %H:%M").replace(tzinfo=TZ)
    except ValueError:
        return None


def parse_table(text: str) -> list[dict[str, str]]:
    rows = []
    for line in text.splitlines():
        if not line.startswith("| ") or line.startswith("| Nome |") or line.startswith("|---"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(dict(zip(_TABLE_KEYS, (cells + [""] * len(_TABLE_KEYS))[: len(_TABLE_KEYS)])))
    return rows


def _section(text: str, title: str) -> str:
    m = re.search(rf"^## {re.escape(title)}\s*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    value = m.group(1).strip() if m else ""
    return "" if value.startswith(_PLACEHOLDER) or value == "(nenhum)" else value


def _frontmatter(text: str) -> dict[str, str]:
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    data = {}
    for line in (m.group(1).splitlines() if m else []):
        if ":" in line:
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip().strip('"')
    return data


def _extras(text: str) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for line in _section(text, "Outros dados").splitlines():
        m = re.match(r"^- \*\*(.+?):\*\*\s*(.*)$", line.strip())
        if not m:
            continue
        value: Any = m.group(2).strip()
        if value.startswith("@json:"):
            try:
                value = json.loads(value[6:])
            except ValueError:
                pass
        elif value.startswith("@str:"):
            value = value[5:]
        fields[m.group(1).strip()] = value
    return fields


def parse_ficha(text: str) -> LegacyContact:
    front = _frontmatter(text)
    extras = _extras(text)
    blocked = str(extras.get("tipo", "")).strip().lower() == "blacklist"
    if blocked:
        extras.pop("tipo", None)
    contact = LegacyContact(
        phone=normalize_phone(front.get("telefone", "")),
        name=front.get("nome", ""),
        category=front.get("categoria", "") or "a_classificar",
        relation=front.get("relacao", ""),
        birthday=front.get("aniversario", ""),
        who_is=_section(text, "Quem é"),
        how_to_treat=_section(text, "Como tratar"),
        other_data=extras,
        blocked=blocked,
    )
    for line in _section(text, "Histórico").splitlines():
        m = _HISTORY_RE.match(line.strip())
        if not m:
            continue
        at = parse_local_datetime(m.group(1))
        if at is None:
            continue
        author = m.group(2).strip()
        direction = "out" if author in ("Marcelo", "Maia") else "in"
        text = (m.group(3) or "").strip() or EMPTY_MESSAGE
        contact.messages.append(LegacyMessage(at=at, author=author, direction=direction, text=text))
    return contact

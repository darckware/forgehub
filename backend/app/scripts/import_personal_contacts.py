"""One-off import of the Maia's file-based contacts into the database (2026-10-14).

Reads what ``knowledge_base/marcelo/pessoal`` held until this date -- ``CONTATOS.md`` (the table),
``contatos/<telefone>.md`` (the fichas with "Quem é", "Como tratar", "Outros dados" and "Histórico")
and ``CATEGORIAS.json`` -- plus the Maia's service rules (``whatsapp/INSTRUCOES_PESSOAIS.md`` and
``atendimento.json``). A contact listed in only one of the table or the fichas is still imported.

Safe to re-run: a phone already in the database is skipped (``--update`` refreshes its record fields
instead, never its history). Imported history lines are marked ``context_status="skipped"`` so the
context pass does not spend a model call on every old message.

    python -m app.scripts.import_personal_contacts [--dry-run] [--update]
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from app.core import personal_contacts as rules
from app.db.base import AsyncSessionLocal
from app.db.models.personal import (
    PersonalAssistantSettings,
    PersonalContact,
    PersonalContactCategory,
    PersonalContactMessage,
)

DEFAULT_BASE = Path("/root/memory/knowledge_base/marcelo/pessoal")
DEFAULT_WHATSAPP = Path("/root/.hermes/profiles/maia/whatsapp")


def load_legacy(base: Path) -> dict[str, rules.LegacyContact]:
    contacts: dict[str, rules.LegacyContact] = {}
    for path in sorted((base / "contatos").glob("*.md")):
        contact = rules.parse_ficha(path.read_text(encoding="utf-8"))
        if not contact.phone:
            contact.phone = rules.normalize_phone(path.stem)
        if contact.phone:
            contacts[contact.phone] = contact
    table = base / "CONTATOS.md"
    for row in rules.parse_table(table.read_text(encoding="utf-8")) if table.exists() else []:
        phone = rules.normalize_phone(row["telefone"])
        if not phone:
            continue
        contact = contacts.setdefault(phone, rules.LegacyContact(phone=phone))
        # The table is what Marcelo edited by hand; it wins over the ficha's frontmatter.
        contact.name = row["nome"] or contact.name
        contact.category = row["categoria"] or contact.category
        contact.relation = row["relacao"] or contact.relation
        contact.birthday = row["aniversario"] or contact.birthday
        contact.observations = row["observacoes"] or contact.observations
        contact.last_contact_at = rules.parse_local_datetime(row["ultimo_contato"]) or contact.last_contact_at
    for contact in contacts.values():
        if contact.messages and contact.last_contact_at is None:
            contact.last_contact_at = max(m.at for m in contact.messages)
        if contact.birthday and not rules.BIRTHDAY_RE.fullmatch(contact.birthday):
            contact.birthday = ""
    return contacts


async def run(base: Path, whatsapp: Path, dry_run: bool, update: bool) -> dict[str, int]:
    legacy = load_legacy(base)
    extra_categories = []
    categories_file = base / "CATEGORIAS.json"
    if categories_file.exists():
        extra_categories = [c for c in json.loads(categories_file.read_text(encoding="utf-8")) if isinstance(c, str)]

    stats = {"contacts_found": len(legacy), "created": 0, "updated": 0, "skipped": 0, "messages": 0, "categories": 0}
    async with AsyncSessionLocal() as db:
        known = set((await db.execute(select(PersonalContactCategory.key))).scalars())
        for key in [*extra_categories, *(c.category for c in legacy.values())]:
            key = rules.normalize_category(key) or ""
            if key and key not in known:
                known.add(key)
                stats["categories"] += 1
                db.add(PersonalContactCategory(key=key))

        existing = {c.phone: c for c in (await db.execute(select(PersonalContact))).scalars()}
        for phone, item in legacy.items():
            fields = {
                "name": item.name, "category": rules.normalize_category(item.category) or "a_classificar",
                "relation": item.relation, "birthday": item.birthday, "observations": item.observations,
                "who_is": item.who_is, "how_to_treat": item.how_to_treat, "other_data": item.other_data,
                "blocked": item.blocked,
            }
            if phone in existing:
                if update:
                    for key, value in fields.items():
                        setattr(existing[phone], key, value)
                    stats["updated"] += 1
                else:
                    stats["skipped"] += 1
                continue
            contact = PersonalContact(phone=phone, last_contact_at=item.last_contact_at, created_by="maia", **fields)
            db.add(contact)
            await db.flush()
            for m in item.messages:
                db.add(PersonalContactMessage(contact_id=contact.id, at=m.at, direction=m.direction, author=m.author,
                                              text=m.text, source="import", context_status="skipped"))
                stats["messages"] += 1
            stats["created"] += 1

        cfg = (await db.execute(select(PersonalAssistantSettings).limit(1))).scalars().first()
        if cfg is None:
            cfg = PersonalAssistantSettings()
            db.add(cfg)
        instructions = whatsapp / "INSTRUCOES_PESSOAIS.md"
        if instructions.exists() and not cfg.instructions.strip():
            cfg.instructions = instructions.read_text(encoding="utf-8").strip()
            stats["instructions"] = 1
        try:
            cfg.wait_minutes = int(json.loads((whatsapp / "atendimento.json").read_text())["espera_minutos"])
        except (OSError, ValueError, KeyError, TypeError):
            pass

        if dry_run:
            await db.rollback()
        else:
            await db.commit()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--whatsapp", type=Path, default=DEFAULT_WHATSAPP)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--update", action="store_true", help="refresh record fields of contacts already imported")
    args = parser.parse_args()
    stats = asyncio.run(run(args.base, args.whatsapp, args.dry_run, args.update))
    print(json.dumps({"dry_run": args.dry_run, **stats}, ensure_ascii=False))


if __name__ == "__main__":
    main()

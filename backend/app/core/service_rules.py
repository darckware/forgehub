"""Customer-service rules per agent and channel, mirrored into the agent's profile.

Marcelo, 2026-11-14: the rules of the agents that serve people outside the ecosystem (Lara: WhatsApp,
site, e-mail; Maia: WhatsApp) live in one standard-named file per channel, ``ATENDIMENTO_<CANAL>.md``,
a complement to the agent's main memory, registered and changed on ForgeHub's Pessoal screen and
monitored by the Auditor (ECO-070).

ForgeHub's ``agent_service_rules`` row is the source. A save writes the file first (atomically) and
commits afterwards, so an unwritable profile aborts the save instead of leaving the agent on old rules
while the screen shows new ones. The agent reads the file each turn (Lara through the shared
``service_rules`` hook; Maia through her WhatsApp plugin, which reads the same text via
``/personal/assistant-settings``).
"""
from __future__ import annotations

import hashlib
import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.governance import AuditEvent
from app.db.models.personal import AgentServiceRule

# Which agent serves which outside channel. A new pair is a code change on purpose: each one needs
# the agent side (hook or plugin) to read its file.
SERVICE_RULE_PAIRS: dict[str, tuple[str, ...]] = {
    "lara": ("whatsapp", "site", "email"),
    "maia": ("whatsapp",),
}
# Hermes spills a hook's context above 10,000 characters to a file and shows the agent only its head
# and tail (tools/hook_output_spill.py); the rules plus their header must stay under that.
SERVICE_RULE_MAX_CHARS = 9000
AUDIT_ENTITY = "agent_service_rule"
_NAMESPACE = uuid.UUID("6f1d8a2e-3c55-4b7e-9a0d-2b7f4e1c9a51")

# What the host calls the profiles directory the backend sees at settings.SERVICE_RULES_PROFILES_ROOT.
HOST_PROFILES_ROOT = "/root/.hermes/profiles"


class ServiceRuleError(ValueError):
    """Invalid pair or content (the route maps it to 404/422)."""


class ServiceRuleConflict(Exception):
    """The caller edited an older version than the one stored."""

    def __init__(self, current_hash: str | None):
        super().__init__("Service rules changed since they were loaded")
        self.current_hash = current_hash


class ServiceRuleFileError(Exception):
    """The profile file could not be written; nothing was saved."""


@dataclass(frozen=True)
class RuleFile:
    container_path: Path
    host_path: str
    name: str


def file_name(channel: str) -> str:
    return f"ATENDIMENTO_{channel.upper()}.md"


def check_pair(agent: str, channel: str) -> None:
    if channel not in SERVICE_RULE_PAIRS.get(agent, ()):
        raise ServiceRuleError(f"{agent}/{channel} is not a service-rule pair")


def rule_file(agent: str, channel: str) -> RuleFile:
    check_pair(agent, channel)
    name = file_name(channel)
    return RuleFile(Path(settings.SERVICE_RULES_PROFILES_ROOT) / agent / name, f"{HOST_PROFILES_ROOT}/{agent}/{name}", name)


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def entity_id(agent: str, channel: str) -> uuid.UUID:
    return uuid.uuid5(_NAMESPACE, f"{agent}:{channel}")


def normalize(content: str) -> str:
    text = (content or "").replace("\r\n", "\n").strip()
    if not text:
        raise ServiceRuleError("Service rules cannot be empty")
    if len(text) > SERVICE_RULE_MAX_CHARS:
        raise ServiceRuleError(f"Service rules exceed {SERVICE_RULE_MAX_CHARS} characters ({len(text)})")
    return text + "\n"


def file_state(agent: str, channel: str, row: AgentServiceRule | None) -> str:
    """in_sync | missing | differs | unknown (the profile isn't reachable from here)."""
    path = rule_file(agent, channel).container_path
    if not path.parent.is_dir():
        return "unknown"
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "unknown"
    if row is None:
        return "differs"
    return "in_sync" if content_hash(text) == row.content_hash else "differs"


def write_file(agent: str, channel: str, content: str) -> None:
    """Atomic replace (temp file + rename in the same directory), mode 0644."""
    path = rule_file(agent, channel).container_path
    if not path.parent.is_dir():
        raise ServiceRuleFileError(f"Profile directory {path.parent} not found")
    try:
        fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
            os.chmod(tmp, 0o644)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
    except OSError as exc:
        raise ServiceRuleFileError(f"Could not write {path}: {type(exc).__name__}") from exc


async def get_rule(db: AsyncSession, agent: str, channel: str, *, lock: bool = False) -> AgentServiceRule | None:
    query = select(AgentServiceRule).where(AgentServiceRule.agent_slug == agent, AgentServiceRule.channel == channel)
    if lock:
        query = query.with_for_update()
    return (await db.execute(query)).scalars().first()


async def list_rules(db: AsyncSession) -> list[tuple[str, str, AgentServiceRule | None]]:
    rows = {(r.agent_slug, r.channel): r for r in (await db.execute(select(AgentServiceRule))).scalars()}
    return [(agent, channel, rows.get((agent, channel)))
            for agent, channels in SERVICE_RULE_PAIRS.items() for channel in channels]


async def save_rule(db: AsyncSession, agent: str, channel: str, content: str, actor: str, *,
                    expected_hash: str | None = None, check_expected: bool = True) -> AgentServiceRule:
    """Validate, write the profile file, then stage the row and its audit event. Caller commits."""
    check_pair(agent, channel)
    text = normalize(content)
    row = await get_rule(db, agent, channel, lock=True)
    current = row.content_hash if row else None
    if check_expected and expected_hash != current:
        raise ServiceRuleConflict(current)
    new_hash = content_hash(text)
    write_file(agent, channel, text)
    if row is None:
        row = AgentServiceRule(agent_slug=agent, channel=channel, content=text, content_hash=new_hash, updated_by=actor)
        db.add(row)
    elif new_hash != current:
        row.content, row.content_hash, row.updated_by = text, new_hash, actor
    if new_hash != current:
        db.add(AuditEvent(entity_type=AUDIT_ENTITY, entity_id=entity_id(agent, channel), event_type="updated",
                          actor=actor, payload={"agent": agent, "channel": channel, "content_hash": new_hash,
                                                "previous_hash": current, "chars": len(text.strip())}))
    await db.flush()
    return row


async def history(db: AsyncSession, agent: str, channel: str, limit: int = 50) -> list[AuditEvent]:
    check_pair(agent, channel)
    query = (select(AuditEvent)
             .where(AuditEvent.entity_type == AUDIT_ENTITY, AuditEvent.entity_id == entity_id(agent, channel))
             .order_by(AuditEvent.created_at.desc()).limit(limit))
    return list((await db.execute(query)).scalars())

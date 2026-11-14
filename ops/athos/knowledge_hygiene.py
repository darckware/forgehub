"""Foundation integrity and agent-memory hygiene (Auditor ECO-067, ECO-068, ECO-069).

Marcelo, 2026-11-14: "o módulo auditor não está vendo isso que está errado no foundation, deixando
as regras desatualizado e obsoleto" and "preciso que monitore as memórias dos agentes com regras
desatualizadas, obsoletas, links desnecessário. Controle do tamanho das memória dos agentes hermes e
externos."

Read-only. Findings name a file, a line and the rule; they never quote memory content.

A retired term is allowed where the text itself says it is history: on the same paragraph, under a
heading, or in a file whose header marks it retired/historical. Dated records (`47_migrations/`)
keep the words of their time and are not checked.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

FOUNDATION = Path("/root/memory/foundation")
KNOWLEDGE_BASE = Path("/root/memory/knowledge_base")
PROFILES = Path("/root/.hermes/profiles")
HOME = Path("/root")

HISTORY_DIRS = {"47_migrations"}
FOUNDATION_ROOT_ENTRIES = {"09_MANIFEST.yaml", "10_README.md", "12_adapters", "14_agents", "22_continuity",
                           "30_docs", "36_governance", "43_map", "47_migrations", "52_policies", "65_templates", ".git"}
DOC_SUFFIXES = {".md", ".yaml", ".yml"}

# Retired path or term -> what replaced it. Keep in sync with the Foundation (FOUNDATION_STRUCTURE.md).
RETIRED_TERMS: dict[str, str] = {
    r"/root/\.hermes/foundation": "/root/memory/foundation",
    r"/root/\.hermes/knowledge_base": "/root/memory/knowledge_base",
    r"\bkanboard\b": "ForgeHub Tasks + Messages",
    r"\bopenclaw\b": "Vector, retired 2026-10-12",
    r"\bknowledge\.db\b": "the agent's knowledge base files",
    r"\bcompany_postgres\b": "one Postgres per application",
    r"\bfoundation_postgres\b": "one Postgres per application",
    r"\bsvc-agente\b": "each agent's own token",
    r"\bWSL\b": "the VPS",
}
_RETIRED = [(re.compile(term, re.I), term, repl) for term, repl in RETIRED_TERMS.items()]
HISTORY_WORDS = re.compile(
    r"retired|discontinued|descontinuad|removed|removid|aposentad|legacy|legado|archived|arquivad|no longer|"
    r"não existe|nao existe|never existed|gone\b|superseded|substitu|replaced|deprecated|obsolet|antig|"
    r"\bold\b|former|anterior|previous|history|histór|histor|was\b|were\b|used to|until\b|até\b|era\b|"
    r"migrat|migrad|instead of|em vez|não use|never use|do not use|never write|nunca|replac|must not|não deve|"
    r"not installed|não instalad|moved|movid|\*\*why:\*\*|does not use|não usa",
    re.I)
FILE_STATUS = re.compile(r"status[^\n]{0,30}(retired|historical|history|snapshot|superseded|archived|aposentad|histórico|not installed)|"
                         r"superseded[^\n]{0,40}do not follow|history only", re.I)
HEADING = re.compile(r"^\s{0,3}#{1,6}\s")
# A Foundation-relative path: NN_folder[/...]
FOUNDATION_REF = re.compile(r"(?:/root/memory/foundation/|(?<![\w/.-]))((?:0[0-9]|[1-6][0-9])_[A-Za-z][\w.-]*(?:/[\w.@-]+)*)")
# An absolute path under the ecosystem roots that a reader would follow.
ABS_REF = re.compile(r"(/root/(?:memory|\.hermes|project|\.claude|\.codex|\.gemini)/[\w./@-]+)")
PLACEHOLDER = re.compile(r"[<>{}*$\[\]]|\.\.\.|XXX|NNN|YYYY", re.I)

# Size limits. Hermes injects memories/MEMORY.md and memories/USER.md into every turn and refuses
# writes beyond the profile's own limits (config.yaml memory_char_limit/user_char_limit); the other
# files are loaded on every run of their runtime, so they stay small (bytes).
HERMES_DEFAULT_LIMITS = {"MEMORY.md": 2200, "USER.md": 1375}
PROFILE_FILE_LIMITS = {"SOUL.md": 24_000, "MEMORY.md": 4_000, "USER.md": 4_000}
INSTRUCTION_FILE_LIMIT = 8_000          # CLAUDE.md / AGENTS.md / GEMINI.md and agy's config/*.md
CLAUDE_INDEX_MAX_LINES = 200            # Claude Code loads only the first 200 lines of MEMORY.md
CLAUDE_MEMORY_DIR_LIMIT = 200_000
CODEX_MEMORY_DB_LIMIT = 5_000_000
KNOWLEDGE_BASE_AGENT_LIMIT = 50_000_000


@dataclass(frozen=True)
class MemoryFile:
    agent: str
    path: Path
    limit: int | None = None        # characters for Hermes memories, bytes otherwise
    unit: str = "bytes"
    max_lines: int | None = None
    text: bool = True               # checked for retired terms and dead links


def _lines_with_context(text: str):
    """Yield (line_number, line, allowed) — allowed when the paragraph, heading or file header is history."""
    lines = text.splitlines()
    header_history = any(FILE_STATUS.search(line) for line in lines[:12])
    heading_history = False
    paragraphs: list[list[int]] = []
    current: list[int] = []
    for i, line in enumerate(lines):
        if line.strip():
            current.append(i)
        elif current:
            paragraphs.append(current)
            current = []
    if current:
        paragraphs.append(current)
    paragraph_of = {i: tuple(p) for p in paragraphs for i in p}
    for i, line in enumerate(lines):
        if HEADING.match(line):
            heading_history = bool(HISTORY_WORDS.search(line))
        paragraph = paragraph_of.get(i, (i,))
        window = paragraph if len(paragraph) <= 12 else range(max(i - 2, 0), min(i + 3, len(lines)))
        allowed = header_history or heading_history or any(HISTORY_WORDS.search(lines[j]) for j in window)
        yield i + 1, line, allowed


def _display(term: str) -> str:
    return term.replace("\\b", "").replace("\\", "")


def _clean(target: str) -> str:
    return target.rstrip(".,:;)`'\"")


def retired_term_findings(path: Path, label: str) -> list[str]:
    try:
        text = path.read_text(errors="ignore")
    except OSError as exc:
        return [f"{label}: unreadable ({type(exc).__name__})"]
    found = []
    for n, line, allowed in _lines_with_context(text):
        if allowed:
            continue
        for pattern, term, repl in _RETIRED:
            if pattern.search(line):
                found.append(f"{label}:{n} uses retired '{_display(term)}' -> {repl}")
    return found


def dead_link_findings(path: Path, label: str, foundation: Path = FOUNDATION) -> list[str]:
    try:
        text = path.read_text(errors="ignore")
    except OSError:
        return []
    found = []
    for n, line, allowed in _lines_with_context(text):
        if allowed:
            continue
        targets = {_clean(m.group(1)) for m in FOUNDATION_REF.finditer(line)}
        for target in targets:
            if PLACEHOLDER.search(target):
                continue
            if not ((foundation / target).exists() or (path.parent / target).exists()):
                found.append(f"{label}:{n} links missing {target}")
        for m in ABS_REF.finditer(line):
            target = _clean(m.group(1))
            if PLACEHOLDER.search(target) or target.endswith("/") or line[m.end():m.end() + 1] in "*<{$":
                continue
            if not os.path.lexists(target):
                found.append(f"{label}:{n} links missing {target}")
    return found


# ---------------------------------------------------------------- Foundation (ECO-067)

def foundation_documents(foundation: Path = FOUNDATION):
    for path in sorted(foundation.rglob("*")):
        rel = path.relative_to(foundation)
        if path.is_file() and rel.parts[0] not in HISTORY_DIRS and ".git" not in rel.parts and path.suffix in DOC_SUFFIXES:
            yield path, str(rel)


def foundation_findings(foundation: Path = FOUNDATION) -> list[str]:
    findings = [f"unexpected top-level entry: {p.name}" for p in sorted(foundation.iterdir())
                if p.name not in FOUNDATION_ROOT_ENTRIES]
    manifest = foundation / "09_MANIFEST.yaml"
    if manifest.is_file():
        root = re.search(r"^canonical_root:\s*(\S+)", manifest.read_text(), re.M)
        if not root or root.group(1) != str(foundation):
            findings.append(f"09_MANIFEST.yaml canonical_root is {root.group(1) if root else 'missing'}, expected {foundation}")
    for path, label in foundation_documents(foundation):
        findings += retired_term_findings(path, label)
        findings += dead_link_findings(path, label, foundation)
    return findings


# ---------------------------------------------------------------- agent memories (ECO-068/069)

def _hermes_limits(profile: Path) -> dict[str, int]:
    limits = dict(HERMES_DEFAULT_LIMITS)
    try:
        config = (profile / "config.yaml").read_text()
    except OSError:
        return limits
    for key, name in (("memory_char_limit", "MEMORY.md"), ("user_char_limit", "USER.md")):
        m = re.search(rf"^\s+{key}:\s*(\d+)", config, re.M)
        if m:
            limits[name] = int(m.group(1))
    return limits


def memory_inventory(profiles: Path = PROFILES, home: Path = HOME) -> list[MemoryFile]:
    files: list[MemoryFile] = []
    if profiles.is_dir():
        for profile in sorted(p for p in profiles.iterdir() if p.is_dir() and not (p / "gateway.parked").exists()):
            if not (profile / "config.yaml").is_file():
                continue
            limits = _hermes_limits(profile)
            for name, limit in limits.items():
                files.append(MemoryFile(profile.name, profile / "memories" / name, limit, "chars"))
            for name, limit in PROFILE_FILE_LIMITS.items():
                files.append(MemoryFile(profile.name, profile / name, limit))
    claude = home / ".claude"
    files.append(MemoryFile("porthus", claude / "CLAUDE.md", INSTRUCTION_FILE_LIMIT))
    for memory_dir in sorted((claude / "projects").glob("*/memory")):
        files.append(MemoryFile("porthus", memory_dir / "MEMORY.md", max_lines=CLAUDE_INDEX_MAX_LINES))
        files.append(MemoryFile("porthus", memory_dir, CLAUDE_MEMORY_DIR_LIMIT, text=False))
        for note in sorted(memory_dir.glob("*.md")):
            if note.name != "MEMORY.md":
                files.append(MemoryFile("porthus", note))
    codex = home / ".codex"
    for name in ("AGENTS.md", "SOUL.md", "IDENTITY.md"):
        files.append(MemoryFile("aramis", codex / name, INSTRUCTION_FILE_LIMIT))
    files.append(MemoryFile("aramis", codex / "memories_1.sqlite", CODEX_MEMORY_DB_LIMIT, text=False))
    gemini = home / ".gemini"
    files.append(MemoryFile("dartan", gemini / "GEMINI.md", INSTRUCTION_FILE_LIMIT))
    for note in sorted((gemini / "config").glob("*.md")):
        files.append(MemoryFile("dartan", note, INSTRUCTION_FILE_LIMIT))
    return files


def _size(item: MemoryFile) -> int:
    if item.path.is_dir():
        return sum(p.stat().st_size for p in item.path.rglob("*") if p.is_file())
    if item.unit == "chars":
        return len(item.path.read_text(errors="ignore"))
    return item.path.stat().st_size


def memory_size_findings(inventory: list[MemoryFile], knowledge_base: Path = KNOWLEDGE_BASE) -> list[str]:
    findings = []
    for item in inventory:
        if not item.path.exists():
            continue
        if item.limit is not None:
            size = _size(item)
            if size > item.limit:
                findings.append(f"{item.agent}: {item.path} is {size} {item.unit} (limit {item.limit})")
        if item.max_lines is not None:
            lines = len(item.path.read_text(errors="ignore").splitlines())
            if lines > item.max_lines:
                findings.append(f"{item.agent}: {item.path} has {lines} lines (only the first {item.max_lines} are loaded)")
    if knowledge_base.is_dir():
        for agent in sorted(p for p in knowledge_base.iterdir() if p.is_dir()):
            size = sum(p.stat().st_size for p in agent.rglob("*") if p.is_file())
            if size > KNOWLEDGE_BASE_AGENT_LIMIT:
                findings.append(f"{agent.name}: knowledge base {agent} is {size} bytes (limit {KNOWLEDGE_BASE_AGENT_LIMIT})")
    return findings


def memory_currency_findings(inventory: list[MemoryFile], foundation: Path = FOUNDATION) -> list[str]:
    findings = []
    for item in inventory:
        if not item.text or not item.path.is_file():
            continue
        label = f"{item.agent}: {item.path}"
        findings += retired_term_findings(item.path, label)
        findings += dead_link_findings(item.path, label, foundation)
    return findings

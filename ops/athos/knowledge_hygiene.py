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
# Explicit history markers only, whole words. Checked on the line of the term and the lines right
# before and after it (wrapped sentences); a heading or the file header (first 12 lines) can also mark a whole section/file.
HISTORY_WORDS = re.compile(
    r"\b(?:retired|discontinued|descontinuad[oa]s?|removed|removid[oa]s?|aposentad[oa]s?|legacy|legado|"
    r"archived|arquivad[oa]s?|no longer|não existe[m]?|nao existe[m]?|never existed|superseded|"
    r"substituíd[oa]s?|replaced|replaces|deprecated|obsolete|obsolet[oa]s?|not installed|não instalad[oa]s?|"
    r"does not use|não usa|instead of|em vez de|never use|do not use|não use|never write|must not be used|must not use|não deve ser usad[oa]|"
    r"formerly|as history|\(history|history only|histórico|\*\*why:\*\*)(?!\w)",
    re.I)
FILE_STATUS = re.compile(r"status[^\n]{0,30}\b(retired|historical|history|snapshot|superseded|archived|aposentad[oa]|histórico|not installed)\b|"
                         r"superseded[^\n]{0,40}do not follow|history only", re.I)
HEADING = re.compile(r"^\s{0,3}#{1,6}\s")
# A section titled History/Histórico/Changelog is history as a whole.
HEADING_HISTORY = re.compile(r"\b(history|histórico|historico|changelog)\b", re.I)
FENCE = re.compile(r"^\s{0,3}(```|~~~)")
# A Foundation-relative path: NN_folder[/...]
FOUNDATION_REF = re.compile(r"(?:/root/memory/foundation/|(?<![\w/.-]))((?:0[0-9]|[1-6][0-9])_[A-Za-z][\w.-]*(?:/[\w.@-]+)*)")
# Absolute paths a reader would follow. Foundation documents: every ecosystem root. Agent memories:
# only the shared memory roots (a note may legitimately name a removed worktree or session).
ABS_REF_FOUNDATION = re.compile(r"(/root/(?:memory|\.hermes|project|\.claude|\.codex|\.gemini)/[\w./@-]+)")
ABS_REF_MEMORY = re.compile(r"(/root/(?:memory|\.hermes)/[\w./@-]+)")
PLACEHOLDER = re.compile(r"[<>{}*$\[\]]|XXX|NNN|YYYY", re.I)
MAX_READ_BYTES = 1_000_000

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
# ForgeHub prepends these files, in order, to every task dispatched to an external runtime and cuts
# the block at this many characters (backend/app/core/agent_profile_files.py); past it, the end of
# the agent's memory is silently lost.
DISPATCH_PREAMBLE_FILES = ("IDENTITY.md", "SOUL.md", "USER.md", "MEMORY.md")
DISPATCH_PREAMBLE_MAX_CHARS = 8000
EXTERNAL_HOMES = {"porthus": (".claude",), "aramis": (".codex",), "dartan": (".gemini", "config")}
PROFILE_IDENTITY_FILES = ("SOUL.md", "IDENTITY.md")
# Never walked by the stray-copy scan: backups, runtime caches and third-party content.
STRAY_SCAN_SKIP = {"state-snapshots", "node_modules", "plugins", ".git", "sessions", "cache", "logs",
                   "__pycache__", "antigravity-cli", "47_migrations"}


@dataclass(frozen=True)
class MemoryFile:
    agent: str
    path: Path
    limit: int | None = None        # characters for Hermes memories, bytes otherwise
    unit: str = "bytes"
    max_lines: int | None = None
    text: bool = True               # checked for retired terms and dead links


def read_text(path: Path) -> str:
    """At most MAX_READ_BYTES of a regular file; raises OSError (callers report it as unreadable)."""
    if not path.is_file():
        raise OSError("not a regular file")
    with path.open("rb") as handle:
        return handle.read(MAX_READ_BYTES).decode("utf-8", errors="ignore")


def _lines_with_context(text: str):
    """Yield (line_number, line, allowed): allowed when the line or the one before it carries a
    history marker, when the enclosing heading does, or when the file header marks it historical.
    Lines inside code fences never change the heading."""
    lines = text.splitlines()
    header_history = any(FILE_STATUS.search(line) for line in lines[:12])
    heading_history = False
    in_fence = False
    for i, line in enumerate(lines):
        if FENCE.match(line):
            in_fence = not in_fence
        elif not in_fence and HEADING.match(line):
            heading_history = bool(HISTORY_WORDS.search(line) or HEADING_HISTORY.search(line))
        neighbours = lines[max(i - 1, 0):i + 2]      # a sentence may wrap onto the next line
        allowed = header_history or heading_history or any(HISTORY_WORDS.search(x) for x in neighbours)
        yield i + 1, line, allowed


def _display(term: str) -> str:
    return term.replace("\\b", "").replace("\\", "")


def _clean(target: str) -> str:
    return target.rstrip(".,:;)`'\"")


def text_findings(path: Path, label: str, *, foundation: Path = FOUNDATION, private: bool = False) -> list[str]:
    """Retired terms and dead links in one file. `private` (agent memories): a dead link is reported
    without its target, since the path itself can carry personal data."""
    try:
        text = read_text(path)
    except OSError:
        return [f"{label}: unreadable"]
    abs_ref = ABS_REF_MEMORY if private else ABS_REF_FOUNDATION
    found = []
    for n, line, allowed in _lines_with_context(text):
        if allowed:
            continue
        for pattern, term, repl in _RETIRED:
            if pattern.search(line):
                found.append(f"{label}:{n} uses retired '{_display(term)}' -> {repl}")
        dead = []
        for m in FOUNDATION_REF.finditer(line):
            target = _clean(m.group(1))
            if not PLACEHOLDER.search(target) and not ((foundation / target).exists() or (path.parent / target).exists()):
                dead.append(target)
        for m in abs_ref.finditer(line):
            target = _clean(m.group(1))
            following = line[m.end():m.end() + 1]
            if PLACEHOLDER.search(target) or target.endswith("/") or (following and following in "*<{$"):
                continue
            if not os.path.lexists(target):
                dead.append(target)
        for target in dict.fromkeys(dead):
            found.append(f"{label}:{n} links a missing path" if private else f"{label}:{n} links missing {target}")
    return list(dict.fromkeys(found))


def retired_term_findings(path: Path, label: str) -> list[str]:
    return [f for f in text_findings(path, label) if "uses retired" in f or f.endswith("unreadable")]


def dead_link_findings(path: Path, label: str, foundation: Path = FOUNDATION) -> list[str]:
    return [f for f in text_findings(path, label, foundation=foundation) if "links" in f or f.endswith("unreadable")]


# ---------------------------------------------------------------- Foundation (ECO-067)

def foundation_documents(foundation: Path = FOUNDATION):
    """Live documents, walking without .git or the dated records and never through symlinks."""
    for dirpath, dirnames, filenames in os.walk(foundation):
        rel_dir = Path(dirpath).relative_to(foundation)
        dirnames[:] = sorted(d for d in dirnames if d != ".git" and not (rel_dir == Path(".") and d in HISTORY_DIRS))
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if path.suffix in DOC_SUFFIXES and not path.is_symlink():
                yield path, str(path.relative_to(foundation))


def foundation_findings(foundation: Path = FOUNDATION) -> list[str]:
    findings = [f"unexpected top-level entry: {p.name}" for p in sorted(foundation.iterdir())
                if p.name not in FOUNDATION_ROOT_ENTRIES]
    try:
        root = re.search(r"^canonical_root:\s*(\S+)", read_text(foundation / "09_MANIFEST.yaml"), re.M)
        if not root or root.group(1) != str(foundation):
            findings.append(f"09_MANIFEST.yaml canonical_root is {root.group(1) if root else 'missing'}, expected {foundation}")
    except OSError:
        findings.append("09_MANIFEST.yaml: unreadable")
    for path, label in foundation_documents(foundation):
        findings += text_findings(path, label, foundation=foundation)
    return findings


# ---------------------------------------------------------------- agent memories (ECO-068/069)

def _hermes_limits(profile: Path) -> dict[str, int] | None:
    """The profile's own limits; None when its config can't be read (reported, never guessed)."""
    limits = dict(HERMES_DEFAULT_LIMITS)
    try:
        config = read_text(profile / "config.yaml")
    except OSError:
        return None
    for key, name in (("memory_char_limit", "MEMORY.md"), ("user_char_limit", "USER.md")):
        m = re.search(rf"^\s+{key}:\s*(\d+)", config, re.M)
        if m:
            limits[name] = int(m.group(1))
    return limits


def memory_inventory(profiles: Path = PROFILES, home: Path = HOME) -> list[MemoryFile]:
    files: list[MemoryFile] = []
    if profiles.is_dir():
        for profile in sorted(p for p in profiles.iterdir() if p.is_dir() and not (p / "gateway.parked").exists()):
            if not os.path.lexists(profile / "config.yaml"):
                continue
            limits = _hermes_limits(profile)
            if limits is None:
                files.append(MemoryFile(profile.name, profile / "config.yaml", limit=-1, text=False))
                limits = {}
            for name, limit in limits.items():
                files.append(MemoryFile(profile.name, profile / "memories" / name, limit, "chars"))
            for name, limit in PROFILE_FILE_LIMITS.items():
                files.append(MemoryFile(profile.name, profile / name, limit))
            for rules_file in sorted(profile.glob("ATENDIMENTO_*.md")):
                files.append(MemoryFile(profile.name, rules_file))
    claude = home / ".claude"
    files.append(MemoryFile("porthus", claude / "CLAUDE.md", INSTRUCTION_FILE_LIMIT))
    for name in DISPATCH_PREAMBLE_FILES:
        files.append(MemoryFile("porthus", claude / name, INSTRUCTION_FILE_LIMIT))
    for memory_dir in sorted((claude / "projects").glob("*/memory")):
        files.append(MemoryFile("porthus", memory_dir / "MEMORY.md", max_lines=CLAUDE_INDEX_MAX_LINES))
        files.append(MemoryFile("porthus", memory_dir, CLAUDE_MEMORY_DIR_LIMIT, text=False))
        for note in sorted(memory_dir.glob("*.md")):
            if note.name != "MEMORY.md":
                files.append(MemoryFile("porthus", note))
    codex = home / ".codex"
    for name in ("AGENTS.md", *DISPATCH_PREAMBLE_FILES):
        files.append(MemoryFile("aramis", codex / name, INSTRUCTION_FILE_LIMIT))
    files.append(MemoryFile("aramis", codex / "memories_1.sqlite", CODEX_MEMORY_DB_LIMIT, text=False))
    gemini = home / ".gemini"
    files.append(MemoryFile("dartan", gemini / "GEMINI.md", INSTRUCTION_FILE_LIMIT))
    for note in sorted((gemini / "config").glob("*.md")):
        files.append(MemoryFile("dartan", note, INSTRUCTION_FILE_LIMIT))
    return files


def _tree_size(root: Path) -> int:
    total = 0
    for dirpath, dirnames, filenames in os.walk(root):
        for name in filenames:
            try:
                total += (Path(dirpath) / name).lstat().st_size
            except OSError:
                continue          # removed mid-walk
    return total


def _size(item: MemoryFile) -> int:
    if item.path.is_dir():
        return _tree_size(item.path)
    if item.unit == "chars":
        return len(read_text(item.path))
    return item.path.lstat().st_size if item.path.is_symlink() and not item.path.exists() else item.path.stat().st_size


def memory_size_findings(inventory: list[MemoryFile], knowledge_base: Path = KNOWLEDGE_BASE) -> list[str]:
    findings = []
    for item in inventory:
        if item.limit == -1:
            findings.append(f"{item.agent}: {item.path} unreadable; memory limits not verified")
            continue
        if item.path.is_symlink() and not item.path.exists():
            findings.append(f"{item.agent}: {item.path} is a broken link")
            continue
        if not item.path.exists():
            continue
        try:
            if item.limit is not None:
                size = _size(item)
                if size > item.limit:
                    findings.append(f"{item.agent}: {item.path} is {size} {item.unit} (limit {item.limit})")
            if item.max_lines is not None:
                lines = len(read_text(item.path).splitlines())
                if lines > item.max_lines:
                    findings.append(f"{item.agent}: {item.path} has {lines} lines (only the first {item.max_lines} are loaded)")
        except OSError:
            findings.append(f"{item.agent}: {item.path} unreadable")
    findings += preamble_findings(home=_home_of(inventory))
    if knowledge_base.is_dir():
        for agent in sorted(p for p in knowledge_base.iterdir() if p.is_dir() and not p.is_symlink()):
            size = _tree_size(agent)
            if size > KNOWLEDGE_BASE_AGENT_LIMIT:
                findings.append(f"{agent.name}: knowledge base {agent} is {size} bytes (limit {KNOWLEDGE_BASE_AGENT_LIMIT})")
    return findings


def memory_currency_findings(inventory: list[MemoryFile], foundation: Path = FOUNDATION) -> list[str]:
    findings = []
    for item in inventory:
        if not item.text:
            continue
        if item.path.is_symlink() and not item.path.exists():
            findings.append(f"{item.agent}: {item.path} is a broken link")
            continue
        if not item.path.exists():
            continue
        findings += text_findings(item.path, f"{item.agent}: {item.path}", foundation=foundation, private=True)
    return findings


def _home_of(inventory: list[MemoryFile]) -> Path:
    for item in inventory:
        if item.agent == "porthus" and item.path.name == "CLAUDE.md":
            return item.path.parent.parent
    return HOME


def preamble_findings(home: Path = HOME) -> list[str]:
    """An external agent whose dispatched identity+memory no longer fits loses its end silently."""
    findings = []
    for agent, parts in EXTERNAL_HOMES.items():
        total = 0
        for name in DISPATCH_PREAMBLE_FILES:
            path = home.joinpath(*parts, name)
            try:
                total += len(read_text(path).strip()) + 2 if path.exists() else 0
            except OSError:
                findings.append(f"{agent}: {path} unreadable")
        if total > DISPATCH_PREAMBLE_MAX_CHARS:
            findings.append(f"{agent}: dispatched identity and memory are {total} chars; only the first "
                            f"{DISPATCH_PREAMBLE_MAX_CHARS} reach the agent — compact {'/'.join(DISPATCH_PREAMBLE_FILES)}")
    return findings


# ---------------------------------------------------------------- service rules (ECO-070)

# Same pairs as backend/app/core/service_rules.py (this script can't import the backend).
SERVICE_RULE_PAIRS = {"lara": ("whatsapp", "site", "email"), "maia": ("whatsapp",)}
SERVICE_RULE_MAX_CHARS = 9000
# Where these rules used to live; none may come back (2026-11-14: one source, ForgeHub + the file).
LEGACY_RULE_PATHS = (
    "/root/memory/knowledge_base/lara/atendimento/cartilha-lara-omnichannel.md",
    "/root/.hermes/profiles/maia/whatsapp/INSTRUCOES_PESSOAIS.md",
    "/root/project/agentes/lara/REGRAS.md",
    "/root/project/agentes/maia/REGRAS.md",
)


def service_rule_findings(db_hashes: dict[tuple[str, str], str], profiles: Path = PROFILES,
                          legacy: tuple[str, ...] = LEGACY_RULE_PATHS) -> list[str]:
    """Each agent/channel file exists, fits the hook limit and equals what ForgeHub stores."""
    import hashlib
    findings = []
    for agent, channels in SERVICE_RULE_PAIRS.items():
        for channel in channels:
            path = profiles / agent / f"ATENDIMENTO_{channel.upper()}.md"
            stored = db_hashes.get((agent, channel))
            if not path.exists():
                findings.append(f"{agent}/{channel}: missing {path}" + ("" if stored else " (not registered in ForgeHub)"))
                continue
            try:
                text = read_text(path)
            except OSError:
                findings.append(f"{agent}/{channel}: {path} unreadable")
                continue
            if len(text.strip()) > SERVICE_RULE_MAX_CHARS:
                findings.append(f"{agent}/{channel}: {path} has {len(text.strip())} chars (limit {SERVICE_RULE_MAX_CHARS}; "
                                "past it the agent sees only the start and the end)")
            if stored is None:
                findings.append(f"{agent}/{channel}: {path} exists but is not registered in ForgeHub")
            elif hashlib.sha256(text.encode("utf-8")).hexdigest() != stored:
                findings.append(f"{agent}/{channel}: {path} differs from ForgeHub (edit it on Pessoal -> Regras de atendimento)")
    for old in legacy:
        if os.path.lexists(old):
            findings.append(f"legacy service-rule copy still present: {old}")
    return findings


# ---------------------------------------------------------------- one SOUL per agent (ECO-070)

def profile_file_findings(profiles: Path = PROFILES, home: Path = HOME, foundation: Path = FOUNDATION,
                          knowledge_base: Path = KNOWLEDGE_BASE) -> list[str]:
    """Each agent has exactly one SOUL/IDENTITY, in its canonical home; external agents also have
    USER.md and MEMORY.md; no stray copy anywhere the agents or the Foundation keep files."""
    findings: list[str] = []
    canonical: set[Path] = set()
    parked: set[Path] = set()
    if profiles.is_dir():
        for profile in sorted(p for p in profiles.iterdir() if p.is_dir() and not p.is_symlink()):
            if (profile / "gateway.parked").exists():
                parked.add(profile)
                continue
            if not os.path.lexists(profile / "config.yaml"):
                continue
            for name in PROFILE_IDENTITY_FILES:
                canonical.add(profile / name)
                if not (profile / name).exists():
                    findings.append(f"{profile.name}: missing {profile / name}")
    for agent, parts in EXTERNAL_HOMES.items():
        for name in DISPATCH_PREAMBLE_FILES:
            path = home.joinpath(*parts, name)
            canonical.add(path)
            if not path.exists():
                findings.append(f"{agent}: missing {path}")
    roots = [profiles, home / ".claude", home / ".codex", home / ".gemini", foundation, knowledge_base]
    for root in roots:
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            current = Path(dirpath)
            dirnames[:] = sorted(d for d in dirnames if d not in STRAY_SCAN_SKIP and current / d not in parked)
            for name in filenames:
                path = current / name
                if name in PROFILE_IDENTITY_FILES and path not in canonical:
                    findings.append(f"stray {name}: {path} (one per agent, in its profile home)")
    return findings

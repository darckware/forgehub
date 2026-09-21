"""Parsers for the Hermes Foundation canonical agent registry.

Pure filesystem-reading helpers (no DB access) used by
POST /api/v1/agents/sync/hermes-foundation (app/api/routes/agent.py) to
populate the Agent domain from the Hermes ecosystem's canonical docs.

Canonical source (confirmed by /root/.hermes/foundation/agents/README.md
and the `hermes-foundation-agent-registry` skill -- NOT
/root/.hermes/knowledge_base/vault/Agents/, which is a derived mirror of only
the 8 baseline profiles and explicitly points back here):
  - ECOSYSTEM_AGENTS.md   -- registry: profile/name/layer/role/telegram
  - AGENT_RUNTIME_MATRIX.md -- runtime tier (A/B/C) per profile
  - SUBAGENTS_CATALOG.md  -- WORKER/ROLE sub-agent labels per agent
  - <NAME>.md              -- per-agent contract (Mission section)

Mounted read-only into the backend container at /foundation-agents (see
docker-compose.yml). Per-profile files (skills/) are read from /profiles,
already mounted for app/api/routes/foundation.py.

`source_path` values stored on synced rows use the *host* canonical path
(/root/.hermes/foundation/agents/...) for human traceability, even though
this module reads through the /foundation-agents mount alias.
"""
import re
from pathlib import Path
from typing import Any

import yaml

def _resolve_foundation_agents_dir() -> Path:
    for candidate in (
        Path("/foundation-agents"),
        Path("/foundation-root/14_agents"),
        Path("/governance/14_agents"),
        Path("/root/.hermes/foundation/14_agents"),
        Path("/root/memory/foundation/14_agents"),
        Path("/root/.hermes/foundation/agents"),
        Path("/root/memory/foundation/agents"),
    ):
        if candidate.is_dir() and (candidate / "ECOSYSTEM_AGENTS.md").is_file():
            return candidate
    return Path("/foundation-agents")


FOUNDATION_AGENTS_DIR = _resolve_foundation_agents_dir()
PROFILES_DIR = Path("/profiles")
CANONICAL_AGENTS_DOC_ROOT = "/root/.hermes/foundation/agents"

ECOSYSTEM_AGENTS_PATH = FOUNDATION_AGENTS_DIR / "ECOSYSTEM_AGENTS.md"
RUNTIME_MATRIX_PATH = FOUNDATION_AGENTS_DIR / "AGENT_RUNTIME_MATRIX.md"
SUBAGENTS_CATALOG_PATH = FOUNDATION_AGENTS_DIR / "SUBAGENTS_CATALOG.md"

_RISK_LEVEL_MAP = {"L": "low", "M": "medium", "H": "high", "C": "critical"}

_SUBAGENT_HEADING_RE = re.compile(r"^###\s+.+\(`([a-z0-9\-]+)`\)\s*$")
_SUBAGENT_ITEM_RE = re.compile(r"^-\s+`([a-z0-9\-]+)`\s+—\s+(.*)$")

# ForgeHub's organizational projection of the Hermes roster. Hermes remains
# the canonical identity/mission source; these fields make reporting lines
# explicit instead of overloading the technical `layer` label.
HERMES_ORGANIZATION: dict[str, tuple[str, str, str | None]] = {
    "athos": ("Executive Orchestration", "Portfolio & Delivery Orchestration", None),
    "atlas": ("Product & Planning", "Demand Engineering", "athos"),
    "nomos": ("Product & Planning", "Business Rules & State Design", "atlas"),
    "daedalus": ("Engineering", "Engineering Leadership", "athos"),
    "archimedes": ("Engineering", "Architecture & Integration Design", "daedalus"),
    "datalus": ("Engineering", "Data Engineering", "daedalus"),
    "hermes-ux": ("Engineering", "Product Design & UX", "daedalus"),
    "koios": ("Engineering", "AI & Retrieval Engineering", "daedalus"),
    "forge": ("Engineering", "Implementation & Maintenance", "daedalus"),
    "mnemosyne": ("Knowledge & Context", "Context Governance & Handoffs", "athos"),
    "mnemon": ("Knowledge & Context", "Runtime Memory", "mnemosyne"),
    "scriba": ("Documentation", "Technical Documentation", "athos"),
    "themis": ("Governance & Compliance", "Privacy & Regulatory Governance", "athos"),
    "prometheus": ("Governance & Compliance", "Integration Governance", "themis"),
    "hephaestus": ("Platform & Operations", "Platform Operations", "athos"),
    "hermod": ("Platform & Operations", "FinOps & Model Operations", "hephaestus"),
    "iris": ("Platform & Operations", "Release & Feature Management", "hephaestus"),
    "soteria": ("Platform & Operations", "Reliability & Disaster Recovery", "hephaestus"),
    "talos": ("Platform & Operations", "Workflow Automation", "hephaestus"),
    "aegis": ("Security & Assurance", "Security Leadership", "athos"),
    "argus": ("Security & Assurance", "Code Quality", "aegis"),
    "chronos": ("Security & Assurance", "Regression & Performance", "aegis"),
    "oracle": ("Security & Assurance", "Acceptance & Evidence", "aegis"),
}


def organization_for_profile(profile_slug: str) -> tuple[str | None, str | None, str | None]:
    return HERMES_ORGANIZATION.get(profile_slug, (None, None, None))


def _read_file_safe(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def _contract_filename(profile_slug: str) -> str:
    return profile_slug.upper().replace("-", "_") + ".md"


def _parse_md_table(content: str) -> list[list[str]]:
    """Return data rows (cells, header/separator rows excluded) from a
    GitHub-flavored Markdown pipe table."""
    rows: list[list[str]] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line.startswith("|"):
            continue
        if set(line.replace("|", "").strip()) <= {"-", " "}:
            continue  # separator row, e.g. "|---|---|---|"
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells and cells[0] == "Profile":
            continue  # header row
        rows.append(cells)
    return rows


def list_provisioned_profiles() -> list[str]:
    """Slugs of every real, provisioned agent under /root/.hermes/profiles/
    (mounted at PROFILES_DIR). This -- not the registry docs below -- is
    the source of truth for which agents exist: the docs can list agents
    that are only planned/documented (e.g. `forgenet`) or go stale and
    miss a profile that was added without a doc update yet."""
    if not PROFILES_DIR.is_dir():
        return []
    return sorted(p.name for p in PROFILES_DIR.iterdir() if p.is_dir())


def list_active_provisioned_profiles() -> list[str]:
    """Return provisioned profiles that the active Foundation registry names.

    A directory can survive a restore or be created experimentally without
    promoting its name back to a persistent agent.  The Foundation lifecycle
    contract therefore requires both pieces of evidence: a live directory and
    an active registry row.  This deliberately excludes archived Tier C role
    names and undocumented directories such as accidental duplicates.
    """
    provisioned = set(list_provisioned_profiles())
    registered = {entry["profile_slug"] for entry in parse_agent_registry()}
    return sorted(provisioned & registered)


def read_profile_forgerouter_api_key(profile_slug: str) -> str | None:
    """Return an already-provisioned agent key without logging it.

    ForgeHub imports this into its encrypted credential column during the
    governed Hermes sync. Placeholder/env-reference values are ignored.

    The credential lives at `providers.<model.provider>.api_key`, not
    `model.api_key` (that block only holds provider/default/api_mode/main
    -- confirmed against every current profile's config.yaml, all of which
    use `forgerouter` as the provider name).
    """
    config_path = PROFILES_DIR / profile_slug / "config.yaml"
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except (FileNotFoundError, yaml.YAMLError):
        return None
    provider = str((config.get("model") or {}).get("provider") or "forgerouter")
    providers = config.get("providers") or {}
    api_key = str((providers.get(provider) or {}).get("api_key") or "").strip()
    if not api_key or api_key.startswith("${"):
        return None
    return api_key


def parse_agent_registry() -> list[dict[str, Any]]:
    """Roster of every Hermes agent *documented* in ECOSYSTEM_AGENTS.md:
    profile_slug, name, layer, role, telegram_required, runtime_tier.
    Includes entries with no provisioned profile directory yet (e.g.
    `forgenet`) -- this is metadata to enrich a provisioned profile with,
    not itself the list of agents to register (see
    list_provisioned_profiles)."""
    matrix_content = _read_file_safe(RUNTIME_MATRIX_PATH) or ""
    tier_by_slug: dict[str, str] = {}
    for cells in _parse_md_table(matrix_content):
        if len(cells) < 4:
            continue
        # Since the 2026-07-18 Tier B archival, the only 4-cell table left in
        # this doc is "Persistent Hermes core" (Profile | Agent | Role |
        # Gateway) -- every row in it is tier A by construction now, there is
        # no more per-row tier letter to read (cells[3] is the Gateway
        # yes/no column, not a tier code; the old Tier B row is gone, and the
        # two other tables in the file -- archived-role mapping, external
        # runtimes -- have fewer than 4 cells and are already filtered out
        # above).
        tier_by_slug[cells[0].strip("`")] = "A"

    registry_content = _read_file_safe(ECOSYSTEM_AGENTS_PATH) or ""
    agents: list[dict[str, Any]] = []
    for cells in _parse_md_table(registry_content):
        if len(cells) < 5:
            continue
        slug = cells[0].strip("`")
        agents.append(
            {
                "profile_slug": slug,
                "name": cells[1],
                "layer": cells[2],
                "role": cells[3],
                "telegram_required": cells[4].strip().lower() == "yes",
                "runtime_tier": tier_by_slug.get(slug),
            }
        )
    return agents


def parse_profile_identity(profile_slug: str) -> dict[str, str | None]:
    """Read the agent's own IDENTITY.md -- the live "who am I" file every
    profile carries under /root/.hermes/profiles/<slug>/ -- as the primary
    source for name/layer/mission during sync, since it reflects the
    agent's actual current configuration rather than the Foundation docs'
    registry snapshot, which can go stale (2026-07-29, Marcelo: "a
    sincronização vem da documentação que pode estar desatualizada. E não
    da configuração dos agentes" -- ECOSYSTEM_AGENTS.md/<NAME>.md are still
    consulted as a fallback when a field is missing here, per "você pode
    até consultar algumas coisas da documentação" -- see sync_hermes_foundation
    in api/routes/agent.py, which does the actual merge).

    Format observed across every current profile (plain "- Key: Value"
    lines, not YAML frontmatter):
        # IDENTITY.md — Athos
        - Name: Athos
        - Runtime: Hermes profile `athos`
        - Layer: Governance
        - Role: Chief of Staff / Ecosystem Governor
        - Mission: govern priorities, approvals, orchestration, ...
    """
    content = _read_file_safe(PROFILES_DIR / profile_slug / "IDENTITY.md")
    if content is None:
        return {}
    fields: dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line.startswith("- ") or ":" not in line:
            continue
        key, _, value = line[2:].partition(":")
        value = value.strip()
        if value:
            fields[key.strip().lower()] = value
    return {
        "name": fields.get("name"),
        "layer": fields.get("layer"),
        "role": fields.get("role"),
        "mission": fields.get("mission"),
    }


def parse_agent_mission(profile_slug: str) -> tuple[str | None, str | None]:
    """Returns (mission_text, canonical_source_path) for an agent's
    contract file, or (None, None) if no contract file exists yet."""
    filename = _contract_filename(profile_slug)
    content = _read_file_safe(FOUNDATION_AGENTS_DIR / filename)
    if content is None:
        return None, None

    mission_lines: list[str] = []
    in_section = False
    for line in content.splitlines():
        if line.strip() == "## Mission":
            in_section = True
            continue
        if in_section:
            if line.startswith("## "):
                break
            if line.strip():
                mission_lines.append(line.strip())

    mission = " ".join(mission_lines) if mission_lines else None
    source_path = f"{CANONICAL_AGENTS_DOC_ROOT}/{filename}"
    return mission, source_path


def parse_subagent_catalog() -> dict[str, list[dict[str, str]]]:
    """WORKER/ROLE sub-agent labels grouped by owning agent's profile_slug."""
    content = _read_file_safe(SUBAGENTS_CATALOG_PATH) or ""
    catalog: dict[str, list[dict[str, str]]] = {}
    current_slug: str | None = None

    for raw_line in content.splitlines():
        line = raw_line.strip()
        heading_match = _SUBAGENT_HEADING_RE.match(line)
        if heading_match:
            current_slug = heading_match.group(1)
            catalog.setdefault(current_slug, [])
            continue
        item_match = _SUBAGENT_ITEM_RE.match(line)
        if item_match and current_slug:
            name, description = item_match.groups()
            catalog[current_slug].append({"name": name, "description": description.strip()})

    return catalog


def _parse_skill_frontmatter(content: str) -> dict[str, Any]:
    if not content.startswith("---"):
        return {}
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        data = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def parse_profile_skills(profile_slug: str) -> list[dict[str, Any]]:
    """Skills declared under a profile's skills/ tree (leaf SKILL.md files
    only; hidden housekeeping dirs like .hub/.curator_backups are
    skipped). Skill name/version are read from frontmatter, falling back
    to the containing directory name and "1.0.0" when absent."""
    skills_dir = PROFILES_DIR / profile_slug / "skills"
    if not skills_dir.is_dir():
        return []

    results: list[dict[str, Any]] = []
    for skill_md in skills_dir.rglob("SKILL.md"):
        relative_parts = skill_md.relative_to(skills_dir).parts
        if any(part.startswith(".") for part in relative_parts):
            continue

        content = _read_file_safe(skill_md)
        if content is None:
            continue

        frontmatter = _parse_skill_frontmatter(content)
        name = str(frontmatter.get("name") or skill_md.parent.name)
        version = str(frontmatter.get("version") or "1.0.0")
        description = frontmatter.get("description")

        metadata = frontmatter.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        created_by = frontmatter.get("created_by") or metadata.get("created_by")
        origin = (
            "foundation"
            if metadata.get("scope") == "governance" or created_by == "agent"
            else "internal"
        )

        risk_letter = str(metadata.get("risk_level") or "").strip().upper()
        risk_level = _RISK_LEVEL_MAP.get(risk_letter, "low")

        prerequisites = frontmatter.get("prerequisites")
        prerequisites = prerequisites if isinstance(prerequisites, dict) else {}
        perms = [str(t) for t in (prerequisites.get("tools") or [])]
        perms += [str(e) for e in (prerequisites.get("env_vars") or [])]
        permissions = ", ".join(perms) if perms else "unspecified (not declared in source SKILL.md)"

        results.append(
            {
                "name": name,
                "version": version,
                "description": str(description) if description else None,
                "origin": origin,
                "risk_level": risk_level,
                "permissions": permissions,
            }
        )

    return results

"""Canonical ecosystem audit checklist metadata.

ECO-021 is retired. ECO-058 stays disabled until the first offsite snapshot
and a sample restore have been verified; its historical ID is reserved.
"""

import ast
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CheckSpec:
    name: str
    category: str
    agent_profile: str
    description: str
    timeout_seconds: int = 55
    enabled: bool = True
    activation_condition: str | None = None


RETIRED_AUDIT_CHECKS = {
    "ECO-021": "The 09:00–23:59 cron window was abandoned for 24x7 operation.",
}

# ID, category, owner, description, timeout, enabled.
_CHECK_ROWS = (
    ('ECO-001', 'foundation', 'athos', 'Canonical Foundation documents exist and are readable', 55, True),
    ('ECO-002', 'foundation', 'athos', 'Foundation contains documentation only; operational scripts stay profile-owned', 55, True),
    ('ECO-003', 'knowledge', 'mnemosyne', 'Shared Knowledge Base layout exists for core and external agents', 55, True),
    ('ECO-004', 'agents', 'athos', 'Core Hermes profiles and external runtime integrations pass the contract validator', 55, True),
    ('ECO-005', 'agents', 'athos', 'Eight principal Hermes gateways are active and healthy', 55, True),
    ('ECO-006', 'services', 'hephaestus', 'ForgeHub bridge and Kanboard worker systemd services are active', 55, True),
    ('ECO-007', 'containers', 'hephaestus', 'All ecosystem application containers are running and healthy', 55, True),
    ('ECO-008', 'network', 'hephaestus', 'Every ecosystem container participates in foundation_network', 55, True),
    ('ECO-009', 'services', 'hephaestus', 'All ecosystem application endpoints are healthy', 55, True),
    ('ECO-010', 'database', 'daedalus', 'Each ecosystem application PostgreSQL instance accepts connections', 55, True),
    ('ECO-011', 'database', 'daedalus', 'Foundation PostgreSQL schema topology has no application tables in public', 55, True),
    ('ECO-012', 'memory', 'mnemosyne', 'Hindsight shared maintenance functions exist and execute', 55, True),
    ('ECO-013', 'memory', 'mnemosyne', 'Hindsight retain/recall pipeline is connected and populated', 55, True),
    ('ECO-014', 'memory', 'mnemosyne', 'Hindsight recent logs contain no maintenance discovery failure', 55, True),
    ('ECO-015', 'provider', 'atlas', 'ForgeRouter is healthy and remains the exclusive agent-facing LLM provider', 55, True),
    ('ECO-016', 'knowledge', 'scriba', 'ForgeHub mounts the complete shared Knowledge Base at /vault', 55, True),
    ('ECO-017', 'configuration', 'daedalus', 'Docker Compose configurations for all ecosystem applications are valid', 55, True),
    ('ECO-018', 'capacity', 'hephaestus', 'Root filesystem disk and inode usage remain below 85 percent', 55, True),
    ('ECO-019', 'security', 'aegis', 'Secret-bearing configuration files for all ecosystem applications are owner-only', 55, True),
    ('ECO-020', 'cron', 'athos', 'Hermes cron scheduler heartbeat is current', 55, True),
    ('ECO-022', 'cron', 'athos', 'Enabled Hermes crons have no failed latest execution', 55, True),
    ('ECO-023', 'cron', 'athos', 'Complete ecosystem audit is scheduled weekly on Sunday at 19:00', 55, True),
    ('ECO-024', 'backup', 'hephaestus', 'Weekly Hermes backup archive is recent and nontrivial', 55, True),
    ('ECO-025', 'audit', 'themis', 'Foundation and ForgeHub audit persistence contains the required active checks', 55, True),
    ('ECO-026', 'knowledge', 'scriba', 'Active Knowledge Base contains no retired provider-rotation or vault references', 55, True),
    ('ECO-027', 'memory', 'mnemosyne', 'Hindsight has no valid obsolete provider, vault or workspace facts', 55, True),
    ('ECO-028', 'scripts', 'daedalus', 'Athos operational shell and Python scripts pass syntax validation', 55, True),
    ('ECO-029', 'infrastructure', 'hephaestus', 'Host clock is plausible and timezone is America/Sao_Paulo', 55, True),
    ('ECO-030', 'skills', 'athos', 'Hermes skills have valid contracts and no obsolete ecosystem instructions', 55, True),
    ('ECO-031', 'profiles', 'athos', 'Athos profile files, configuration, memory links and owned scripts are valid', 55, True),
    ('ECO-032', 'profiles', 'aegis', 'Aegis profile files, configuration, memory links and owned scripts are valid', 55, True),
    ('ECO-033', 'profiles', 'daedalus', 'Daedalus profile files, configuration, memory links and owned scripts are valid', 55, True),
    ('ECO-034', 'profiles', 'hephaestus', 'Hephaestus profile files, configuration, memory links and owned scripts are valid', 55, True),
    ('ECO-035', 'profiles', 'atlas', 'Atlas profile files, configuration, memory links and owned scripts are valid', 55, True),
    ('ECO-036', 'profiles', 'mnemosyne', 'Mnemosyne profile files, configuration, memory links and owned scripts are valid', 55, True),
    ('ECO-037', 'profiles', 'scriba', 'Scriba profile files, configuration, memory links and owned scripts are valid', 55, True),
    ('ECO-038', 'profiles', 'themis', 'Themis profile files, configuration, memory links and owned scripts are valid', 55, True),
    ('ECO-039', 'cleanup', 'daedalus', 'Host cleanup includes bounded Docker image and build cache usage', 600, True),
    ('ECO-040', 'telegram', 'athos', 'Telegram voice input is transcribed locally and receives a pt-BR voice reply', 180, True),
    ('ECO-041', 'cli', 'athos', 'Hermes CLI voice command, local STT and pt-BR TTS are ready', 60, True),
    ('ECO-042', 'profiles', 'kairos', 'Kairos profile contract is valid', 55, True),
    ('ECO-043', 'profiles', 'lara', 'Lara profile contract is valid', 55, True),
    ('ECO-044', 'agents', 'athos', 'Every active Hermes profile and external runtime has a registered agent; parked profiles are excluded', 55, True),
    ('ECO-045', 'containers', 'hephaestus', 'Every ecosystem container has an approved restart policy in Compose and runtime', 55, True),
    ('ECO-046', 'backup', 'daedalus', 'Every application PostgreSQL database has a recent readable and nontrivial dump', 120, True),
    ('ECO-047', 'security', 'aegis', 'Application listeners obey the interface and port allow-list; public API docs are closed', 120, True),
    ('ECO-048', 'network', 'hephaestus', 'Cloudflare routes respond and ForgeVault denies anonymous and public agent access including MCP', 120, False, 'Verified local/public agent token probe without logging credentials'),
    ('ECO-049', 'services', 'hephaestus', 'ForgeVault API, web, PostgreSQL and Redis are healthy', 55, True),
    ('ECO-050', 'services', 'hephaestus', 'Darckware site and API respond and Lara site chat returns a reply', 120, False, 'Safe dry-run Lara site chat probe that does not contact a client'),
    ('ECO-051', 'services', 'hephaestus', 'CoreTI web, API, nginx and PostgreSQL are healthy', 55, True),
    ('ECO-052', 'network', 'aegis', 'Headscale, Tailscale and RustDesk relay services are active', 55, True),
    ('ECO-053', 'agents', 'athos', 'Every active Hermes profile has authenticated outbound Agent Activity hooks', 55, True),
    ('ECO-054', 'agents', 'athos', 'Messages dispatches and feedback are timely with at most 20 percent failures over seven days', 120, True),
    ('ECO-055', 'agents', 'athos', 'Porthus, Aramis and Dartan have valid homes, profiles and ForgeHub MCP configuration', 55, False, 'Verified external runtime home and ForgeHub MCP inventory'),
    ('ECO-056', 'provider', 'atlas', 'Every active agent has a matching configured ForgeRouter key', 55, False, 'Secret-safe comparison with ForgeRouter agent key registry'),
    ('ECO-057', 'memory', 'mnemosyne', 'ForgeHub Hindsight retention timer is active and its latest run succeeded', 55, True),
    ('ECO-058', 'backup', 'hephaestus', 'Offsite backup has a snapshot within 36 hours and the latest repository check succeeded', 120, False, 'First offsite snapshot and sample restore verified by the operator'),
)

CANONICAL_AUDIT_CHECKS: dict[str, CheckSpec] = {
    row[0]: CheckSpec(*row) for row in _CHECK_ROWS
}


def verifier_check_names(source: str) -> set[str]:
    """Read CHECKS keys without importing or running host code."""
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(target, ast.Name) and target.id == "CHECKS" for target in targets):
            continue
        if not isinstance(node.value, ast.Dict):
            raise ValueError("CHECKS must be a dictionary literal")
        keys = [ast.literal_eval(key) for key in node.value.keys]
        if not all(isinstance(key, str) for key in keys):
            raise ValueError("CHECKS keys must be strings")
        if len(keys) != len(set(keys)):
            raise ValueError("CHECKS contains duplicate IDs")
        return set(keys)
    raise ValueError("CHECKS dictionary not found")

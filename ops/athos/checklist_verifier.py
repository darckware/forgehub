#!/usr/bin/env python3
"""Weekly, read-only ecosystem checklist with PostgreSQL audit evidence.

The active checklist is stored in ``audit.foundation_checklist``. Each active
description starts with a stable ``[ECO-NNN]`` key; this avoids coupling check
logic to translated prose. Retired rows and their historical logs are kept.
"""

from __future__ import annotations

import ast
import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

FOUNDATION = Path("/root/memory/foundation")
HERMES = Path("/root/.hermes")
ATHOS = HERMES / "profiles/athos"
KB = HERMES / "knowledge_base"
FORGEHUB = Path("/root/project/forgehub")
FORGEROUTER = Path("/root/project/forgerouter")
CORE_PROFILES = ("athos", "aegis", "daedalus", "hephaestus", "atlas", "mnemosyne", "scriba", "themis", "kairos", "lara")
# Every Hermes profile the gateway serves: the core set plus Maia (Marcelo's personal assistant).
# Maia has no shared Knowledge Base folder (personal data stays in her private Hindsight bank), so
# KB checks keep using CORE_PROFILES.
HERMES_PROFILES = (*CORE_PROFILES, "maia")
# Profiles whose Telegram is required (14_agents/ECOSYSTEM_AGENTS.md, 2026-09-27).
TELEGRAM_PROFILES = ("athos", "aegis", "kairos", "lara")
EXTERNAL_KB = ("aramis", "porthus", "dartan")
# Active agents executed outside Hermes profiles. Keep this roster aligned with
# the canonical Foundation registry. Vector/OpenClaw was retired on 2026-10-12.
EXTERNAL_RUNTIMES = {
    "aramis": "codex",
    "porthus": "claude",
    "dartan": "agy",
}
# Knowledge Base roots that are not agents: Marcelo's own stack/standards KB.
OTHER_KB_ROOTS = ("marcelo",)
# One Postgres per application since the 2026-09-04 topology migration
# (36_governance/POSTGRESQL_TOPOLOGY.md); company_postgres/foundation_postgres are gone.
CONTAINERS = ("forgehub_postgres", "hindsight_postgres", "forgerouter_postgres", "forgehub-backend", "forgehub-frontend", "forgerouter", "hindsight")
POSTGRES_CONTAINERS = ("forgehub_postgres", "hindsight_postgres", "forgerouter_postgres")


@dataclass
class Result:
    ok: bool
    notes: str


def run(args: list[str], timeout: int = 30, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)


def ok(notes: str) -> Result:
    return Result(True, notes)


def fail(notes: str) -> Result:
    return Result(False, notes[:4000])


def psql(query: str, database: str = "foundation", container: str = "hindsight_postgres") -> str:
    result = run(["docker", "exec", container, "psql", "-v", "ON_ERROR_STOP=1", "-U", "foundation", "-d", database, "-At", "-c", query])
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def http_json(url: str) -> dict:
    with urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def check_docs() -> Result:
    required = (
        "10_README.md", "09_MANIFEST.yaml", "36_governance/FOUNDATION.md", "36_governance/FOUNDATION_STRUCTURE.md",
        "36_governance/AGENT_PROFILE_STANDARD.md", "36_governance/KNOWLEDGE_ARCHITECTURE.md",
        "36_governance/POSTGRESQL_TOPOLOGY.md", "52_policies/SECURITY_POLICY.md",
        "52_policies/OPERATIONAL_POLICY.md", "43_map/ECOSYSTEM_MAP.md", "43_map/ECOSYSTEM_KNOWLEDGE_MAP.md",
        "14_agents/ECOSYSTEM_AGENTS.md", "14_agents/AGENT_RUNTIME_MATRIX.md",
    )
    missing = [item for item in required if not (FOUNDATION / item).is_file() or not os.access(FOUNDATION / item, os.R_OK)]
    return fail(f"Missing/unreadable: {missing}") if missing else ok(f"{len(required)} canonical documents readable")


def check_foundation_boundary() -> Result:
    scripts = FOUNDATION / "scripts"
    executables = [str(p) for p in FOUNDATION.rglob("*") if p.is_file() and os.access(p, os.X_OK) and "plugins/" not in str(p.relative_to(FOUNDATION))]
    if scripts.exists() or executables:
        return fail(f"Foundation execution boundary violated: scripts_dir={scripts.exists()} executables={executables[:10]}")
    return ok("Foundation contains no central scripts or unexpected executables")


def check_kb_layout() -> Result:
    expected = [KB / p for p in (*CORE_PROFILES, *EXTERNAL_KB)]
    expected += [KB / "shared" / p for p in ("decisions", "discoveries", "inbox", "runbooks")]
    missing = [str(p) for p in expected if not p.is_dir()]
    allowed_roots = set((*CORE_PROFILES, *EXTERNAL_KB, *OTHER_KB_ROOTS, "shared"))
    unexpected = sorted(p.name for p in KB.iterdir() if p.is_dir() and p.name not in allowed_roots)
    if missing or unexpected:
        return fail(f"Knowledge Base drift: missing={missing}, unexpected={unexpected}")
    return ok(f"Knowledge Base layout valid ({len(allowed_roots)} active roots)")


def check_profiles() -> Result:
    # A parked profile (`hermes -p X gateway stop`, marker gateway.parked) is retired from
    # service -- e.g. prometheus, Tier B, parked 2026-09-27 -- and not part of the active set.
    active = {p.name for p in (HERMES / "profiles").iterdir() if p.is_dir() and not (p / "gateway.parked").exists()}
    expected = set(HERMES_PROFILES)
    if active != expected:
        return fail(f"Active profile set drift: missing={sorted(expected-active)}, unexpected={sorted(active-expected)}")
    result = run(["python3", str(ATHOS / "scripts/validate_agent_profiles.py")], timeout=30)
    return ok(result.stdout.strip()) if result.returncode == 0 else fail((result.stdout + result.stderr).strip())


def check_gateways() -> Result:
    """Hermes multiplex (September 2026): ONE user unit, hermes-gateway.service, serves every
    profile. Healthy = that unit active, exactly one gateway process, every core profile in
    served_profiles, and every Telegram-required profile's adapter connected."""
    env = dict(os.environ, XDG_RUNTIME_DIR="/run/user/0")
    unit = subprocess.run(["systemctl", "--user", "is-active", "hermes-gateway.service"],
                          capture_output=True, text=True, env=env, check=False).stdout.strip()
    procs = []
    for cmdline in Path("/proc").glob("[0-9]*/cmdline"):
        try:
            argv = cmdline.read_bytes().split(b"\0")
        except OSError:
            continue
        # argv must contain the two arguments `gateway run` -- a text search also matches
        # every shell whose command line merely mentions it.
        if any(argv[i] == b"gateway" and argv[i + 1] == b"run" for i in range(len(argv) - 1)):
            procs.append(cmdline.parent.name)
    bad = []
    if unit != "active":
        bad.append(f"hermes-gateway.service={unit or 'unknown'}")
    if len(procs) != 1:
        bad.append(f"gateway processes={len(procs)} (expected 1)")
    try:
        state = json.loads((HERMES / "gateway_state.json").read_text())
    except Exception as exc:
        return fail(f"gateway_state.json unreadable: {exc}; " + "; ".join(bad))
    served = set(state.get("served_profiles") or [])
    missing = [p for p in HERMES_PROFILES if p not in served]
    if missing:
        bad.append(f"not served: {missing}")
    platforms = state.get("platforms") or {}
    down = [p for p in TELEGRAM_PROFILES if (platforms.get(f"{p}:telegram") or {}).get("state") != "connected"]
    if down:
        bad.append(f"telegram not connected: {down}")
    return fail("; ".join(bad)) if bad else ok(
        f"Multiplex gateway active; {len(HERMES_PROFILES)} Hermes profiles served; Telegram connected for {len(TELEGRAM_PROFILES)}")


def check_support_services() -> Result:
    # Kanboard was discontinued from the ForgeHub flow (2026-08-13) and its
    # container removed -- asserting its worker is active would fail forever.
    units = ("forgehub-chat-bridge.service",)
    bad = [unit for unit in units if run(["systemctl", "is-active", "--quiet", unit]).returncode]
    return fail(f"Inactive services: {bad}") if bad else ok("ForgeHub bridge active")


def container_state(name: str) -> tuple[str, str, list[str]]:
    data = json.loads(run(["docker", "inspect", name]).stdout)[0]
    state = data["State"]
    health = (state.get("Health") or {}).get("Status", "none")
    return state.get("Status", "unknown"), health, list(data["NetworkSettings"]["Networks"].keys())


def check_containers() -> Result:
    bad = []
    for name in CONTAINERS:
        try:
            status, health, _ = container_state(name)
        except Exception as exc:
            bad.append(f"{name}:inspect:{exc}")
            continue
        if status != "running" or health not in ("none", "healthy"):
            bad.append(f"{name}:{status}/{health}")
    return fail("; ".join(bad)) if bad else ok("Seven ecosystem containers running; defined healthchecks are healthy")


def check_network() -> Result:
    bad = []
    for name in CONTAINERS:
        try:
            _, _, networks = container_state(name)
            if "foundation_network" not in networks:
                bad.append(f"{name}:{networks}")
        except Exception as exc:
            bad.append(f"{name}:{exc}")
    return fail("; ".join(bad)) if bad else ok("All ecosystem containers use foundation_network")


def check_endpoints() -> Result:
    endpoints = {
        "forgerouter": "http://127.0.0.1:2100/health",
        "hindsight": "http://127.0.0.1:8888/health",
        "forgehub": "http://127.0.0.1:8000/health",
    }
    bad = []
    for name, url in endpoints.items():
        try:
            payload = http_json(url)
            if payload.get("status") not in ("ok", "healthy"):
                bad.append(f"{name}:{payload}")
        except Exception as exc:
            bad.append(f"{name}:{exc}")
    for name, url in (("frontend", "http://127.0.0.1:4173/"),):
        result = run(["curl", "-fsS", "-o", "/dev/null", url])
        if result.returncode:
            bad.append(f"{name}:unreachable")
    return fail("; ".join(bad)) if bad else ok("ForgeRouter, Hindsight and ForgeHub endpoints healthy")


def check_postgres() -> Result:
    bad = [name for name in POSTGRES_CONTAINERS if run(["docker", "exec", name, "pg_isready", "-q"]).returncode]
    return fail(f"PostgreSQL not ready: {bad}") if bad else ok(f"{len(POSTGRES_CONTAINERS)} ecosystem PostgreSQL instances accept connections")


def check_schema_topology() -> Result:
    counts = psql("SELECT count(*) FILTER (WHERE table_schema='hindsight'), count(*) FILTER (WHERE table_schema='public') FROM information_schema.tables WHERE table_type='BASE TABLE';")
    hindsight, public = (int(v) for v in counts.split("|"))
    audit = int(psql("SELECT count(*) FROM information_schema.tables WHERE table_schema='audit' AND table_type='BASE TABLE';"))
    if hindsight != 21 or public != 0 or audit != 7:
        return fail(f"Schema drift: hindsight={hindsight}, public={public}, audit={audit}")
    return ok("Schema topology valid: hindsight=21 tables, audit=7, public=0 application tables")


def check_hindsight_functions() -> Result:
    count = int(psql("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname IN ('mental_models_with_cron','banks_needing_consolidation','schemas_with_expired_rows');"))
    if count != 3:
        return fail(f"Expected 3 shared Hindsight functions, found {count}")
    psql("SELECT count(*) FROM public.banks_needing_consolidation(); SELECT count(*) FROM public.mental_models_with_cron(); SELECT count(*) FROM public.schemas_with_expired_rows('llm_requests','created_at',30);")
    return ok("Three Hindsight shared maintenance functions exist and execute")


def check_hindsight_pipeline() -> Result:
    health = http_json("http://127.0.0.1:8888/health")
    stats = http_json("http://127.0.0.1:8888/v1/default/banks/hermes/stats")
    nodes = int(stats.get("total_nodes") or 0)
    if health.get("database") != "connected" or nodes <= 0:
        return fail(f"Hindsight pipeline unhealthy: health={health}, total_nodes={nodes}")
    return ok(f"Hindsight database connected; {nodes} memory nodes available")


def check_hindsight_logs() -> Result:
    result = run(["docker", "logs", "--since", "10m", "hindsight"], timeout=20)
    text = (result.stdout + result.stderr)
    pattern = re.compile(r"maintenance.*failed|mental_models_with_cron.*does not exist|banks_needing_consolidation.*does not exist|schemas_with_expired_rows.*does not exist", re.I)
    hits = [line for line in text.splitlines() if pattern.search(line)]
    return fail("Recent Hindsight maintenance failures: " + " | ".join(hits[-5:])) if hits else ok("No Hindsight maintenance discovery failure in the last 10 minutes")


def check_forgerouter() -> Result:
    payload = http_json("http://127.0.0.1:2100/health")
    return ok("ForgeRouter health OK; profile exclusivity covered by profile validator") if payload.get("status") == "ok" else fail(str(payload))


def check_kb_mount() -> Result:
    mounts = json.loads(run(["docker", "inspect", "forgehub-backend", "--format", "{{json .Mounts}}"] ).stdout)
    found = any(item.get("Source") == str(KB) and item.get("Destination") == "/vault" for item in mounts)
    return ok("ForgeHub mounts the complete shared Knowledge Base at /vault") if found else fail("ForgeHub /vault mount does not target the shared Knowledge Base root")


def check_compose() -> Result:
    bad = []
    for directory, files in ((FORGEHUB, ["docker-compose.yml"]), (FORGEROUTER, ["docker-compose.yml"])):
        result = run(["docker", "compose", *sum((["-f", f] for f in files), []), "config", "--quiet"], cwd=directory)
        if result.returncode:
            bad.append(f"{directory}:{result.stderr.strip()}")
    return fail("; ".join(bad)) if bad else ok("ForgeHub and ForgeRouter Compose configurations are valid")


def check_capacity() -> Result:
    disk = run(["df", "-P", "/"]).stdout.splitlines()[-1].split()
    inode = run(["df", "-Pi", "/"]).stdout.splitlines()[-1].split()
    disk_pct, inode_pct = int(disk[4].rstrip("%")), int(inode[4].rstrip("%"))
    if disk_pct >= 85 or inode_pct >= 85:
        return fail(f"Capacity threshold exceeded: disk={disk_pct}% inode={inode_pct}%")
    return ok(f"Capacity safe: disk={disk_pct}% inode={inode_pct}%")


def check_secret_modes() -> Result:
    paths = (FORGEHUB / ".env", FORGEROUTER / ".env", ATHOS / "config.yaml")
    bad = [f"{path}:{oct(path.stat().st_mode & 0o777)}" for path in paths if path.exists() and path.stat().st_mode & 0o077]
    return fail("Secret-bearing files too permissive: " + ", ".join(bad)) if bad else ok("Secret-bearing files are owner-only")


def load_jobs() -> list[dict]:
    return json.loads((ATHOS / "cron/jobs.json").read_text())["jobs"]


def check_cron_heartbeat() -> Result:
    heartbeat = ATHOS / "cron/ticker_heartbeat"
    age = datetime.now().timestamp() - heartbeat.stat().st_mtime if heartbeat.exists() else 10**9
    return ok(f"Hermes scheduler heartbeat age={age:.0f}s") if age < 600 else fail(f"Hermes scheduler heartbeat stale/missing: age={age:.0f}s")


def check_cron_window() -> Result:
    bad = []
    for job in load_jobs():
        if not job.get("enabled") or job.get("schedule", {}).get("kind") != "cron":
            continue
        expr = job["schedule"]["expr"]
        parts = expr.split()
        if len(parts) != 5:
            bad.append(f"{job['name']}:{expr}")
            continue
        hour = parts[1]
        allowed = hour in {str(h) for h in range(9, 24)} or hour == "9-23" or hour.startswith("9-23/")
        if not allowed:
            bad.append(f"{job['name']}:{expr}")
    return fail("Jobs outside 09:00-23:59: " + ", ".join(bad)) if bad else ok("All enabled Hermes cron jobs are restricted to 09:00-23:59")


def check_cron_status() -> Result:
    bad = [f"{j['name']}:{j.get('last_status')}:{j.get('last_error')}" for j in load_jobs() if j.get("enabled") and j.get("last_run_at") and j.get("last_status") not in ("ok", None)]
    return fail("Failed enabled jobs: " + "; ".join(bad)) if bad else ok("Enabled Hermes jobs have no failed latest execution")


def check_weekly_audit() -> Result:
    jobs = [j for j in load_jobs() if j.get("enabled") and j.get("name") == "ecosystem-weekly-audit"]
    if len(jobs) != 1 or jobs[0].get("schedule", {}).get("expr") != "0 19 * * 0" or jobs[0].get("script") != "ecosystem_weekly_audit.sh":
        return fail(f"Weekly audit cron missing or drifted: {jobs}")
    return ok("Weekly ecosystem audit scheduled Sunday 19:00")


def check_backup() -> Result:
    files = list(Path("/root/backup/hermes-root/weekly").glob("*.tar.*"))
    if not files:
        return fail("No weekly Hermes archive found")
    latest = max(files, key=lambda path: path.stat().st_mtime)
    age_days = (datetime.now().timestamp() - latest.stat().st_mtime) / 86400
    if age_days > 8 or latest.stat().st_size < 10_000_000:
        return fail(f"Weekly backup stale/suspicious: {latest}, age={age_days:.1f}d, size={latest.stat().st_size}")
    cleanup = (ATHOS / "scripts/create_trash_cleanup_task.sh").read_text(errors="replace")
    if "forgehub-auditor-before-*.dump" not in cleanup or "-atime +30" not in cleanup:
        return fail("Auditor recovery-dump cleanup policy is missing or not set to 30 unused days")
    return ok(f"Weekly backup current: {latest.name}, age={age_days:.1f}d; Auditor dumps expire after 30 unused days")


def check_audit_tables() -> Result:
    foundation_count = int(psql("SELECT count(*) FROM audit.foundation_checklist WHERE status NOT IN ('retired','disabled');"))
    forge_count = int(psql("SELECT count(*) FROM company.audit_checks WHERE enabled;", "forgehub", "forgehub_postgres"))
    return ok(f"Audit persistence ready: Foundation={foundation_count}, ForgeHub={forge_count}") if foundation_count >= 52 and forge_count >= 52 else fail(f"Audit checklist incomplete: Foundation={foundation_count}, ForgeHub={forge_count}")


def check_kb_obsolete() -> Result:
    result = run(["rg", "-n", "-i", "hermes-provider-rotation|fallback_providers|knowledge_base/vault|provider_groups", str(KB)])
    historical = ("/inventory/", "decisions/2026-06-25-vault-decommission.md")  # file and its INDEX link
    active_hits = [line for line in result.stdout.splitlines() if not any(marker in line for marker in historical)]
    return fail("Obsolete active KB references: " + " | ".join(active_hits[:10])) if active_hits else ok("No obsolete provider-rotation/vault references outside explicit historical provenance")


def check_hindsight_obsolete() -> Result:
    bad = []
    for term in ("hermes-provider-rotation", "nvidia fallback", "/root/.hermes/workspaces", "/root/memory/knowledge_base/vault"):
        offset = 0
        current = 0
        while True:
            payload = http_json("http://127.0.0.1:8888/v1/default/banks/hermes/memories/list?" + urlencode({"q": term, "state": "valid", "limit": 100, "offset": offset}))
            items = payload.get('items')
            total = int(payload.get('total') or 0)
            if not isinstance(items, list) or (not items and offset < total):
                return fail(f"Cannot inspect Hindsight facts for {term}: incomplete response")
            # Experiences record what happened, including retired paths and
            # their removal. They are provenance, not assertions of current
            # configuration; do not invalidate history to silence the audit.
            current += sum(item.get('fact_type') != 'experience' for item in items)
            offset += len(items)
            if offset >= total:
                break
            if offset >= 2000:
                return fail(f"Hindsight audit needs pagination beyond 2000 facts for {term}")
        if current:
            bad.append(f"{term}:{current}")
    return fail("Obsolete valid Hindsight facts: " + ", ".join(bad)) if bad else ok("No obsolete active provider/vault/path facts in Hindsight")


def check_scripts() -> Result:
    bad = []
    for path in (ATHOS / "scripts").glob("*.sh"):
        result = run(["bash", "-n", str(path)])
        if result.returncode:
            bad.append(f"{path.name}:{result.stderr.strip()}")
    for path in (ATHOS / "scripts").glob("*.py"):
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception as exc:
            bad.append(f"{path.name}:{exc}")
    return fail("Script syntax failures: " + "; ".join(bad)) if bad else ok("Athos shell and Python operational scripts pass syntax validation")


def check_time() -> Result:
    result = run(["timedatectl", "show", "--property=Timezone", "--value"])
    timezone_name = result.stdout.strip()
    year = datetime.now().year
    if timezone_name != "America/Sao_Paulo" or not 2026 <= year <= 2100:
        return fail(f"Host clock configuration unexpected: timezone={timezone_name!r}, year={year}")
    return ok("Host clock is plausible and timezone is America/Sao_Paulo")


def check_hermes_skills() -> Result:
    """Validate local skill contracts against the current ecosystem model."""
    # Archived skills (skills/.archive/, curator or manual) are retired on purpose.
    skill_files = sorted(p for p in (HERMES / "profiles").glob("*/skills/**/SKILL.md") if "/.archive/" not in str(p))
    invalid_frontmatter = []
    for path in skill_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        if not lines or lines[0].strip() != "---" or "---" not in [line.strip() for line in lines[1:100]]:
            invalid_frontmatter.append(str(path))

    obsolete = []
    retired_names = ("hermes-dashboard-ops", "local-proxy-service", "cron-boot-sync")
    for name in retired_names:
        path = ATHOS / "skills/devops" / name / "SKILL.md"
        if path.exists():
            obsolete.append(str(path))

    stale = []
    governed = {
        ATHOS / "skills/devops/hermes-profile-config/SKILL.md": (
            "fallback_providers", "provider_groups", "provider: openrouter", "provider: nvidia"
        ),
        ATHOS / "skills/devops/hermes-cron-management/SKILL.md": (
            "/root/memory/foundation/scripts", "/root/.hermes/services/crons", "wrap_cron_job.sh"
        ),
        ATHOS / "skills/devops/cron-refactor/SKILL.md": (
            "/root/memory/foundation/scripts", "/root/.hermes/services/crons"
        ),
    }
    for path, patterns in governed.items():
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        hits = [pattern for pattern in patterns if pattern.lower() in text]
        if hits:
            stale.append(f"{path}:{','.join(hits)}")

    if invalid_frontmatter or obsolete or stale:
        return fail(
            "Skill governance drift: "
            f"invalid_frontmatter={invalid_frontmatter[:10]}; "
            f"obsolete={obsolete}; stale_contracts={stale}"
        )
    unique_hashes = len({__import__("hashlib").sha256(path.read_bytes()).hexdigest() for path in skill_files})
    return ok(f"Hermes skills valid: files={len(skill_files)}, unique_contents={unique_hashes}, no obsolete ecosystem contracts")


def check_agent_profile(profile: str) -> Result:
    result = run(
        ["python3", str(ATHOS / "scripts/validate_agent_profiles.py"), "--profile", profile],
        timeout=30,
    )
    output = (result.stdout + result.stderr).strip()
    return ok(output) if result.returncode == 0 else fail(output)


def check_disk_cleanup() -> Result:
    cleanup_path = ATHOS / "scripts/create_trash_cleanup_task.sh"
    repair_path = ATHOS / "scripts/repair_ecosystem_cleanup.sh"
    cleanup = cleanup_path.read_text(errors="replace") if cleanup_path.is_file() else ""
    required = (
        "docker builder prune --all --force",
        "journalctl --vacuum-time=14d --vacuum-size=200M",
        "systemd-tmpfiles --clean",
        "forgehub-auditor-before-*.dump",
        "hermes-backup-*.tar.gz",
        "-mindepth 2 -maxdepth 2",
        "state-snapshots",
        ".curator_backups",
    )
    missing = [item for item in required if item not in cleanup]
    if not repair_path.is_file() or not os.access(repair_path, os.X_OK):
        missing.append("executable cleanup self-repair script is missing")
    if re.search(r"docker\s+volume\s+prune|docker\s+system\s+prune[^\n]*--volumes", cleanup):
        missing.append("unsafe Docker volume-prune command must be absent")

    logrotate_path = Path("/etc/logrotate.d/hermes-ecosystem")
    logrotate_text = logrotate_path.read_text(errors="replace") if logrotate_path.is_file() else ""
    for marker in ("profiles/*/logs/*.log", "profiles/*/cron/logs/*.log", "rotate 14", "maxsize 10M"):
        if marker not in logrotate_text:
            missing.append(f"logrotate:{marker}")

    try:
        daemon = json.loads(Path("/etc/docker/daemon.json").read_text())
        options = daemon.get("log-opts") or {}
        if options.get("max-size") != "10m" or options.get("max-file") != "3":
            missing.append("Docker json-file rotation is not 10m x 3")
    except Exception as exc:
        missing.append(f"invalid Docker daemon log policy: {exc}")

    ecosystem_containers = (
        "forgehub-backend", "forgehub-frontend", "hindsight", "forgerouter",
        "hindsight_postgres", "forgehub_postgres", "forgerouter_postgres",
    )
    for container in ecosystem_containers:
        inspected = run([
            "docker", "inspect", container, "--format",
            "{{index .HostConfig.LogConfig.Config \"max-size\"}}|{{index .HostConfig.LogConfig.Config \"max-file\"}}",
        ])
        if inspected.returncode or inspected.stdout.strip() != "10m|3":
            missing.append(f"container log rotation drift: {container}")

    jobs = [job for job in load_jobs() if job.get("enabled") and job.get("name") == "foundation-clear"]
    if len(jobs) != 1 or jobs[0].get("schedule", {}).get("expr") != "0 21 * * 0" or jobs[0].get("script") != cleanup_path.name:
        missing.append(f"weekly cleanup job drift: {jobs}")

    for timer in ("logrotate.timer", "systemd-tmpfiles-clean.timer"):
        if run(["systemctl", "is-active", "--quiet", timer]).returncode:
            missing.append(f"inactive timer: {timer}")

    system_control = Path("/root/project/forgehub/backend/app/api/routes/system_control.py")
    system_control_text = system_control.read_text(errors="replace") if system_control.is_file() else ""
    if "CLEANUP_SCRIPT" not in system_control_text or str(cleanup_path) not in system_control_text:
        missing.append("ForgeHub System Control is not invoking the Athos cleanup script")
    if '@router.post("/cleanup-empty-trash")' in system_control_text or "def _move_command(" in system_control_text:
        missing.append("ForgeHub still contains a redundant cleanup execution path")

    if missing:
        return fail("Disk cleanup policy drift: " + "; ".join(missing))

    system_df = run(["docker", "system", "df", "--format", "{{json .}}"], timeout=30)
    build_cache = "unknown"
    for line in system_df.stdout.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("Type") == "Build Cache":
            build_cache = row.get("Size", "unknown")
    return ok(
        "Weekly disk cleanup valid: all inactive Docker build cache, temp rules, journal 14d/200M, "
        f"logs 10M x14, manual backups 30d, one UI/cron engine, protected volumes; current build_cache={build_cache}"
    )


def check_telegram_voice_runtime() -> Result:
    result = run(
        ["python3", str(ATHOS / "scripts/voice_runtime_audit.py"), "--channel", "telegram"],
        timeout=150,
    )
    output = (result.stdout + result.stderr).strip()
    return ok(output) if result.returncode == 0 else fail(output)


def check_cli_voice_runtime() -> Result:
    result = run(
        [
            "python3", str(ATHOS / "scripts/voice_runtime_audit.py"),
            "--channel", "cli", "--skip-tts-probe",
        ],
        timeout=45,
    )
    output = (result.stdout + result.stderr).strip()
    return ok(output) if result.returncode == 0 else fail(output)


# Catalogue v2 additions. These controls read state and never repair it.
APPLICATIONS = ("forgehub", "forgerouter", "hindsight", "forgevault", "darckware", "coreti")
APPLICATION_POSTGRES = ("forgehub_postgres", "hindsight_postgres", "forgerouter_postgres", "forgevault-postgres-1", "darckware-postgres", "coreti_postgres", "saedas_postgres")


def _compose_path(app: str) -> Path:
    if app == "hindsight":
        return Path("/root/memory/hindsight/docker-compose.yml")
    return Path(f"/root/project/{app}/docker-compose.yml")


def _healthy_containers(names: tuple[str, ...]) -> Result:
    problems = []
    for name in names:
        result = run(["docker", "inspect", name, "--format", "{{json .State}}"])
        if result.returncode:
            problems.append(f"{name}: missing")
            continue
        state = json.loads(result.stdout)
        health = (state.get("Health") or {}).get("Status", "none")
        if state.get("Status") != "running" or health not in ("none", "healthy"):
            problems.append(f"{name}: {state.get('Status')}/{health}")
    return fail("; ".join(problems)) if problems else ok(f"{len(names)} containers running with healthy status")


def _url_status(url: str, *, expected: tuple[int, ...] = (200,)) -> Result:
    result = run(["curl", "-L", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "12", url], timeout=16)
    try:
        status = int(result.stdout.strip()[-3:])
    except ValueError:
        status = 0
    return ok(f"{url}: HTTP {status}") if result.returncode == 0 and status in expected else fail(f"{url}: HTTP {status}; {result.stderr.strip()[:200]}")


def check_registered_agents() -> Result:
    profiles = [p.name for p in (HERMES / "profiles").iterdir() if p.is_dir() and p.name != "default" and not (p / "gateway.parked").exists()]
    rows = psql("SELECT lower(coalesce(profile_slug,'')) || '|' || lower(coalesce(runtime_type,'')) FROM company.agents WHERE is_active", "forgehub", "forgehub_postgres")
    registrations = dict(row.split("|", 1) for row in rows.splitlines() if "|" in row)
    missing = [name for name in profiles if registrations.get(name) != "hermes"]
    missing += [
        f"{name} (expected {runtime})"
        for name, runtime in EXTERNAL_RUNTIMES.items()
        if registrations.get(name) != runtime
    ]
    expected_count = len(profiles) + len(EXTERNAL_RUNTIMES)
    return fail(f"Unregistered active profiles/runtimes: {missing}") if missing else ok(
        f"{expected_count} active Hermes profiles and external runtimes registered; parked profiles ignored"
    )


def check_restart_policy() -> Result:
    names = run(["docker", "ps", "--format", "{{.Names}}"])
    if names.returncode:
        return fail(names.stderr.strip())
    bad = []
    for name in names.stdout.splitlines():
        state = run(["docker", "inspect", name, "--format", "{{.HostConfig.RestartPolicy.Name}}"])
        if state.returncode or state.stdout.strip() not in ("always", "unless-stopped"):
            bad.append(f"{name}: runtime={state.stdout.strip() or 'unknown'}")
    for app in APPLICATIONS:
        compose = _compose_path(app)
        if not compose.is_file():
            bad.append(f"{app}: missing compose")
            continue
        rendered = run(["docker", "compose", "-f", str(compose), "config", "--format", "json"], timeout=25)
        if rendered.returncode:
            bad.append(f"{app}: invalid compose")
            continue
        for service, config in json.loads(rendered.stdout).get("services", {}).items():
            if config.get("restart") not in ("always", "unless-stopped"):
                bad.append(f"{app}/{service}: compose restart={config.get('restart')}")
    return fail("Restart policy drift: " + "; ".join(bad)) if bad else ok("All running containers and Compose services use approved restart policy")


def check_postgres_dumps() -> Result:
    # Since 2026-10-20 the worker stages dumps per target and removes staging
    # after the snapshot. The abandoned whole-VPS staging directory is not
    # evidence of current backup health. A successful target run implies its
    # pg_dump commands and restic snapshot succeeded; restoration is a separate
    # control. Preserve failures even when an older successful run exists.
    raw = psql("""
        SELECT json_build_object(
            'container', t.postgres_container, 'name', t.name,
            'enabled', t.enabled, 'status', r.status,
            'snapshot_id', r.snapshot_id, 'finished_at', r.finished_at)
        FROM company.offsite_backup_targets t
        LEFT JOIN LATERAL (
            SELECT status, snapshot_id, finished_at
            FROM company.offsite_backup_runs r WHERE r.target_id=t.id
            ORDER BY r.created_at DESC LIMIT 1
        ) r ON true WHERE t.postgres_container IS NOT NULL
    """, "forgehub", "forgehub_postgres")
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    bad = []
    now = datetime.now(timezone.utc)
    for container in APPLICATION_POSTGRES:
        targets = [row for row in rows if row['container'] == container and row['enabled']]
        if not targets:
            bad.append(f"{container}: no enabled backup target")
            continue
        for row in targets:
            finished = row.get('finished_at')
            try:
                age = (now - datetime.fromisoformat(finished)).total_seconds() / 86400 if finished else None
            except (ValueError, TypeError):
                age = None
            if row.get('status') != 'ok' or not row.get('snapshot_id') or age is None or not 0 <= age <= 8:
                bad.append(f"{container}/{row['name']}: latest backup={row.get('status')}, snapshot={row.get('snapshot_id') or 'missing'}, age_days={age}")
    return fail("PostgreSQL backup gaps: " + "; ".join(bad)) if bad else ok(
        f"{len(APPLICATION_POSTGRES)} PostgreSQL containers have recent successful dump/snapshot runs; restore verification is separate"
    )



def _bridge_8910_restricted() -> bool:
    """0.0.0.0:8910 (host-bridge) is accepted only while UFW restricts it to lo / foundation_network
    (Marcelo, 2026-10-12: containers reach the bridge via host.docker.internal; loopback-only broke
    Messages from 2026-10-10 to 2026-10-12)."""
    r = run(["/usr/sbin/ufw", "status"])
    if r.returncode or "Status: active" not in r.stdout:
        return False
    rules = [line for line in r.stdout.splitlines() if line.split() and line.split()[0].startswith("8910")]
    return bool(rules) and all(("on lo" in line) or ("127.0.0.1" in line) or ("172.19.0.0/16" in line) for line in rules)

def check_public_interfaces() -> Result:
    sockets = run(["ss", "-ltnH"])
    if sockets.returncode:
        return fail(sockets.stderr.strip())
    bad = []
    for line in sockets.stdout.splitlines():
        parts = line.split()
        address = parts[3] if len(parts) > 3 else ""
        if address.startswith(("0.0.0.0:", "[::]:", "*:")):
            if address == "0.0.0.0:8910" and _bridge_8910_restricted():
                continue
            bad.append(address)
        if address.startswith("100.105.235.114:") and address.rsplit(":", 1)[-1] not in ("3000", "8020"):
            bad.append(address)
    for domain in ("forgehub.darckware.net", "forgevault.darckware.net"):
        for suffix in ("/docs", "/redoc", "/openapi.json"):
            probe = _url_status(f"https://{domain}{suffix}", expected=(401, 403, 404))
            if not probe.ok:
                bad.append(probe.notes)
    return fail("Public interface drift: " + "; ".join(bad[:20])) if bad else ok("Only approved loopback/Tailscale listeners; public API docs closed")


def check_cloudflare_vault_boundary() -> Result:
    problems = []
    if run(["systemctl", "is-active", "--quiet", "cloudflared.service"]).returncode:
        problems.append("cloudflared inactive")
    for domain in ("forgehub.darckware.net", "forgevault.darckware.net", "darckware.net"):
        probe = _url_status(f"https://{domain}/", expected=(200, 301, 302, 401, 403))
        if not probe.ok:
            problems.append(probe.notes)
    for path in ("/api/v1/secrets", "/mcp"):
        probe = _url_status(f"https://forgevault.darckware.net{path}", expected=(401, 403, 404))
        if not probe.ok:
            problems.append(probe.notes)
    return fail("Cloudflare/ForgeVault boundary: " + "; ".join(problems)) if problems else ok("Cloudflare routes respond; public ForgeVault API and MCP deny anonymous access")


def check_forgevault_services() -> Result:
    containers = _healthy_containers(("forgevault-postgres-1", "forgevault-redis-1", "forgevault-api-1", "forgevault-web-1"))
    api = _url_status("http://127.0.0.1:8080/", expected=(200,))
    return fail(f"{containers.notes}; {api.notes}") if not containers.ok or not api.ok else ok("ForgeVault API, web, PostgreSQL and Redis healthy")


def check_darckware_services() -> Result:
    site = _url_status("https://darckware.net/", expected=(200, 301, 302))
    api = _url_status("http://127.0.0.1:8020/health", expected=(200,))
    # Chat is a stateful external action; a dry public request must be explicitly
    # supported before this control can safely exercise the Lara conversation.
    return fail(f"{site.notes}; {api.notes}") if not site.ok or not api.ok else ok("Darckware site and API respond; Lara chat requires a controlled probe")


def check_coreti_services() -> Result:
    containers = _healthy_containers(("coreti_postgres", "coreti_api", "coreti_web", "coreti_nginx"))
    return containers


def check_remote_access() -> Result:
    units = ("remoto-headscale.service", "tailscaled.service")
    bad = [name for name in units if run(["systemctl", "is-active", "--quiet", name]).returncode]
    relays = _healthy_containers(("hbbs", "hbbr"))
    if not relays.ok:
        bad.append(relays.notes)
    return fail(f"Inactive remote access services: {bad}") if bad else ok("Headscale and Tailscale services plus RustDesk relay containers active")


def check_outbound_hooks() -> Result:
    bad = []
    for profile in HERMES_PROFILES:
        path = HERMES / "profiles" / profile / "config.yaml"
        content = path.read_text(errors="replace") if path.is_file() else ""
        if "/api/v1/agent-activity/events" not in content or "outbound:" not in content:
            bad.append(profile)
    return fail(f"Missing outbound Agent Activity hooks: {bad}") if bad else ok("Every active Hermes profile has outbound Agent Activity hook configuration")


def check_messages_health() -> Result:
    query = ("SELECT count(*) FILTER (WHERE dispatch_status='failed'), count(*), "
             "count(*) FILTER (WHERE dispatch_status IN ('dispatched','running') "
             "AND dispatch_deadline_at < now()) FROM company.agent_demands "
             "WHERE created_at >= now() - interval '7 days' AND dispatch_status IS NOT NULL")
    try:
        failed, total, overdue = (int(value) for value in psql(query, "forgehub", "forgehub_postgres").split("|"))
    except Exception as exc:
        return fail(f"Messages metrics unavailable: {exc}")
    ratio = failed / total if total else 0
    if ratio > .20 or overdue:
        return fail(f"Messages failure ratio {ratio:.1%} ({failed}/{total}); overdue dispatches={overdue}")
    return ok(f"Messages failure ratio {ratio:.1%} ({failed}/{total}); no overdue dispatches")


def check_external_runtimes() -> Result:
    bad = []
    for name in ("aramis", "porthus", "dartan"):
        home = HERMES / "profiles" / name
        if not home.is_dir():
            bad.append(f"{name}: missing profile")
        elif not (home / "config.yaml").is_file():
            bad.append(f"{name}: missing config")
    return fail("External runtime gaps: " + "; ".join(bad)) if bad else ok("External agent profiles configured")


def check_forgerouter_keys() -> Result:
    # The router can expose key presence but the verifier must never read or
    # print key material. A missing inventory is a failure, not a pass.
    return fail("ForgeRouter per-agent key comparison requires a non-secret inventory endpoint")


def check_hindsight_retention_timer() -> Result:
    timer = "forgehub-hindsight-retention.timer"
    if run(["systemctl", "is-active", "--quiet", timer]).returncode:
        return fail(f"{timer} inactive")
    service = run(["systemctl", "show", "forgehub-hindsight-retention.service", "--property=Result", "--value"])
    return ok("Hindsight retention timer active; last service succeeded") if service.stdout.strip() == "success" else fail(f"Hindsight retention service result={service.stdout.strip() or 'unknown'}")


def check_offsite_backup() -> Result:
    path = Path("/root/backup/offsite-staging/last_run.json")
    if not path.is_file():
        return fail("No offsite backup run status recorded")
    state = json.loads(path.read_text())
    finished = datetime.fromisoformat(state["finished_at"])
    age = (datetime.now(timezone.utc) - finished.astimezone(timezone.utc)).total_seconds() / 3600
    if state.get("result") != "ok" or not state.get("snapshot_id") or not str(state.get("check", "")).startswith("ok") or age > 36:
        return fail(f"Offsite backup not verified: result={state.get('result')}, age={age:.1f}h, check={state.get('check')}")
    return ok(f"Offsite snapshot {state['snapshot_id']} checked {age:.1f}h ago")


def check_containers_v2() -> Result:
    names = (
        "forgehub-backend", "forgehub-frontend", "forgerouter", "hindsight",
        *APPLICATION_POSTGRES, "forgevault-web-1", "forgevault-api-1",
        "forgevault-redis-1", "darckware-frontend", "darckware-backend",
        "coreti_web", "coreti_api", "coreti_nginx",
    )
    return _healthy_containers(names)


def check_endpoints_v2() -> Result:
    baseline = check_endpoints()
    extra = [
        _url_status("http://127.0.0.1:8080/", expected=(200,)),
        _url_status("https://darckware.net/", expected=(200, 301, 302)),
        _url_status("http://127.0.0.1:8020/health"),
        _url_status("https://coreti.darckware.net/", expected=(200, 301, 302, 401, 403)),
    ]
    bad = [part.notes for part in [baseline, *extra] if not part.ok]
    return fail("; ".join(bad)) if bad else ok("All six ecosystem application endpoints respond")


def check_postgres_v2() -> Result:
    bad = [name for name in APPLICATION_POSTGRES if run(["docker", "exec", name, "pg_isready", "-q"]).returncode]
    return fail(f"PostgreSQL not ready: {bad}") if bad else ok("Six application PostgreSQL instances accept connections")


def check_compose_v2() -> Result:
    bad = []
    for app in APPLICATIONS:
        compose = _compose_path(app)
        if not compose.is_file():
            bad.append(f"{app}: missing compose")
            continue
        result = run(["docker", "compose", "-f", str(compose), "config", "--quiet"], timeout=25)
        if result.returncode:
            bad.append(f"{app}: {result.stderr.strip()[:200]}")
    return fail("; ".join(bad)) if bad else ok("All six application Compose files validate")


def check_secret_modes_v2() -> Result:
    paths = [ATHOS / "config.yaml"] + [
        path for app in APPLICATIONS
        for path in _compose_path(app).parent.glob(".env*")
        if path.name == ".env" or path.name.startswith(".env.local")
    ]
    bad = []
    for path in paths:
        if not path.is_file():
            bad.append(f"{path}: missing")
        elif path.stat().st_mode & 0o077:
            bad.append(f"{path}: permissions {oct(path.stat().st_mode & 0o777)}")
    return fail("Secret file permissions: " + "; ".join(bad)) if bad else ok("All application env and Athos config files are owner-only")


def check_disk_cleanup_v2() -> Result:
    baseline = check_disk_cleanup()
    if not baseline.ok:
        return baseline
    # The maximum cache size is provisional until governance sets an exact
    # byte limit. Fail closed rather than call a descriptive 'bounded' rule green.
    return fail("Docker image/build-cache byte threshold has not been approved")



def check_shared_skills_locked() -> Result:
    """ECO-059 (2026-10-12): shared skills and the knowledge_cycle hook are immutable, match their
    manifest, and are linked into the profiles. Hermes >= v0.21.7 lets background review edit pinned
    skills, so the OS-level lock is the only protection. Logic lives in the tool itself."""
    result = run(["python3", "/root/.hermes/shared-skills/_tools/shared_skills_lock.py", "verify"], timeout=60)
    notes = (result.stdout or result.stderr).strip() or f"verify exited {result.returncode}"
    return ok(notes) if result.returncode == 0 else fail(notes + " — unlock/edit/lock: /root/.hermes/shared-skills/_tools/shared_skills_lock.py")

CHECKS = {
    "ECO-001": check_docs,
    "ECO-002": check_foundation_boundary,
    "ECO-003": check_kb_layout,
    "ECO-004": check_profiles,
    "ECO-005": check_gateways,
    "ECO-006": check_support_services,
    "ECO-007": check_containers_v2,
    "ECO-008": check_network,
    "ECO-009": check_endpoints_v2,
    "ECO-010": check_postgres_v2,
    "ECO-011": check_schema_topology,
    "ECO-012": check_hindsight_functions,
    "ECO-013": check_hindsight_pipeline,
    "ECO-014": check_hindsight_logs,
    "ECO-015": check_forgerouter,
    "ECO-016": check_kb_mount,
    "ECO-017": check_compose_v2,
    "ECO-018": check_capacity,
    "ECO-019": check_secret_modes_v2,
    "ECO-020": check_cron_heartbeat,
    "ECO-022": check_cron_status,
    "ECO-023": check_weekly_audit,
    "ECO-024": check_backup,
    "ECO-025": check_audit_tables,
    "ECO-026": check_kb_obsolete,
    "ECO-027": check_hindsight_obsolete,
    "ECO-028": check_scripts,
    "ECO-029": check_time,
    "ECO-030": check_hermes_skills,
    "ECO-031": lambda: check_agent_profile("athos"),
    "ECO-032": lambda: check_agent_profile("aegis"),
    "ECO-033": lambda: check_agent_profile("daedalus"),
    "ECO-034": lambda: check_agent_profile("hephaestus"),
    "ECO-035": lambda: check_agent_profile("atlas"),
    "ECO-036": lambda: check_agent_profile("mnemosyne"),
    "ECO-037": lambda: check_agent_profile("scriba"),
    "ECO-038": lambda: check_agent_profile("themis"),
    "ECO-039": check_disk_cleanup_v2,
    "ECO-040": check_telegram_voice_runtime,
    "ECO-041": check_cli_voice_runtime,
    "ECO-042": lambda: check_agent_profile("kairos"),
    "ECO-043": lambda: check_agent_profile("lara"),
    "ECO-044": check_registered_agents,
    "ECO-045": check_restart_policy,
    "ECO-046": check_postgres_dumps,
    "ECO-047": check_public_interfaces,
    "ECO-048": check_cloudflare_vault_boundary,
    "ECO-049": check_forgevault_services,
    "ECO-050": check_darckware_services,
    "ECO-051": check_coreti_services,
    "ECO-052": check_remote_access,
    "ECO-053": check_outbound_hooks,
    "ECO-054": check_messages_health,
    "ECO-055": check_external_runtimes,
    "ECO-056": check_forgerouter_keys,
    "ECO-057": check_hindsight_retention_timer,
    "ECO-058": check_offsite_backup,
    "ECO-059": check_shared_skills_locked,
}


def active_items() -> list[tuple[int, str, str]]:
    rows = psql("SELECT id, item_description, coalesce(category,'') FROM audit.foundation_checklist WHERE status NOT IN ('retired','disabled') ORDER BY id;")
    return [(int(parts[0]), parts[1], parts[2]) for line in rows.splitlines() if line for parts in [line.split("|", 2)]]


def record(item_id: int, result: Result) -> None:
    notes = result.notes.replace("'", "''")
    state = "OK" if result.ok else "FAIL"
    psql(
        f"INSERT INTO audit.foundation_checklist_log(checklist_item_id,verified_at,result,notes) VALUES ({item_id},NOW(),'{state}','{notes}');"
        f"UPDATE audit.foundation_checklist SET status='{state.lower()}',last_checked=NOW(),last_result='{notes}',check_interval='weekly' WHERE id={item_id};"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", choices=sorted(CHECKS), help="run and persist one control only")
    args = parser.parse_args()
    failures: list[tuple[str, str, str]] = []
    items = active_items()
    if args.check:
        items = [item for item in items if item[1].startswith(f"[{args.check}]")]
    if not items:
        print(f"No active ecosystem checklist item found{f' for {args.check}' if args.check else ''}", file=sys.stderr)
        return 1
    for item_id, description, _category in items:
        match = re.match(r"\[(ECO-\d{3})]", description)
        key = match.group(1) if match else ""
        check = CHECKS.get(key)
        try:
            result = check() if check else fail(f"No implementation registered for checklist key {key or description}")
        except Exception as exc:
            result = fail(f"Unhandled check error: {type(exc).__name__}: {exc}")
        record(item_id, result)
        if args.check:
            print(result.notes)
        if not result.ok:
            failures.append((key or str(item_id), description, result.notes))
    psql("DELETE FROM audit.foundation_checklist_log WHERE verified_at < NOW() - interval '180 days';")
    if failures:
        print("# Auditoria semanal do ecossistema — FALHA")
        print(f"\nTimestamp: {datetime.now(timezone.utc).isoformat()}\n")
        for key, description, notes in failures:
            print(f"- **{key}** {description}: {notes}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

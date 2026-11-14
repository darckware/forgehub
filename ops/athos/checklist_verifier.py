#!/usr/bin/env python3
"""Weekly, read-only ecosystem checklist with PostgreSQL audit evidence.

The active checklist is stored in ``audit.foundation_checklist``. Each active
description starts with a stable ``[ECO-NNN]`` key; this avoids coupling check
logic to translated prose. Retired rows and their historical logs are kept.
"""

from __future__ import annotations

import ast
import argparse
import ipaddress
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import urlopen

FOUNDATION = Path("/root/memory/foundation")
HERMES = Path("/root/.hermes")
ATHOS = HERMES / "profiles/athos"
KB = Path("/root/memory/knowledge_base")  # /root/.hermes/knowledge_base is a legacy symlink
FORGEHUB = Path("/root/project/forgehub")
FORGEROUTER = Path("/root/project/forgerouter")
CATALOG_SOURCE = Path(__file__).resolve().parents[2] / "backend/app/core/audit_catalog.py"
if not CATALOG_SOURCE.is_file():
    CATALOG_SOURCE = FORGEHUB / "backend/app/core/audit_catalog.py"
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


AUDIT_ROUTINE_SCHEDULES = {
    "daily": "0 19 * * *",
    "weekly": "0 19 * * 0",
    "monthly": "0 19 1 * *",
    "quarterly": "0 19 1 1,4,7,10 *",
}


# One period plus a day of grace: a tier must have completed a run within
# this window, counted from its last completed run or from when it was enabled.
AUDIT_ROUTINE_WINDOWS_DAYS = {"daily": 2, "weekly": 8, "monthly": 32, "quarterly": 93}

# Completion alone is not evidence. Check the batch's coverage, including
# failing controls (a complete audit can correctly report failures).
AUDIT_ROUTINE_INVENTORY_QUERY = """
SELECT coalesce(json_agg(json_build_object(
 'frequency',r.audit_frequency,'schedule',r.schedule,'timezone',r.timezone,
 'enabled',r.enabled,'enabled_at',r.enabled_at,'last_completed_at',
 (SELECT max(x.finished_at) FROM company.agent_routine_runs x
 WHERE x.routine_id=r.id AND x.status='completed'
 AND x.audit_batch_id IS NOT NULL AND x.finished_at<=now()
 AND x.created_at<=x.finished_at AND x.occurrence_at<=x.finished_at
 AND ((x.evidence_received IS TRUE
   AND EXISTS (SELECT 1 FROM company.audit_checks c WHERE c.enabled AND c.frequency=r.audit_frequency)
   AND NOT EXISTS (SELECT 1 FROM company.audit_checks c
     WHERE c.enabled AND c.frequency=r.audit_frequency AND NOT EXISTS (
       SELECT 1 FROM company.audit_check_runs y WHERE y.check_id=c.id
       AND y.batch_id=x.audit_batch_id AND y.requested_by='routine'
       AND y.status IN ('ok','fail','error','timeout')
       AND y.created_at BETWEEN x.created_at AND x.finished_at)))
 OR (x.no_action IS TRUE AND x.evidence_received IS FALSE
   AND NOT EXISTS (SELECT 1 FROM company.audit_checks c WHERE c.enabled AND c.frequency=r.audit_frequency)
   AND NOT EXISTS (SELECT 1 FROM company.audit_check_runs y WHERE y.batch_id=x.audit_batch_id))
 )))), '[]'::json) FROM company.agent_routines r WHERE r.kind='audit'
"""


def _moment(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def audit_routine_problems(rows: object, now: datetime | None = None) -> list[str]:
    """Why the four Operação 24x7 audit routines don't schedule and run every
    tier (empty = they do). Pure, so it is testable without a database."""
    if not isinstance(rows, list):
        return ["malformed audit routine inventory"]
    now = now or datetime.now(timezone.utc)
    by_tier = {row.get("frequency"): row for row in rows if isinstance(row, dict)}
    if len(by_tier) != len(rows) or set(by_tier) - set(AUDIT_ROUTINE_SCHEDULES):
        return ["malformed audit routine inventory"]
    problems = []
    for frequency, schedule in AUDIT_ROUTINE_SCHEDULES.items():
        row = by_tier.get(frequency)
        if row is None:
            problems.append(f"{frequency}: no routine")
        elif row.get("enabled") is not True:
            problems.append(f"{frequency}: routine disabled")
        elif row.get("schedule") != schedule or row.get("timezone") != "America/Sao_Paulo":
            problems.append(f"{frequency}: schedule {row.get('schedule')} {row.get('timezone')}")
        else:
            window = AUDIT_ROUTINE_WINDOWS_DAYS[frequency]
            since = now.timestamp() - window * 86400
            moments = [_moment(row.get("last_completed_at")), _moment(row.get("enabled_at"))]
            if not any(moment is not None and since <= moment.timestamp() <= now.timestamp() for moment in moments):
                problems.append(f"{frequency}: no completed run in {window} days")
    return problems


def check_weekly_audit() -> Result:
    """ECO-023: every tier is scheduled -- by the four audit routines (since
    2026-11-13), each with a completed run within one period plus a day of
    grace, or, until they all are, by the legacy Sunday cron."""
    # A paused job (`hermes cron pause`, the activation plan's step) keeps
    # enabled=true in the store but no longer runs.
    jobs = [j for j in load_jobs() if j.get("enabled") and j.get("state") != "paused"
            and j.get("name") == "ecosystem-weekly-audit"]
    legacy_ok = len(jobs) == 1 and jobs[0].get("schedule", {}).get("expr") == "0 19 * * 0" and jobs[0].get("script") == "ecosystem_weekly_audit.sh"
    try:
        rows = json.loads(psql(AUDIT_ROUTINE_INVENTORY_QUERY,
            "forgehub", "forgehub_postgres"))
        problems = audit_routine_problems(rows)
    except Exception as exc:  # before the migration: no audit_frequency column
        problems = [f"audit routines unreadable: {type(exc).__name__}"]
    if not problems:
        note = "; legacy ecosystem-weekly-audit cron still enabled (disable it)" if jobs else ""
        return ok("Audit tiers scheduled and run by the four Operação 24x7 audit routines" + note)
    if legacy_ok:
        return ok("Weekly ecosystem audit scheduled Sunday 19:00 (legacy cron; audit routines: " + ", ".join(problems) + ")")
    return fail(f"No audit schedule: routines {', '.join(problems)}; legacy cron missing or drifted: {jobs}")


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
    # Parse literals only: importing backend settings would load credentials.
    values = {}
    for node in ast.parse(CATALOG_SOURCE.read_text()).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ('_CHECK_ROWS','RETIRED_AUDIT_CHECKS'):
                    values[target.id] = ast.literal_eval(node.value)
    expected_states = {row[0]:row[5] for row in values['_CHECK_ROWS']}
    expected = set(expected_states)
    retired = set(values['RETIRED_AUDIT_CHECKS'])
    if not expected or expected & retired:
        return fail("Canonical audit metadata is invalid")
    foundation = json.loads(psql("SELECT coalesce(json_agg(json_build_object('name',substring(item_description FROM '(ECO-[0-9]{3})'),'status',status)), '[]'::json) FROM audit.foundation_checklist WHERE item_description ~ 'ECO-[0-9]{3}'", 'foundation', 'hindsight_postgres'))
    company = json.loads(psql("SELECT coalesce(json_agg(json_build_object('name',name,'enabled',enabled)), '[]'::json) FROM company.audit_checks WHERE name ~ '^ECO-[0-9]{3}$'", 'forgehub', 'forgehub_postgres'))
    bad = []
    for name, rows in (('Foundation',foundation),('ForgeHub',company)):
        if not isinstance(rows,list) or any(not isinstance(row,dict) or not isinstance(row.get('name'),str) for row in rows):
            bad.append(f"{name}: malformed inventory")
            continue
        active = [row['name'] for row in rows if row['name'] not in retired]
        missing = sorted(expected-set(active))
        extra = sorted(set(active)-expected)
        if missing:
            bad.append(f"{name}: missing {','.join(missing)}")
        if extra:
            bad.append(f"{name}: unknown {','.join(extra)}")
        if len(active) != len(set(active)):
            bad.append(f"{name}: duplicate controls")
        for row in rows:
            key = row['name']
            if key not in expected and key not in retired:
                continue
            required_enabled = expected_states.get(key,False)
            if name == 'ForgeHub':
                matches = type(row.get('enabled')) is bool and row['enabled'] is required_enabled
            else:
                state = row.get('status')
                matches = (state in ('ok','fail','pending','active','new','unverified') if required_enabled
                           else state in ('disabled','retired'))
            if not matches:
                bad.append(f"{name}/{key}: activation mismatch")
    return fail('; '.join(bad)) if bad else ok(f"Foundation and ForgeHub contain all {len(expected)} canonical checks; retired history preserved")


def check_kb_obsolete() -> Result:
    result = run(["rg", "-n", "-i", "hermes-provider-rotation|fallback_providers|knowledge_base/vault|provider_groups", str(KB)])
    historical = ("/inventory/", "decisions/2026-06-25-vault-decommission.md")  # file and its INDEX link
    active_hits = [line for line in result.stdout.splitlines() if not any(marker in line for marker in historical)]
    return fail("Obsolete active KB references: " + " | ".join(active_hits[:10])) if active_hits else ok("No obsolete provider-rotation/vault references outside explicit historical provenance")


_RETIRED_WORDS = r"(?:obsolet\w*|legad\w*|legacy|aposentad\w*|descontinuad\w*|retired|deprecated)"


def _describes_retirement(item: dict, term: str) -> bool:
    """True only when the sentence ties a retirement word to the term itself: "migrou de <term>",
    "referência obsoleta <term>", "<term> (legado)". A bare word elsewhere never counts."""
    text = str(item.get('text') or item.get('content') or '').lower()
    t = r"[`'\"]?" + re.escape(term.lower()) + r"[`'\"]?"
    patterns = (
        rf"migr\w*\s+(?:de|from)\s+{t}",
        rf"{_RETIRED_WORDS}\s+{t}",
        rf"{t}\s*[(,:-]?\s*(?:é\s+|is\s+|está\s+)?{_RETIRED_WORDS}",
    )
    return any(re.search(p, text) for p in patterns)


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
            # A fact that names the term only to say it is obsolete or migrated is not an
            # assertion of current configuration either (2026-11-13: the record of each fix
            # kept this check red forever).
            current += sum(item.get('fact_type') != 'experience' and not _describes_retirement(item, term)
                           for item in items)
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


# One versioned production inventory. Profile installations use the release
# manifest in ForgeHub; source/test imports use their neighboring manifest.
TARGET_MANIFEST = Path(__file__).with_name("audit_targets.json")
if not TARGET_MANIFEST.is_file():
    TARGET_MANIFEST = FORGEHUB / "ops/athos/audit_targets.json"

# Coverage is fail-closed for the known production application set. New targets
# may be added, but removing a known system cannot silently make it unaudited.
REQUIRED_APPLICATIONS = frozenset({
    'forgehub', 'forgerouter', 'hindsight', 'forgevault',
    'darckware', 'coreti', 'saedas', 'filenest',
})


def validate_target_manifest(data: dict) -> list[dict]:
    if not isinstance(data, dict) or set(data) != {'schema_version','applications'} or data['schema_version'] != 1:
        raise ValueError("Unsupported application manifest")
    targets = data['applications']
    if not isinstance(targets, list) or not targets:
        raise ValueError("Application inventory is empty")
    names, containers = set(), set()
    for target in targets:
        if not isinstance(target, dict) or set(target) != {'name','owner','compose','containers','postgres','endpoints'}:
            raise ValueError("Incomplete application target")
        if any(not isinstance(target[key], str) or not target[key] for key in ('name','owner','compose')):
            raise ValueError("Target identity or owner missing")
        compose = Path(target['compose'])
        if target['name'] in names or not compose.is_absolute() or '..' in compose.parts or 'test-env' in compose.parts:
            raise ValueError("Duplicate or non-production application target")
        names.add(target['name'])
        for key in ('containers','postgres','endpoints'):
            if not isinstance(target[key], list) or not target[key]:
                raise ValueError("Target coverage is incomplete")
        for name in target['containers']:
            if not isinstance(name, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]*', name) or name in containers or re.search(r'(^|[_-])(test|homologation|homolog)([_-]|$)',name):
                raise ValueError("Duplicate, invalid or test container in production inventory")
            containers.add(name)
        if any(name not in target['containers'] for name in target['postgres']):
            raise ValueError("PostgreSQL target must be covered as a container")
        for endpoint in target['endpoints']:
            if not isinstance(endpoint, dict) or set(endpoint) != {'url','expected'}:
                raise ValueError("Invalid endpoint definition")
            url = urlsplit(endpoint['url'])
            if url.scheme not in ('http','https') or not url.hostname or url.username is not None or url.password is not None or url.query or url.fragment:
                raise ValueError("Endpoint must be an unauthenticated URL without credentials")
            if not isinstance(endpoint['expected'], list) or not endpoint['expected'] or any(type(code) is not int or not 100<=code<=599 for code in endpoint['expected']):
                raise ValueError("Invalid HTTP status contract")
    missing = REQUIRED_APPLICATIONS - names
    if missing:
        raise ValueError(f"Required application coverage is missing: {', '.join(sorted(missing))}")
    return targets


def application_targets() -> list[dict]:
    return validate_target_manifest(json.loads(TARGET_MANIFEST.read_text()))


def application_postgres() -> tuple[str, ...]:
    return tuple(name for target in application_targets() for name in target['postgres'])


def _compose_path(app: str) -> Path:
    return Path(next(target['compose'] for target in application_targets() if target['name'] == app))


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
    for app in (target['name'] for target in application_targets()):
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
    for container in application_postgres():
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
        f"{len(application_postgres())} PostgreSQL containers have recent successful dump/snapshot runs; restore verification is separate"
    )



def _bridge_8910_restricted() -> bool:
    """0.0.0.0:8910 (host-bridge) is accepted only while UFW restricts it to lo / foundation_network
    (Marcelo, 2026-10-12: containers reach the bridge via host.docker.internal; loopback-only broke
    Messages from 2026-10-10 to 2026-10-12)."""
    # UFW invokes sysctl via PATH for verbose status. Keep this read-only probe
    # usable in external runtimes whose PATH omits sbin.
    r = run(["/usr/bin/env", f"PATH={os.environ.get('PATH', '')}:/usr/sbin:/sbin",
             "LC_ALL=C", "/usr/sbin/ufw", "status", "verbose"])
    if (r.returncode or "Status: active" not in r.stdout
            or not re.search(r"Default: (?:deny|reject) \(incoming\)", r.stdout)):
        return False
    restricted_allow = False
    for line in r.stdout.splitlines():
        # Comments are not evidence of source restrictions.
        columns = re.split(r"\s{2,}", line.split("#", 1)[0].strip())
        if len(columns) != 3:
            continue
        target, action, source = columns
        if action != "ALLOW IN":
            continue
        port = target.split()[0].split("/", 1)[0]
        if target.split()[0].endswith("/udp"):
            continue  # The exception is for a TCP listener.
        # Ranges, all-port rules and unknown application profiles may also
        # admit 8910. Fail closed for a profile we cannot resolve here.
        covers_bridge = not re.fullmatch(r"[0-9:,]+", port)
        if not covers_bridge:
            for entry in port.split(","):
                bounds = entry.split(":")
                covers_bridge |= int(bounds[0]) <= 8910 <= int(bounds[-1])
        if not covers_bridge:
            continue
        if not (re.search(r"\bon lo$", target)
                or source in ("127.0.0.1", "172.19.0.0/16")):
            return False
        restricted_allow = True
    return restricted_allow


TAILSCALE_NETWORKS = (ipaddress.ip_network("100.64.0.0/10"), ipaddress.ip_network("fd7a:115c:a1e0::/48"))


def _approved_tailnet_listener(address: str, line: str) -> bool:
    """Infrastructure exceptions require socket owners, never just a port."""
    port = address.rsplit(":", 1)[-1]
    owners = set(re.findall(r'\("([^"]+)",pid=\d+,fd=\d+\)', line))
    if owners == {"tailscaled"}:
        return True  # Peer API TCP port is dynamically assigned by Tailscale.
    if port == "22" and owners and owners <= {"sshd", "systemd"}:
        return True  # OpenSSH may share its activation socket with systemd.
    if port in ("21115", "21116", "21117") and owners == {"docker-proxy"}:
        return True  # RustDesk bridge publications, exclusively on this node's IP.
    return port in ("3000", "8020") and owners == {"docker-proxy"}


def _listener_findings(ss_output: str, bridge_restricted: bool) -> list[str]:
    """Classify `ss -ltnpH` rows; return one diagnostic per unauthorized TCP listener."""
    findings = []
    for line in ss_output.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        address = parts[3]
        owners = re.findall(r'\("([^"]+)",pid=(\d+)', line)
        processes = ",".join(f"{name}[{pid}]" for name, pid in owners) or "unknown"
        host, _, port = address.rpartition(":")
        host = host.split("%", 1)[0].strip("[]")
        label = f"tcp {address} process={processes}"
        try:
            # Normalize mapped addresses before applying any address classification.
            ip = ipaddress.ip_address("0.0.0.0" if host == "*" else host)
            native_ipv4 = isinstance(ip, ipaddress.IPv4Address)
            if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
                ip = ip.ipv4_mapped
            port_number = int(port)
        except ValueError:
            findings.append(f"{label}: unparseable listener")
            continue
        if ip.is_unspecified:
            # This exception is for the exact IPv4 bind, never IPv6/mapped aliases.
            if address == "0.0.0.0:8910" and bridge_restricted:
                continue
            findings.append(f"{label}: wildcard bind, no authorized baseline")
            continue
        if ip.is_loopback:
            continue
        if any(ip in network for network in TAILSCALE_NETWORKS):
            if native_ipv4 and str(ip) == "100.105.235.114" and _approved_tailnet_listener(f"{ip}:{port_number}", line):
                continue
            # Tailscale's own peer API also binds this node's tailnet IPv6 on a port it picks at
            # start-up (Marcelo, 2026-11-13). Only tailscaled, only this node's exact IPv6.
            if (str(ip) == "fd7a:115c:a1e0::2501:ebce"
                    and set(re.findall(r'\("([^"]+)",pid=\d+,fd=\d+\)', line)) == {"tailscaled"}):
                continue
            findings.append(f"{label}: Tailscale bind, no authorized baseline for address/owner")
            continue
        if ip.is_global:
            findings.append(f"{label}: public address bind, no authorized baseline")
    return findings


def check_public_interfaces() -> Result:
    sockets = run(["ss", "-ltnpH"])
    if sockets.returncode:
        return fail(sockets.stderr.strip())
    bad = _listener_findings(sockets.stdout, _bridge_8910_restricted())
    for domain in ("forgehub.darckware.net", "forgevault.darckware.net", "darckware.net"):
        for suffix in ("/docs", "/redoc", "/openapi.json"):
            probe = _url_status(f"https://{domain}{suffix}", expected=(401, 403, 404))
            if not probe.ok:
                bad.append(probe.notes)
    addresses = []
    for raw in run(["hostname", "-I"]).stdout.split():
        try:
            addresses.append(ipaddress.ip_address(raw))
        except ValueError:
            continue
    tailscale = [str(a) for a in addresses if any(a in n for n in TAILSCALE_NETWORKS)]
    public = [str(a) for a in addresses if a.is_global and str(a) not in tailscale]
    def context_value(value: str) -> str:
        return value if len(value) <= 250 else value[:247] + "..."

    context = (
        f"host={context_value(run(['hostname', '-f']).stdout.strip() or 'unknown')} "
        f"public={context_value(','.join(public) or 'none')} "
        f"tailscale={context_value(','.join(tailscale) or 'none')}; "
        "evidence: local `ss -ltnpH` (TCP only) + HTTPS probes"
    )
    reachability = "external reachability NOT verified (local listener presence only; UFW evaluated only for 8910; nft not evaluated)"
    if bad:
        # Reserve metadata first; fail() must never cut a finding or the disclaimer.
        prefix = f"Public interface drift ({len(bad)}) [{context}]. {reachability}: "
        suffix_budget = len(f"; {len(bad)} findings omitted")
        details = []
        used = len(prefix) + suffix_budget
        for finding in bad[:20]:
            needed = len(finding) + (2 if details else 0)
            if used + needed > 4000:
                break
            details.append(finding)
            used += needed
        omitted = len(bad) - len(details)
        suffix = f"; {omitted} findings omitted" if omitted else ""
        return fail(prefix + "; ".join(details) + suffix)
    return ok(f"Only authorized loopback/Tailscale TCP listeners; public API docs closed [{context}]. {reachability}")


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


# Metadata only: these queries never read profile configuration or credential values.
MESSAGES_QUEUE_SLA_MINUTES = 15
MESSAGES_FEEDBACK_SLA_MINUTES = 15
ACTIVITY_DELIVERY_SLA_MINUTES = 5


def _metadata_counts(query: str, fields: tuple[str, ...]) -> dict[str, int]:
    data = json.loads(psql(query, "forgehub", "forgehub_postgres"))
    if not isinstance(data, dict) or any(type(data.get(field)) is not int or data[field] < 0 for field in fields):
        raise ValueError("Missing or invalid aggregate metadata")
    return data


def check_outbound_hooks() -> Result:
    # Only the signed webhook receiver writes these metadata events. An idle
    # profile proves neither a broken hook nor a working hook; report it as idle.
    query = f"""
        WITH active AS (
            SELECT id FROM company.agents
            WHERE is_active AND status='active' AND runtime_type='hermes'
        ), executed AS (
            SELECT d.target_agent_id, d.dispatched_at
            FROM company.agent_demands d JOIN active a ON a.id=d.target_agent_id
            WHERE d.dispatched_at BETWEEN now()-interval '24 hours'
                AND now()-interval '{ACTIVITY_DELIVERY_SLA_MINUTES} minutes'
              AND d.dispatch_status IN ('dispatched','running','completed','failed')
        ), missing AS (
            SELECT d.target_agent_id FROM executed d WHERE NOT EXISTS (
                SELECT 1 FROM company.agent_activity_events e
                WHERE e.agent_id=d.target_agent_id AND e.runtime='hermes'
                  AND e.kind IN ('turn_started','session_started')
                  AND e.created_at BETWEEN d.dispatched_at-interval '15 seconds'
                      AND d.dispatched_at+interval '{ACTIVITY_DELIVERY_SLA_MINUTES} minutes'
            )
        )
        SELECT json_build_object(
            'active_profiles', (SELECT count(*) FROM active),
            'recently_executed', (SELECT count(DISTINCT target_agent_id) FROM executed),
            'missing_delivery', (SELECT count(DISTINCT target_agent_id) FROM missing))
    """
    try:
        data = _metadata_counts(query, ('active_profiles','recently_executed','missing_delivery'))
        if not data['active_profiles'] or not 0 <= data['missing_delivery'] <= data['recently_executed'] <= data['active_profiles']:
            return fail("Activity delivery inventory unavailable or inconsistent")
    except (ValueError, KeyError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        return fail(f"Activity delivery metadata unavailable ({type(exc).__name__})")
    notes = (f"Authenticated Activity deliveries: active={data['active_profiles']}, "
             f"executed={data['recently_executed']}, missing_delivery={data['missing_delivery']}, "
             f"idle={data['active_profiles']-data['recently_executed']} (no recent Messages run; other channels unverified)")
    return fail(notes) if data['missing_delivery'] else ok(notes)


def check_messages_health() -> Result:
    # The seven-day limit applies to the historical rate only. Outstanding
    # dispatch/deadline/feedback obligations are never excluded by creation age.
    # A checked queue may legitimately wait on dependencies, capacity or quota;
    # the dispatcher records executor_wait_checked_at without editing content.
    query = f"""
        SELECT json_build_object(
          'total', count(*) FILTER (WHERE created_at>=now()-interval '7 days' AND dispatch_status IS NOT NULL),
          'failed', count(*) FILTER (WHERE created_at>=now()-interval '7 days' AND dispatch_status='failed'),
          'overdue', count(*) FILTER (WHERE dispatch_status IN ('dispatched','running') AND dispatch_deadline_at<now()),
          'missing_deadlines', count(*) FILTER (WHERE dispatch_status IN ('dispatched','running') AND dispatch_deadline_at IS NULL),
          'queued_due', count(*) FILTER (WHERE origin_type='task' AND status<>'archived' AND consolidated_into_id IS NULL
              AND dispatch_status IS NULL AND agent_run_id IS NULL AND target_agent_id IS NOT NULL AND scheduled_at<=now()),
          'unchecked_due', count(*) FILTER (WHERE origin_type='task' AND status<>'archived' AND consolidated_into_id IS NULL
              AND dispatch_status IS NULL AND agent_run_id IS NULL AND target_agent_id IS NOT NULL
              AND scheduled_at<now()-interval '{MESSAGES_QUEUE_SLA_MINUTES} minutes'
              AND (executor_wait_checked_at IS NULL OR executor_wait_checked_at<now()-interval '{MESSAGES_QUEUE_SLA_MINUTES} minutes')),
          'feedback_overdue', count(*) FILTER (WHERE status<>'archived' AND consolidated_into_id IS NULL
              AND dispatch_status IN ('completed','failed') AND feedback_sent_at IS NULL
              AND updated_at<now()-interval '{MESSAGES_FEEDBACK_SLA_MINUTES} minutes'
              AND (channel IS DISTINCT FROM 'agent' OR (dispatch_status='failed' AND from_agent_id IS NOT NULL)))
        ) FROM company.agent_demands
    """
    fields = ('total','failed','overdue','missing_deadlines','queued_due','unchecked_due','feedback_overdue')
    try:
        data = _metadata_counts(query, fields)
        if data['failed'] > data['total'] or data['unchecked_due'] > data['queued_due']:
            return fail("Messages aggregate metadata unavailable: inconsistent counts")
    except (ValueError, KeyError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        return fail(f"Messages aggregate metadata unavailable ({type(exc).__name__})")
    ratio = data['failed']/data['total'] if data['total'] else 0
    notes = (f"Messages failure ratio {ratio:.1%} ({data['failed']}/{data['total']}); "
             + ', '.join(f"{field}={data[field]}" for field in fields[2:]))
    return fail(notes) if ratio > .20 or any(data[field] for field in ('overdue','missing_deadlines','unchecked_due','feedback_overdue')) else ok(notes)


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
    return _healthy_containers(tuple(name for target in application_targets() for name in target['containers']))


def check_endpoints_v2() -> Result:
    baseline = check_endpoints()  # Preserve the existing JSON health contract.
    results = [baseline]
    targets = application_targets()
    for target in targets:
        for endpoint in target['endpoints']:
            results.append(_url_status(endpoint['url'], expected=tuple(endpoint['expected'])))
    bad = [part.notes for part in results if not part.ok]
    return fail('; '.join(bad)) if bad else ok(f"All {len(targets)} registered production application endpoints respond")


def check_postgres_v2() -> Result:
    names = application_postgres()
    bad = [name for name in names if run(["docker", "exec", name, "pg_isready", "-q"]).returncode]
    return fail(f"PostgreSQL not ready: {bad}") if bad else ok(f"{len(names)} registered application PostgreSQL instances accept connections")


def check_compose_v2() -> Result:
    bad = []
    for app in (target['name'] for target in application_targets()):
        compose = _compose_path(app)
        if not compose.is_file():
            bad.append(f"{app}: missing compose")
            continue
        result = run(["docker", "compose", "-f", str(compose), "config", "--quiet"], timeout=25)
        if result.returncode:
            bad.append(f"{app}: {result.stderr.strip()[:200]}")
    return fail("; ".join(bad)) if bad else ok(f"All {len(application_targets())} application Compose files validate")


def check_secret_modes_v2() -> Result:
    paths = [ATHOS / "config.yaml"] + [
        path for app in (target['name'] for target in application_targets())
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


# ECO-039 Docker byte limits, approved by Marcelo on 2026-11-13. Decimal bytes, the units
# `docker system df` prints. Unused images = Docker's Images "Reclaimable" figure (no
# container, running or stopped, uses them) minus the protected images the weekly prune
# never removes (recent release tags, tagged in the last 7 days, ForgeHub test env) --
# measured by prune_unused_docker_images.measure(), so check and cleanup agree.
DOCKER_BUILD_CACHE_LIMIT_BYTES = 15 * 10**9
DOCKER_UNUSED_IMAGE_LIMIT_BYTES = 10 * 10**9
# Release source first; the weekly cleanup runs the installed profile copy.
DOCKER_IMAGE_PRUNE_SCRIPT = next(
    (path for path in (Path(__file__).resolve().with_name("prune_unused_docker_images.py"),
                       ATHOS / "scripts/prune_unused_docker_images.py") if path.is_file()),
    ATHOS / "scripts/prune_unused_docker_images.py")


def _docker_image_prune_module(path: Path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("athos_docker_image_prune", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def check_disk_cleanup_v2() -> Result:
    baseline = check_disk_cleanup()
    if not baseline.ok:
        return baseline
    # The weekly cleanup must carry both bounding steps; the check never prunes itself.
    cleanup = (ATHOS / "scripts/create_trash_cleanup_task.sh").read_text(errors="replace")
    prune_text = DOCKER_IMAGE_PRUNE_SCRIPT.read_text(errors="replace") if DOCKER_IMAGE_PRUNE_SCRIPT.is_file() else ""
    missing = []
    if DOCKER_IMAGE_PRUNE_SCRIPT.name not in cleanup:
        missing.append("weekly cleanup lacks the unused-image prune step")
    if not os.access(DOCKER_IMAGE_PRUNE_SCRIPT, os.X_OK) or "UNUSED_IMAGE_LIMIT_BYTES = 10 * 10**9" not in prune_text:
        missing.append(f"{DOCKER_IMAGE_PRUNE_SCRIPT.name} missing, not executable or not at the 10 GB limit")
    # Its docker calls are argument lists: no prune, volume or force argument may appear.
    if re.search(r'"(prune|volume|--force|-f|-a|--all)"', prune_text):
        missing.append(f"{DOCKER_IMAGE_PRUNE_SCRIPT.name} contains a forbidden prune/force/volume argument")
    if missing:
        return fail("Docker cleanup incomplete: " + "; ".join(missing))
    try:
        prune = _docker_image_prune_module(DOCKER_IMAGE_PRUNE_SCRIPT)
        df = run(["docker", "system", "df", "--format", "{{json .}}"], timeout=90)
        if df.returncode:
            return fail(f"NOT VERIFIED: docker system df failed: {df.stderr.strip()[:200]}")
        rows = {row.get("Type"): row for row in map(json.loads, df.stdout.splitlines())}
        build_cache = prune.parse_size(rows["Build Cache"]["Size"])
        images = prune.measure()
    except (KeyError, ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        return fail(f"NOT VERIFIED: Docker usage unreadable ({type(exc).__name__}: {str(exc)[:200]})")
    notes = (f"Docker build cache {build_cache/1e9:.2f}GB (limit {DOCKER_BUILD_CACHE_LIMIT_BYTES/1e9:.0f}GB); "
             f"unused images {images['unused']/1e9:.2f}GB (limit {DOCKER_UNUSED_IMAGE_LIMIT_BYTES/1e9:.0f}GB; "
             f"reclaimable {images['reclaimable']/1e9:.2f}GB minus {len(images['protected'])} protected images "
             f"{images['protected_bytes']/1e9:.2f}GB); weekly cleanup has builder prune + unused-image prune")
    over = build_cache > DOCKER_BUILD_CACHE_LIMIT_BYTES or images["unused"] > DOCKER_UNUSED_IMAGE_LIMIT_BYTES
    return fail("Over approved limit: " + notes) if over else ok(notes)



def check_shared_skills_locked() -> Result:
    """ECO-059 (2026-10-12): shared skills and the knowledge_cycle hook are immutable, match their
    manifest, and are linked into the profiles. Hermes >= v0.21.7 lets background review edit pinned
    skills, so the OS-level lock is the only protection. Logic lives in the tool itself."""
    result = run(["python3", "/root/.hermes/shared-skills/_tools/shared_skills_lock.py", "verify"], timeout=60)
    notes = (result.stdout or result.stderr).strip() or f"verify exited {result.returncode}"
    return ok(notes) if result.returncode == 0 else fail(notes + " — unlock/edit/lock: /root/.hermes/shared-skills/_tools/shared_skills_lock.py")


def check_forgevault_ssh_key_reads() -> Result:
    """ECO-060 (2026-11-06, #42179): only forgehub-remote-access reads *_SSH_KEY in ForgeVault.
    Any failure to read the audit is a failure here, never a pass."""
    result = run(["python3", str(ATHOS / "scripts/forgevault_ssh_key_audit.py")], timeout=50)
    output = (result.stdout + result.stderr).strip()
    return ok(output) if result.returncode == 0 else fail(output or "NOT VERIFIED: no output from the audit")


def _knowledge_hygiene():
    """Release source first, then the copy installed next to this script."""
    import importlib.util
    candidates = (Path(__file__).resolve().with_name('knowledge_hygiene.py'),
                  FORGEHUB / 'ops/athos/knowledge_hygiene.py')
    source = next(path for path in candidates if path.is_file())
    spec = importlib.util.spec_from_file_location('athos_knowledge_hygiene', source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _findings_result(findings: list[str], passed: str) -> Result:
    if not findings:
        return ok(passed)
    shown: list[str] = []
    size = 0
    for finding in findings:          # whole findings only, within fail()'s 4000 characters
        if size + len(finding) + 2 > 3500:
            break
        shown.append(finding)
        size += len(finding) + 2
    more = f" (+{len(findings) - len(shown)} more)" if len(shown) < len(findings) else ""
    return fail(f"{len(findings)} finding(s): {'; '.join(shown)}{more}")


def check_foundation_integrity() -> Result:
    """ECO-067: Foundation structure, links and retired paths/terms (Marcelo, 2026-11-14)."""
    try:
        findings = _knowledge_hygiene().foundation_findings()
    except Exception as exc:  # an unreadable Foundation is a failure, never a pass
        return fail(f"Foundation integrity not verified: {type(exc).__name__}")
    return _findings_result(findings, "Foundation structure, links and terms are current")


def check_agent_memory_size() -> Result:
    """ECO-068: Hermes and external agents' memories within their runtime limits."""
    try:
        module = _knowledge_hygiene()
        findings = module.memory_size_findings(module.memory_inventory())
    except Exception as exc:
        return fail(f"Agent memory size not verified: {type(exc).__name__}")
    return _findings_result(findings, "Agent memories are within their size limits")


def check_agent_memory_currency() -> Result:
    """ECO-069: agents' memories carry no retired rules, paths or dead links."""
    try:
        module = _knowledge_hygiene()
        findings = module.memory_currency_findings(module.memory_inventory())
    except Exception as exc:
        return fail(f"Agent memory currency not verified: {type(exc).__name__}")
    return _findings_result(findings, "Agent memories carry no retired rules, paths or dead links")


def check_agent_profile_files() -> Result:
    """ECO-070: one SOUL/IDENTITY per agent in its home, external agents carry USER/MEMORY, and each
    customer-service rules file ATENDIMENTO_<CANAL>.md equals what ForgeHub stores (Marcelo, 2026-11-14)."""
    try:
        module = _knowledge_hygiene()
        rows = psql("SELECT coalesce(json_agg(json_build_object('a',agent_slug,'c',channel,'h',content_hash)),'[]'::json) "
                    "FROM company.agent_service_rules", "forgehub", "forgehub_postgres")
        hashes = {(r["a"], r["c"]): r["h"] for r in json.loads(rows or "[]")}
        findings = module.profile_file_findings() + module.service_rule_findings(hashes)
    except Exception as exc:
        return fail(f"Agent profile files not verified: {type(exc).__name__}")
    return _findings_result(findings, "One SOUL per agent; service-rule files match ForgeHub; no legacy copies")


def check_module_health(name: str) -> Result:
    # Release source first; deployed profile scripts may load the helper next
    # to themselves. No dependency on an accidentally installed older profile.
    import importlib.util
    candidates = (Path(__file__).resolve().with_name('module_health.py'),
                  FORGEHUB / 'ops/athos/module_health.py')
    try:
        source = next(path for path in candidates if path.is_file())
        spec = importlib.util.spec_from_file_location('athos_module_health', source)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        check = module.CHECKS[name]
        counts = _metadata_counts(check.query, check.fields)
        healthy, notes = check.evaluate(counts)
        if name == 'remote':
            schema = _metadata_counts(module.COLLABORATION_SCHEMA_QUERY, ('tables', 'historical_events'))
            switch = os.environ.get('REMOTE_COLLABORATION_ENABLED', 'false').strip().lower()
            if switch not in ('true', '1', 'yes', 'on', 'false', '0', 'no', 'off'):
                raise ValueError('Invalid collaboration switch')
            expected = switch in ('true', '1', 'yes', 'on') or schema['historical_events'] > 0
            if schema['tables'] == 2:
                collaboration = module.COLLABORATION_CHECK
                valid, evidence = collaboration.evaluate(_metadata_counts(collaboration.query, collaboration.fields))
                healthy = healthy and valid
                notes += '; ' + evidence
            elif schema['tables'] == 0 and not expected:
                notes += '; collaboration_not_applicable=1'
            else:
                healthy = False
                notes += '; collaboration_unavailable=1'
        return ok(notes) if healthy else fail(notes)
    except Exception:
        if name == 'remote':
            return fail('remote_unavailable=1')
        return fail('NOT VERIFIED: module aggregate metadata unavailable')


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
    "ECO-060": check_forgevault_ssh_key_reads,
    "ECO-061": lambda: check_module_health("workers"),
    "ECO-062": lambda: check_module_health("mission"),
    "ECO-063": lambda: check_module_health("factory"),
    "ECO-064": lambda: check_module_health("remote"),
    "ECO-065": lambda: check_module_health("sessions"),
    "ECO-066": lambda: check_module_health("routines"),
    "ECO-067": check_foundation_integrity,
    "ECO-068": check_agent_memory_size,
    "ECO-069": check_agent_memory_currency,
    "ECO-070": check_agent_profile_files,
}


def active_items() -> list[tuple[int, str, str]]:
    rows = psql("SELECT id, item_description, coalesce(category,'') FROM audit.foundation_checklist WHERE status NOT IN ('retired','disabled') ORDER BY id;")
    return [(int(parts[0]), parts[1], parts[2]) for line in rows.splitlines() if line for parts in [line.split("|", 2)]]


AUDIT_FREQUENCIES = ("daily", "weekly", "monthly", "quarterly")


def check_interval() -> str:
    """The tier ForgeHub's Auditor ran this check in (FORGEHUB_AUDIT_FREQUENCY,
    set on every command since 2026-11-13); weekly when run by hand or by an
    older runner -- what the single Sunday audit always recorded."""
    value = os.environ.get("FORGEHUB_AUDIT_FREQUENCY", "").strip()
    return value if value in AUDIT_FREQUENCIES else "weekly"


def record(item_id: int, result: Result) -> None:
    notes = result.notes.replace("'", "''")
    state = "OK" if result.ok else "FAIL"
    interval = check_interval()
    psql(
        f"INSERT INTO audit.foundation_checklist_log(checklist_item_id,verified_at,result,notes) VALUES ({item_id},NOW(),'{state}','{notes}');"
        f"UPDATE audit.foundation_checklist SET status='{state.lower()}',last_checked=NOW(),last_result='{notes}',check_interval='{interval}' WHERE id={item_id};"
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

#!/usr/bin/env python3
# backup_offsite_projects.py -- worker of the per-project off-site backup.
# Started detached by backup_offsite_projects.sh (Athos cron, or a run asked for
# on ForgeHub's System Control -> Backup externo). Drains ForgeHub's queue
# (POST /api/v1/offsite-backup/internal/runs:claim, oldest first, one target
# per project as edited on that screen; the nightly schedule first queues
# every enabled target) and, for each target: dumps its Postgres container, takes a
# restic snapshot of its folders into the encrypted repository on Google Drive
# (rclone remote "gdrive"), applies retention to that target only, and reports
# the outcome back (POST .../internal/runs, .../internal/runs:finish). One
# target failing never stops the next. Sundays, after a full run: prune +
# integrity check with a 5% data read, recorded as "__repository__".
# The restic password comes from ForgeVault at run time (Athos identity,
# backup_forgevault_secret.py). Stdlib only; runs on the system python3.
import argparse
import fcntl
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
API = os.environ.get("OFFSITE_BACKUP_API", "http://localhost:8000/api/v1/offsite-backup")
FORGEHUB_ENV = Path("/root/project/forgehub/.env")
LOCK = Path("/root/backup/.backup_offsite.lock")
STAGE_ROOT = Path("/root/backup/offsite-staging")
HERMES_PY = "/usr/local/lib/hermes-agent/venv/bin/python"
RESTIC_SECRET_ID = "ce9121cd-9f0d-4616-aea0-e042abf14c5f"
REPOSITORY_RUN_NAME = "__repository__"
ALREADY_RUNNING_EXIT = 75

# Regenerable content, on top of each target's own excludes.
GLOBAL_EXCLUDES = [
    "node_modules", ".venv", "venv", "venvs", "__pycache__", ".next", ".pytest_cache", ".ruff_cache",
    ".mypy_cache", ".cache", ".npm", ".nuget", "**/bin/Debug", "**/bin/Release", "**/obj/Debug",
    "**/obj/Release", "/root/.local/share/Trash",
]
# The first run (2026-10-02) died on Google Drive's RATE_LIMIT_EXCEEDED:
# fewer, bigger packs and a paced rclone keep the request rate under it.
RCLONE_ARGS = (
    "serve restic --stdio --b2-hard-delete --tpslimit 4 --tpslimit-burst 4 "
    "--drive-pacer-min-sleep 200ms --low-level-retries 20"
)
RESTIC_GLOBAL = ["-o", f"rclone.args={RCLONE_ARGS}", "--pack-size", "64"]
KEEP = ["--keep-daily", "7", "--keep-weekly", "4", "--keep-monthly", "12"]


def log(message: str) -> None:
    print(f"{datetime.now().isoformat(timespec='seconds')} [offsite] {message}", flush=True)


def bridge_token() -> str:
    for line in FORGEHUB_ENV.read_text().splitlines():
        if line.startswith("CHAT_BRIDGE_TOKEN="):
            return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError("CHAT_BRIDGE_TOKEN not found in ForgeHub .env")


class ForgeHub:
    def __init__(self) -> None:
        self.token = bridge_token()

    def call(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            f"{API}{path}", method=method, data=data,
            headers={"X-Bridge-Token": self.token, "Content-Type": "application/json"},
        )
        for attempt in range(5):
            try:
                with urllib.request.urlopen(request, timeout=60) as resp:
                    return json.load(resp)
            except urllib.error.HTTPError:
                raise
            except OSError:
                # ForgeHub restarting (deploy): the backup itself must not be lost to it.
                if attempt == 4:
                    raise
                time.sleep(30)
        raise RuntimeError("unreachable")

    def start(self, name: str, trigger: str) -> str:
        return self.call("POST", "/internal/runs", {"target_name": name, "trigger": trigger})["run_id"]

    def finish(self, run_id: str, status: str, **fields) -> None:
        try:
            self.call("POST", "/internal/runs:finish", {"run_id": run_id, "status": status, **fields})
        except Exception as exc:  # noqa: BLE001 -- the log keeps it; the next start marks the run interrupted
            log(f"could not report run {run_id}: {exc}")


def restic_env(repository: str) -> dict:
    env = dict(os.environ)
    env["RESTIC_REPOSITORY"] = repository
    env["RESTIC_PASSWORD_COMMAND"] = f"{HERMES_PY} {SCRIPTS / 'backup_forgevault_secret.py'} {RESTIC_SECRET_ID}"
    env["RESTIC_CACHE_DIR"] = "/root/.cache/restic"
    return env


def run(cmd: list[str], *, env: dict | None = None, stdout=None) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, env=env, stdout=stdout or subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        detail = (result.stderr or "").strip()
        if not detail and stdout is None:
            detail = (result.stdout or "").strip()
        # Name the subcommand ("restic backup"), not the global flags before it.
        position = 1 + len(RESTIC_GLOBAL) if cmd[0] == "restic" else 1
        sub = cmd[position] if len(cmd) > position else ""
        raise RuntimeError(f"{cmd[0]} {sub} exited {result.returncode}: {detail[-1500:]}")
    return result


def dump_postgres(container: str, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    user = run(["docker", "exec", container, "printenv", "POSTGRES_USER"]).stdout.strip()
    with open(dest / "_globals.sql", "w") as out:
        run(["docker", "exec", container, "pg_dumpall", "-U", user, "--globals-only"], stdout=out)
    databases = run([
        "docker", "exec", container, "psql", "-U", user, "-d", "postgres", "-At", "-c",
        "SELECT datname FROM pg_database WHERE NOT datistemplate AND datname <> 'postgres'",
    ]).stdout.split()
    for db in databases:
        target = dest / f"{db}.sql"
        with open(target, "w") as out:
            run(["docker", "exec", container, "pg_dump", "-U", user, "--no-owner", "-d", db], stdout=out)
        if target.stat().st_size == 0:
            raise RuntimeError(f"empty dump {container}/{db}")


def stage_system_state(dest: Path) -> None:
    """Online SQLite copies of Hermes/Foundation and what rebuilding the host needs."""
    sqlite_root = dest / "sqlite"
    for root in ("/root/.hermes", "/root/db/sqlite-foundation"):
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in ("venv", "venvs", ".venv", "node_modules")]
            for name in filenames:
                if not name.endswith((".db", ".sqlite", ".sqlite3")):
                    continue
                path = Path(dirpath) / name
                try:
                    with open(path, "rb") as handle:
                        if handle.read(16) != b"SQLite format 3\x00":
                            continue
                except OSError:
                    continue
                copy = sqlite_root / str(path).lstrip("/")
                copy.parent.mkdir(parents=True, exist_ok=True)
                run(["sqlite3", str(path), ".timeout 10000", f".backup '{copy}'"])
    system = dest / "system"
    system.mkdir(parents=True, exist_ok=True)
    commands = {
        "apt-manual.txt": "apt-mark showmanual",
        "dpkg-selections.txt": "dpkg --get-selections",
        "snap.txt": "snap list",
        "npm-global.txt": "npm -g ls --depth=0",
        "hermes-agent-pip.txt": f"{HERMES_PY} -m pip freeze",
        "docker-ps.txt": "docker ps -a --format '{{.Names}}\t{{.Image}}\t{{.Status}}'",
        "docker-compose-ls.txt": "docker compose ls -a",
        "docker-images.txt": "docker image ls --format '{{.Repository}}:{{.Tag}}\t{{.ID}}\t{{.Size}}'",
        "docker-networks.txt": "docker network ls",
        "systemd-enabled.txt": "systemctl list-unit-files --state=enabled --no-pager",
        "systemd-user-enabled.txt": "XDG_RUNTIME_DIR=/run/user/0 systemctl --user list-unit-files --state=enabled --no-pager",
        "crontab.txt": "crontab -l",
        "host.txt": "uname -a; cat /etc/os-release; hermes --version",
    }
    for filename, command in commands.items():
        with open(system / filename, "w") as out:
            subprocess.run(command, shell=True, stdout=out, stderr=subprocess.DEVNULL)


def backup_target(target: dict, env: dict) -> dict:
    name = target["name"]
    missing = [p for p in target["paths"] if not os.path.exists(p)]
    if missing:
        raise RuntimeError(f"paths not found on the host: {', '.join(missing)}")
    target_stage = STAGE_ROOT / name
    target_stage.mkdir(parents=True, mode=0o700, exist_ok=True)
    target_stage.chmod(0o700)
    current = target_stage / 'current'
    previous = target_stage / 'previous'

    def validate_recovery_slots() -> None:
        for managed in (current, previous):
            if managed.is_symlink() or (managed.exists() and not (managed / 'COMPLETE').is_file()):
                raise RuntimeError(f'unrecognized recovery directory: {managed}; refusing replacement')

    # A persistent blocked slot must not generate another retained dump on
    # every retry. Check before allocating staging, then recheck on promotion.
    validate_recovery_slots()
    stage = Path(tempfile.mkdtemp(prefix='pending-', dir=target_stage))
    staging_complete = False
    sources = list(target["paths"])
    snapshot_saved = False
    # Staging contains credential-bearing SQL and SQLite copies. Keep it
    # root-only, including when the remote upload fails and it is retained.
    try:
        if target.get("postgres_container"):
            log(f"{name}: dumping {target['postgres_container']}")
            dump_postgres(target["postgres_container"], stage / "postgres" / target["postgres_container"])
        if target.get("include_system_state"):
            log(f"{name}: staging SQLite copies and host state")
            stage_system_state(stage)
        (stage / 'COMPLETE').write_text(datetime.now().isoformat())
        staging_complete = True
        # Publish only a fully staged replacement. The restic source path is
        # stable across runs; retain at most the current and previous complete
        # attempts. Never remove manually-created recovery directories.
        validate_recovery_slots()
        if previous.exists():
            shutil.rmtree(previous)
        if current.exists():
            current.rename(previous)
        stage.rename(current)
        stage = current
        if stage.exists():
            sources.append(str(stage))
        cmd = ["restic", *RESTIC_GLOBAL, "backup", *sources, "--one-file-system", "--exclude-caches",
               "--tag", "offsite", "--tag", f"target:{name}", "--json", "--quiet"]
        for pattern in GLOBAL_EXCLUDES + list(target.get("excludes") or []):
            cmd += ["--exclude", pattern]
        log(f"{name}: restic backup {' '.join(sources)}")
        out = run(cmd, env=env).stdout
        summary = {}
        for line in out.splitlines():
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if message.get("message_type") == "summary":
                summary = message
        if not summary.get('snapshot_id'):
            raise RuntimeError('restic returned no snapshot receipt; retaining staged database copies')
        snapshot_saved = True
        run(["restic", *RESTIC_GLOBAL, "forget", "--tag", f"target:{name}", "--group-by", "tags", *KEEP, "--quiet"],
            env=env)
        return {
            "snapshot_id": (summary.get("snapshot_id") or "")[:8] or None,
            "files_new": summary.get("files_new"),
            "data_added": summary.get("data_added"),
            "total_bytes": summary.get("total_bytes_processed"),
        }
    finally:
        # A failed upload must not discard the only fresh consistent copies.
        # Only a confirmed remote snapshot allows staging cleanup.
        if snapshot_saved:
            for managed in (current, previous):
                if (managed / 'COMPLETE').is_file():
                    shutil.rmtree(managed)
            if not any(target_stage.iterdir()):
                target_stage.rmdir()
        elif staging_complete and stage.exists():
            log(f'{name}: retained COMPLETE recovery copies in {stage}')
        elif stage.exists():
            # A partial dump is not a recovery copy. Earlier COMPLETE attempts
            # remain untouched if this staging attempt fails.
            shutil.rmtree(stage)


def main() -> int:
    parser = argparse.ArgumentParser()
    # schedule: queue every enabled target first, then drain the queue.
    # manual: ForgeHub already queued what was asked for; just drain it.
    parser.add_argument("--trigger", choices=("schedule", "manual"), default="schedule")
    args = parser.parse_args()

    LOCK.parent.mkdir(parents=True, exist_ok=True)
    lock = open(LOCK, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("already running")
        return ALREADY_RUNNING_EXIT
    STAGE_ROOT.mkdir(parents=True, exist_ok=True)

    hub = ForgeHub()
    if args.trigger == "schedule":
        queued = hub.call("POST", "/internal/enqueue", {"trigger": "schedule"})
        log(f"schedule: queued {', '.join(queued['queued']) or '(nothing)'}"
            + (f"; already waiting {', '.join(queued['skipped'])}" if queued["skipped"] else ""))

    claim = hub.call("POST", "/internal/runs:claim")
    if claim["run"] is None:
        log("queue empty")
        return 0
    env = restic_env(claim["repository"])

    # The repository must answer before any target is attempted; otherwise
    # every queued target would fail with the same error and fill the bell.
    try:
        run(["restic", *RESTIC_GLOBAL, "cat", "config"], env=env)
        # Only stale locks go (dead process, or older than 30 min): this host
        # holds LOCK, so no other backup of ours can be writing.
        run(["restic", *RESTIC_GLOBAL, "unlock"], env=env)
    except Exception as exc:  # noqa: BLE001
        error = f"repository unavailable: {exc}"
        hub.finish(claim["run"]["run_id"], "failed", error=error[-4000:])
        log(error + " -- the rest of the queue waits for the next launch")
        return 1

    done = failures = 0

    def drain(claim: dict) -> None:
        nonlocal done, failures
        while claim["run"] is not None:
            target, run_id = claim["target"], claim["run"]["run_id"]
            started = time.monotonic()
            try:
                stats = backup_target(target, env)
                hub.finish(run_id, "ok", **stats)
                log(f"{target['name']}: ok snapshot={stats['snapshot_id']} added={stats['data_added']} "
                    f"in {int(time.monotonic() - started)}s")
            except Exception as exc:  # noqa: BLE001 -- one target failing never stops the next
                failures += 1
                hub.finish(run_id, "failed", error=str(exc)[-4000:])
                log(f"{target['name']}: FAILED {exc}")
            done += 1
            # Whatever was queued meanwhile (a click during this run) is taken too.
            claim = hub.call("POST", "/internal/runs:claim")

    drain(claim)

    if args.trigger == "schedule" and datetime.now().isoweekday() == 7:
        run_id = hub.start(REPOSITORY_RUN_NAME, args.trigger)
        try:
            log("repository: prune + check (5% data read)")
            run(["restic", *RESTIC_GLOBAL, "prune", "--quiet"], env=env)
            run(["restic", *RESTIC_GLOBAL, "check", "--read-data-subset=5%", "--quiet"], env=env)
            hub.finish(run_id, "ok")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            hub.finish(run_id, "failed", error=str(exc)[-4000:])
            log(f"repository: FAILED {exc}")
        # A run asked for during prune/check (it can take an hour) would
        # otherwise wait for the next night.
        drain(hub.call("POST", "/internal/runs:claim"))

    log(f"done: {done} target(s), {failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

# Operational errors correction — 2026-10-26

Authorized request: Marcelo, "corrigir os erros". Scope: the findings from the pending-work inspection and incident #41560. No historical execution has been reset or marked completed.

## Corrected and verified

- Isolated ForgeHub patch fixes nested Auditor results and telemetry projection. Missing CPU/metrics are unavailable, never invented zeroes. Scheduled briefing completion requires real failure-treatment tasks; existing tasks by other agents and trailing owner/deadline details are accepted.
- ECO-044 no longer requires retired Vector. ECO-027 preserves historical experience provenance while checking current assertions, with pagination and incomplete-response failure. Both controls were re-run through ForgeHub and recorded `ok`.
- ECO-046 reads current per-project backup runs instead of abandoned whole-VPS staging, covers seven PostgreSQL containers and keeps failed/incomplete/stale snapshots red. Its current failure is real: the system backup has not completed externally.
- Shared-skills integrity was independently rechecked and recorded `ok`; no manifest was rewritten by this correction.
- Removed nonexistent `/root/agents` from system backup target. All retained paths were validated on the actual host. Original configuration: `/root/.hermes/profiles/athos/state-snapshots/operational-errors-20261025/system-backup-target.json`.
- System backup generated PostgreSQL and SQLite copies and attempted upload. The Google Drive shared OAuth project returned `RATE_LIMIT_EXCEEDED`, surfaced through restic as HTTP 500; no snapshot was falsely accepted.
- Worker now preserves private staging after failed upload, requires a snapshot receipt and isolates attempts so a failed retry cannot delete the last consistent dump. A private local Foundation dump was also regenerated at `/root/backup/offsite-staging/sistema/local-recovery-20261026T182648/postgres/hindsight_postgres/foundation.sql` (395,235,833 bytes, complete-dump footer checked). This does not prove an offsite restore.
- Three PostgreSQL containers were inspected with active `json-file` rotation `10m` x `3`. Compose validates. Existing logging definitions were preserved.
- Llamafile launcher is restricted to `127.0.0.1:8081` and starts in a detached session. Final runtime health must be confirmed after launch.

## Validation

The isolated release is based on `5714bf6`, without unrelated SSH/UI work. A separate database `forgehub_ops_verify_20261025` was created with a schema-only clone; no production records were copied. Current focused suite: **70 passed**, including the two previously excluded database tests. `--noconftest` avoids production-cleanup fixtures. Changed-file Ruff and `git diff --check` pass.

Command (using the existing interpreter; the database name is mandatory):

```sh
POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5433 POSTGRES_DB=forgehub_ops_verify_20261025 \
  /root/project/forgehub/backend/.venv/bin/python -m pytest --noconftest \
  app/tests/test_operational_mcp_contract.py app/tests/test_briefing_evidence.py \
  app/tests/test_factory_mcp.py app/tests/test_athos_audit_monitor.py \
  app/tests/test_audit_catalog.py app/tests/test_ecosystem_verifier_regressions.py -q
```

The profile-owned scripts are versioned as release copies in `ops/athos/`; their executable source remains `/root/.hermes/profiles/athos/scripts/`. Tests load that source on this host. Backups of original scripts and infrastructure files are private in `/root/.hermes/profiles/athos/state-snapshots/operational-errors-20261025/`.

## Remaining gates and external conditions

- Independent Porthus review and isolated ForgeHub release; no production deployment claimed by this report.
- Google Drive quota: shared OAuth quota is external. A successful snapshot and restore verification are still required. Do not replace an expired failure with `ok` or delete retained recovery copies.
- Voice: the current uniform Piper/auto-audio template contradicts the dated 1 October decision and Lara/Maia's current female Edge voices. The verifier supports the dated policy, but user confirmation is pending before changing active profiles; no profile or gateway restart was performed. Fleet guard also has unrelated pre-existing drift, which must not be blanket-accepted.
- Remaining listener/cleanup audit findings need comparison with approved Tailscale/RustDesk topology and the unapproved Docker-cache byte threshold. Do not disable checks or close remote access solely to make the audit green.
- Failed Hermes retrospective and Dartan quota remain separate runtime/provider issues; no uncertain run was retried and no completion evidence was fabricated.

## Rollback

Restore changed profile scripts from the private snapshot directory. Restore the backup target's exact `old_paths` only if the removed path is intentionally recreated. Restore the previous Llamafile launcher before a controlled service restart if required. ForgeHub rollback uses the previous backend image; do not release unrelated working-tree changes.

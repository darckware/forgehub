# Operational briefing incident — 2026-10-25

## Findings and evidence

The reproducible presentation defects belong to **ForgeHub**, specifically
`host-bridge/forgehub_messages_mcp.py`, loaded by
`backend/app/mcp/factory_server.py`. They do not establish a ForgeRouter outage.
Historical evidence below was read without changing production state.

### The 59 `never_ran` results are a broken MCP projection

Athos session `20261025_080011_24e3b7` in
`/root/.hermes/profiles/athos/state.db` contains the MCP response
`Auditor Checks (59)` with every entry displayed as `never_ran`.
The tool read `last_run_status`; the real `AuditCheckOut` schema and
`audit._check_out()` expose **`last_run.status` and `last_run.created_at`**.
The missing field unconditionally selected the `never_ran` fallback, even for
checks with recorded runs. The tool also omitted the enabled/disabled distinction.

Independent evidence contradicts a wholly missing baseline:
`/root/.hermes/profiles/athos/cron/output/2718ef651fec/2026-10-18_19-00-35.md`
records **43/53 OK, 10 failed**, including ECO-007, ECO-022, ECO-027, ECO-039,
ECO-040, ECO-041, ECO-044, ECO-046, ECO-047 and ECO-051. The weekly script posts
to `/api/v1/audit/run-internal`, whose implementation persists the returned runs.
Athos's cron store shows this job enabled, last status `ok` on 18 October and
next run 25 October at 19:00 BRT. Script success means the batch ran; it does not
mean every check passed. These historical counts are not today's live baseline.
The current database distribution could not be queried from the sandbox.

`run_audit_checks` had another projection defect: it expected
`passed/failed/total/results`, while `AuditRunAllOut` returns `runs` with
statuses `ok/fail/error/timeout`. It could report `0/0 passed, 0 failed` after
real failures. Its 60-second HTTP timeout was also shorter than the existing
weekly script's 1500-second batch allowance.

### Zero metrics were invented, not measured

The same briefing session records CPU `0% (0 cores)`, memory `0.0 / 0.0 GB`
and disk `0.0 / 0.0 GB`. The MCP queried `/api/v1/system-control/status`,
whose actual response contains Git/repository and backup information. It then
defaulted absent CPU/memory/disk objects to numeric zero.

The existing host telemetry contract is `/api/v1/system-stats`, proxying
host-bridge `/v1/system-stats`: memory/disk have `*_bytes` and `percent_used`.
It does **not** collect CPU. CPU is now explicitly unavailable, and absent
metrics cannot imply health. No new host collector or profile change is needed.
The bridge-token middleware permits exactly this read-only telemetry endpoint;
invalid/missing tokens and adjacent paths remain protected.

### #41555: partial security work, not a dispatch launch failure

Original demand ID: `59519d56-ec3e-4a05-ad59-2424b9dfbe33`.
Runner evidence:
`/root/.forgehub/agent-runs/b2364768-dcd8-416f-8d0a-f374d8867430.json`.
The Hermes process ran 06:00:00–06:05:50 BRT on 25 October and exited 0,
but its report explicitly says **`STATUS: PARTIAL`**. ForgeHub correctly maps
that completion report to `dispatch_status=failed`; exit 0 is not completion.

The report identifies pending listener hardening (8001/8081/8910), incomplete
ForgeVault authentication/TTL verification and an overwrite rejected by the
runtime file-mutation verifier. The dated report actually exists at
`/root/.hermes/profiles/aegis/daily_security_sweep_2026-10-25.md` (5743 bytes).
These are the execution's findings, not independently validated current
exposure or authorization to rotate credentials. Aegis/Hephaestus must validate
listener topology and ForgeVault access, preserving Docker's bridge needs;
blindly rebinding 8910 to loopback could break container-to-host access.

### #41553: Hermes lost its session turn lease

Original demand ID: `383d3fd6-e868-4c34-9d29-62354168ccb9`.
Runner evidence:
`/root/.forgehub/agent-runs/1a28bc4d-e0cd-409b-91da-d459ad6fd6a1.json`.
Session: `20261024_222007_cc4589`; execution 24 October 22:19:58–22:36:04
BRT (25 October 01:19:58–01:36:04 UTC), exit **130**.

`/root/.hermes/profiles/athos/logs/errors.log.1:391–395` records unavailable
ForgeHub tools, lease refresh staying locked, interrupted provider wait after
852 seconds and MCP termination during shutdown. The decisive terminal reason
is in `agent.log.1:13348`:
`interrupted_during_api_call(session_turn_lease_lost)`.
The preceding log records client abort against the local ForgeRouter endpoint.
Thus the long provider wait alone is not proof of a provider/router defect.
Logs show nine successful API calls (upstream Nvidia); the tenth was aborted.

The transcript additionally used `kanban_list` and received no ForgeHub matches
from `tool_search`; direct `tool_call` attempts said the tools were unavailable.
Startup logs nevertheless registered ForgeHub's 71 tools. This demonstrates a
runtime session/tool-catalog inconsistency, not an absent MCP implementation.

The corresponding lease mechanism is installed outside this repository at
`/usr/local/lib/hermes-agent/agent/turn_facade_lease.py:195` (also present in
the versioned Hermes install workspace). Repairing runtime lease contention or
tool projection requires Hermes diagnostics by its operator. This sandbox
cannot write there. The exact SQLite lock holder and the reason registered
tools disappeared from that session are not established by available evidence.
Recommended next step: correlate this session's turn-lease renewal and SQLite
lock diagnostics with runtime tool filtering; preserve recorded run IDs and
confirm terminal state before an authorized retry. Do not reset dispatch state
or bypass the lease. No ForgeRouter code was changed.

### #41557/#41558: a briefing is not corrective action or delivery evidence

Briefing demand ID: `d43170f3-51b0-4463-a0a6-45519682cee0`.
Runner `af38a996-4597-451b-92fb-26aff119aad5` claimed `STATUS: DONE` after
creating #41558 (`96057310-ace7-4525-90de-11060ea349ca`). The session's
`send_agent_message` response explicitly says **addressed to athos**, queued for
execution. `channel=telegram` identifies origin/context; it is not delivery.
Runner `1478028b-52a1-448a-b9d0-739612a8c954` then asked whether to start the
audit. It supplied no Telegram delivery receipt and no corrective handoff.
The original failure notices #41554/#41556 already existed; claiming no notice
existed would also be inaccurate. Notices alone do not prove remediation.

## Implemented correction and boundary

- MCP reads nested audit results/timestamps, distinguishes disabled controls,
  counts the actual execution array and displays failed check output. Missing
  batch evidence never becomes a successful `0/0` summary.
- System metrics use the existing host telemetry route and units; CPU and
  missing telemetry are explicitly unavailable. The batch timeout matches the
  existing weekly script's allowance.
- Scheduled briefings carry an action/delivery contract. Dispatch finalization
  refuses `DONE` when a failed routine in the preceding 24 hours lacks a real
  treatment task referenced as `ACTION: #source -> #followup`. The task must
  belong to the briefing agent, name an executor and cite the original failure.
  Archived/failed/incubation tasks, automatic notices without an agent author,
  fabricated IDs and another briefing do not satisfy this check.
- This gate verifies **handoff**, not repair completion, and operates at
  finalization. It does not intercept an external Telegram send. It covers
  recent failed routine demands, not every old audit finding or missed routine
  without a demand. Those remain visible operational work, not assumed healthy.
- Existing run IDs, production database state, profiles, secrets, listener
  bindings and the unrelated SSH-key changes in the workspace were preserved.

## Verification and remaining release work

Initial regression command: `cd backend && .venv/bin/python -m pytest
--noconftest app/tests/test_operational_mcp_contract.py -q`: **10 failed**
before correction, reproducing the contract defects; **10 passed** afterward.

Final offline command:

```sh
cd backend
.venv/bin/python -m pytest --noconftest \
  app/tests/test_operational_mcp_contract.py app/tests/test_briefing_evidence.py \
  app/tests/test_factory_mcp.py app/tests/test_athos_audit_monitor.py \
  app/tests/test_audit_catalog.py \
  -k 'not test_status_separates_scheduler_from_check_result and not test_db_catalog_matches_canonical' -q
```

`--noconftest` avoids shared fixtures that mutate the operational database.
Final result: **49 passed, 2 deselected in 3.54s**. Coverage includes the
completion gate's invocation from dispatch finalization, actual task-reference
validation, generated briefing instructions and exact telemetry auth scope.
The two deselected tests require that database. The sandbox cannot reach
`forgehub_postgres:5433` (connection timeout) or `localhost:8000/health`
(connection refused); Docker socket access returns permission denied.
The initial broader run was interrupted when it reached database tests.

`ruff check app` found four existing errors in the pre-existing changes to
`api/routes/server.py` (unused `or_`, `KeysToVaultOut`, two `old_ref` assignments).
Scoped backend lint passed. Explicitly linting the MCP file also finds two
pre-existing unused variables (`grant` and `res`) outside changed lines.
`git diff --check` passed. No frontend change/build is needed for this patch.

Release requires Porthus's independent review, the database-backed tests,
authenticated live MCP smoke checks, and the normal deployment gate. The
runbook commands are `./scripts/build.sh` and `./scripts/deploy.sh`; the latter
builds and runs `docker compose up -d --no-build`. Do not deploy this dirty
workspace, which includes unrelated work. After an isolated reviewed release,
verify real audit timestamps/statuses, unavailable CPU, memory/disk source,
briefing failure without action, and completion with valid treatment tasks.

No production deploy or credential change was performed. Remaining external
work: Hermes lease/tool-catalog repair, security verification by the owners,
and verified delivery of future briefings through the authorized send path.

The targeted `git add` of only this incident's eight files failed with
`fatal: Unable to create '/root/project/forgehub/.git/index.lock': Read-only file system`.
The sandbox explicitly mounts `.git` read-only; no commit or push was possible.
No alternate Git directory or permission bypass was attempted. The existing
HEAD remains `5714bf6`; it is **not** a commit of this correction. Review and
release must run in an environment with a writable Git index and Docker access.

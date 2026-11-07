# Mission management verification — 2026-11-07

Continues Marcelo's last session: mission registration/editing, orchestration, member functions
and scoped context for executors and reviewers. Implementation is local; nothing was deployed
and no real mission or agent run was created by these checks.

## Result

Administrators can create a draft, edit unapproved mission metadata and cancel with a written
reason and confirmation. Cancellation preserves history. Row versions reject stale edits and
terminal missions remain read-only. Athos is suggested from an active registry record; the
selected orchestrator owns the protected coordinator membership.

The edit page manages member functions, responsibilities and review permission via the mission
command, with confirmation and an idempotency key preserved on retry. Releasing a member does
not delete its history. Task assignment and independent reviewer selection remain in planning
and the execution board. Human acceptance is unchanged.

Executor and reviewer dispatches include their own membership, the orchestrator and the existing
allowlisted task/brief/baseline/criteria slice. Review dispatches also carry the reviewed execution's
summary/evidence and the decision route, with read-only instructions. They do not instruct the
reviewer to report an executor run. Source hashes are retained in the audit manifest; the 32 KiB
limit applies to both modes. Existing memory-hook containment remains a separate requirement.

## Checks run

| Check | Result |
|---|---|
| `ENVIRONMENT=test .venv/bin/python -m pytest app/tests/test_mission_base.py app/tests/test_mission_dispatch_context.py -q` (backend) | 23 passed |
| `ENVIRONMENT=test .venv/bin/python -m pytest app/tests/test_mission_dispatch.py app/tests/test_mission_dispatch_context.py app/tests/test_mission_mcp.py -q` (backend) | 28 passed; context module overlaps the previous run |
| Ruff on all changed mission Python files | Passed |
| `npm test -- --run` (frontend, final run) | 107 files, 478 tests passed |
| `npm run build` (frontend, final run) | Passed, locale catalogs aligned; existing large-bundle warning remains |
| Chromium with fictitious API responses | 1440 px and 390 px; no horizontal overflow, keyboard focus, membership loading failure/retry affordance, no runtime exceptions or API mutations |
| Premium static UI audit | No findings in the changed mission form/team; 53 repository findings remain outside these changed owners |
| `git diff --check` | Passed |

The new executor-context and reviewer-context assertions failed before their implementation,
then passed. Frontend coverage includes draft creation, non-administrator refusal, membership
confirmation, metadata edits with row version, reason/confirmation before cancellation and
terminal read-only behavior. API tests use the guarded isolated test database only.

The native select popup interaction stalled the first Chromium automation attempt. The final
smoke checks keyboard focus without opening that popup; popup keyboard behavior is not claimed
as verified. Native select and datetime popups remain browser-owned as documented in DESIGN.md.

## Screenshots

- [Desktop form](evidence/2026-11-07-missions/forgehub-missions-desktop.png)
- [Team functions](evidence/2026-11-07-missions/forgehub-missions-team.png)
- [Mobile](evidence/2026-11-07-missions/forgehub-missions-mobile.png)

## Finalization follow-up

The independent local technical review found two issues, both corrected and re-reviewed:
the form now pins its row version to the snapshot that populated its fields (including cancellation),
and existing members whose agents became inactive remain selectable for release.
Regression checks reproduce the failures before the fixes; the concurrency test waits for the
query cache notification before submitting. The local re-review passed all eight form tests.

Fresh release checks on the corrected tree:

- Backend full suite: **1,963 passed, 21 skipped**, 23 warnings, 358.13 seconds.
- Frontend full suite: **107 files, 480 tests passed**.
- Frontend build, locale checks, scoped Ruff and `git diff --check`: passed.
- Fresh production backup restored in an isolated disposable PostgreSQL: revision `d2f8a6c41e07`,
  180 company tables, zero invalid indexes, restore/startup 3.57 seconds. No published ports,
  application processes, shared volumes or egress; quarantine discarded after verification.
  Backup SHA-256: `5fe02850dc204c163b97f183bf8f61a8957d8c1f070c25ead6fb7a696a4f4208`.

Official Porthus review was requested through ForgeHub Messages **#42236**. The request is queued
with no run. ForgeHub records his usage-limit unavailability until **2026-11-10 02:00 UTC**
(2026-11-09 23:00 America/Sao_Paulo), sourced from run #42232. The alternate external agents also
have future usage-limit blocks. No availability, retry or run fields were cleared to force a review.

Production remains `fh-d84a445`; `MISSION_TOOLS_ENABLED` and `MISSION_CYCLE_ENABLED` are both false.
The new release has no migration. Its publication, tool activation and a real FileNest mission
remain unverified until the applicable gates are met. The isolated full suite includes all four M0
rehearsals (membership, planning-to-active, dispatch/report and review/completion); those are tests,
not a real accepted FileNest mission. The live project inventory contains ten projects and no FileNest
project. Existing FileNest implementation work in `/tmp/filenest-implementation` was identified and
preserved; it must not be duplicated or treated as accepted.

Independent official release approval and production publication are not claimed by this report.
Unrelated FileNest planning, ECO-047 and diagnostics changes in the workspace were preserved.

Later the same day Marcelo instructed **“faça você a revisão”**, authorizing Aramis to substitute
the blocked Porthus review for this release. The request #42236 was preserved and archived.
See [the operator-requested review](2026-11-07-mission-self-review.md) for findings, corrections
and the final release decision; the pending-review state above is the earlier historical snapshot.

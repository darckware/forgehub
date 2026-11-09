# Mission, Messages and 24x7 maturation: planning review

**Result:** written plan approved after corrections by two independent read-only reviews.
This approves the planning/context consolidation, not implementation completion or activation.

## Reviewed artifacts

- Spec: `docs/superpowers/specs/2026-11-09-mission-messages-maturation.md`.
- Plan: `docs/superpowers/plans/2026-11-09-mission-messages-maturation.md`.
- Context/decision boundaries: `docs/architecture/MESSAGES_ORCHESTRATION.md`.
- Prepared label catalog: `docs/product/messages-labels.md`.

The reviews checked repository code for claim accuracy. No database tests, production writes,
agent messages or Telegram deliveries were performed by the reviewers.

## Preserved direction

Mission/Task retains work management and canonical dependencies/evidence; Messages retains
administrative execution and communication; Operação 24x7 aggregates/supervises the same records;
Pessoal remains Marcelo's actual decision surface. No replacement architecture or extra general
orchestrator is proposed.

The plan preserves the existing analysis/decision-aid button, right-side label legend, current
folders, per-agent contracts, source-specific permissions and governed mission acceptance.
Outstanding tasks remain accountable; a blocked task is never made complete merely to clear a queue.

## Review corrections incorporated

| Finding | Correction |
|---|---|
| Reconciliation helper without guaranteed caller | Task 2 places bounded reconciliation at the start of the existing periodic dispatcher, outside due/assigned selection; tests cover disabled contextual maintenance and lost wake/concurrent passes |
| Request hash could include mutable server context | Task 3 hashes immutable caller payload/expected context; completed identical receipt replays before fresh-context validation; only a new effect validates current expected context |
| Resource-policy expansion implicit | Task 5 explicitly preserves current mission-only checkout/branch protection and canonical-task publication targets; extension is a separate policy decision |
| Pessoal destination metadata may hide the actual question | Task 1 browser tests require the same registered question and guarded answer control across task/incubation/Moodle origins, including a question blocking an approval |
| Planning-stage work outside active/verifying watchdog | Task 7 explicitly qualifies stalled P1–P8/planning recovery while preserving deliberate pauses and legitimate waits |
| Standalone personal/service work not covered by a mission test | Tasks 2/6 include owner/intent/recovery and Telegram continuity without requiring a new mission |
| Dossier metadata agreement could look like trusted verification | Task 7 adds negative checksum/forged-metadata/stale-version/changed-scope cases and a bounded trusted-content verification guard |
| Current paused-worker ownership unclear | Ledger names the publication owner, actual flags, restoration/hold responsibility and verification condition; subsequent restoration is recorded below |
| New executable replies could be mistaken for completed feedback | G10 and Tasks 1/2 distinguish question-answer continuations from inert completed returns and preserve original authorization guards |
| Inbox acknowledgement could strand a consumer after a crash | G11 and Task 6 inject an acknowledgement-before-execution crash and recover from the existing run/progress contract without blind replay |

Both reviewers approved the revised written plan. The delivery review also rechecked the G10/G11
addendum and updated operational checkpoint and found no new blocking planning issue.

## Important gaps before broader activation

The highest-priority qualification items are reliable authorized-wait recovery, useful contextual
advice on real pending human decisions, full command replay/crash semantics, event cursor recovery,
and executable question-answer continuity. Role-compatible reassignment, safe declared parallelism,
planning supervision and accepted delivery remain explicit gates rather than assumed capabilities.

Tests named in the new plan are future acceptance work unless the publication ledger explicitly
records a completed run. A testable plan is not evidence that those tests have already passed.

## Verified operational checkpoint

At `2026-11-09T16:59:31Z`, ordinary backend workers were restored on the existing reviewed
`c86227f` production artifact. Confirmed settings:

- `BACKGROUND_WORKERS_ENABLED=true`.
- `MESSAGE_TRIAGE_ENABLED=false`.
- `MISSION_CYCLE_ENABLED=false`.
- Backend health returned 200 and frontend API proxy was verified.

This closes the temporary staging suspension and restores existing operation. It does not enable
the new triage maintenance or automatic mission manager. The checkpoint is recorded in
`/root/.forgehub/releases/messages-triage-c86227f/release.json`.

Porthus requests **#42232, #42233, #42234 and #42235** were checked again and remain archived.
Their independently verified Aramis deliveries and replay vetoes are preserved; the original
pending dispatch history was not rewritten as a successful Porthus execution.

Repository `d81933c` and prepared working-tree changes remain distinct from the production artifact.
The plan's first task qualifies the prepared labels, links and factual closure before publication.

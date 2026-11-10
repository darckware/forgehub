# Mission/Messages maturation implementation progress

Plan: `docs/superpowers/plans/2026-11-09-mission-messages-maturation.md`.

Recovery entry point: [requirements and continuity checkpoint](2026-11-09-development-continuity.md).
This preserves later operator requests beyond the original seven tasks. Counts
below describe individual historical runs; the final full regression/build was
interrupted by the terminal scope OOM and is not a completed qualification run.

This is an implementation checkpoint, not a release or qualification claim.
The branch has uncommitted implementation; deployment has not changed.

## Task 1: prepared, qualification incomplete

Labels, legend and factual closure are prepared. Actual blocking questions
are exposed in each Personal group, including the same guarded answer control.
Manual archives do not imply delivery; pending executable replies are not completed.
Incubation owner decisions are distinct from operator decisions.

Latest checks: classifier/triage 41 passed; Personal/Messages/label UI 35
passed; frontend build and three locale catalogs passed.
Remaining: browser/keyboard qualification and independent review/publication.

## Task 2: in progress

The existing periodic dispatcher reconciles audited automatic quota postponements
before ordinary due-message selection. It preserves deliberate schedules, changed
content, approval gates and original run reservation. Its bounded candidate query
requires quota audit provenance so ordinary future schedules cannot fill the scan.
Persisted intent is distinct from the executor-bound approval fingerprint;
current approval and dispatch admission are still checked before release.

Latest check: recovery/failover/dispatch-signal suite **32 passed**.
Coverage added for early quota reset, deliberate future scheduling, missing executor
followed by assignment, pending approval, and concurrent periodic passes in fresh
sessions. Concurrent passes use the actual persisted reservation and produce one
run ID without a wake signal or model invocation.

Also covered: busy executor release without a wake, changed scope, independently
verified delivery veto and uncertain run identity. Remaining: full scan/admission
review, answer continuation qualification, and commit qualification.

Reproduced starvation of the 201st quota wait (RED). Bounded scans now order
by persisted `executor_wait_checked_at`, use row locks with skip-locked admission,
and preserve the message's content updated_at when recording a check. A fresh
session reaches later waits while the first 200 remain blocked. Migration
`e4d0b2c67a95` adds the bookkeeping column and partial queue index; downgrade,
re-upgrade and the **32-test** recovery suite passed on the isolated test database.
Production migration/deployment has not been performed.

## Task 3: in progress

Reproduced cursor loss with an injected request failure (RED). The periodic pass
now persists event cursor and request/rerun intent together. The request helper
accepts `commit=False`, leaving commit and wake to its caller. The periodic pass
wakes only after commit. The reproduced failure and existing mission-cycle suite
passed together: **31 passed**. An additional rollback/no-wake/default-commit
test passed with the failure scenario: **2 passed**.

Reproduced changed-reason reuse returning an incorrect 200 (RED), then added
complete immutable request hashing and existing actor/key command receipts.
Changed reason/parameters now conflict; identical requests replay the receipt.
Recovery plus existing mission-cycle regression suite: **33 passed**.

Added optional `expected_context_version`, validated after receipt replay and
before new effects. Reproduced missing field support (RED); the recovery suite
including stale-context refusal and replay after context advances: **4 passed**.
The current server context is not included in request identity.

Remaining: mandatory version for automatic manager calls (including tool contract),
recoverable nested effects after their inner commit, and legacy receipt handling
review. Automatic manager execution remains disabled during qualification.

Reproduced a committed assignment surviving failure of outer decision completion
(RED). Extracted internal assignment/review/return commands with caller-owned
commit, preserving public endpoint behavior. The cycle now uses these commands
without committing before its decision/audit/context/receipt. Recovery plus
existing mission-cycle suite: **35 passed**.

Reproduced incomplete replay after accepted external dispatch (missing demand
link and final context). Recovery now reads the committed actor/key task-dispatch
receipt, validates the canonical demand/task link and finishes the outer audit,
context and receipt without invoking the runtime. Concurrent replay produces one
final audit and one runtime start. Recovery plus existing cycle suite: **36 passed**.
Other nested actions, explicit pending status and uncertain-host rejection handling
still require qualification.

Reproduced an interrupted accepted dispatch showing applied, and an accepted
host request with lost response showing refused (RED). Decisions now start
pending; completion sets applied/deferred in the final transaction. A committed
dispatch receipt/run preserves pending through the HTTP error instead of recording
a false refusal. Replay recovers the same identity and finalizes decision records
without another runtime start. Migration `e5e1c3d78ba6` extends the status constraint
and refuses downgrade while pending rows exist. Test-only upgrade and the recovery
plus existing cycle suite passed: **38 passed**. Downgrade/restore qualification,
other nested actions and final review remain open; no production activation.

New agent decisions now require an explicit `expected_context_version`; reproduced
missing-version acceptance (RED), then added the guard after completed receipt
replay. Human/legacy user requests retain the optional field. Old agent clients
receive actionable `CONTEXT_VERSION_REQUIRED` instead of silently executing from
unspecified context. MCP decision/defer/pause tools forward the caller's version
(including zero), and routine instructions require preserving it on retry.
The test client preserves the original version per request key. Recovery plus
existing mission-cycle suite: **37 passed**. Current server context is never
silently fetched as a replacement for the agent's caller-supplied version.

## Task 4: in progress

Reproduced deterministic pending approvals being omitted from contextual analysis
(RED). Real approval/question decisions now receive bounded contextual input,
including pending blocking question text/context/recommendation. The deterministic
fallback is saved before the optional provider call. A separately fenced enrichment
step rechecks source/context freshness and the actual pending decision, then
updates only summary/reason/recommendation. Model state/category/action/evidence
and routing cannot replace backend facts. Tests cover both decision types, a model
proposing resolve, provider outage and changed scope. Decision aid, triage and
analyzer unit regressions initially: **46 passed**. Added answered-question and
expired-lease enrichment fences, and a provider-boundary test for sanitization
and untrusted question content. Final affected backend/analyzer run: **49 passed**.
Personal decision/label UI run: **29 passed**. Affected Python lint passed after
removing an unused import and documenting intentional pytest fixture injection.
Task 4 remains prepared pending integration review/commit and publication.

## Task 5: in progress

Started the deterministic `executor_eligibility` reason interface and reused it
in automatic substitution. Initial blockers cover inactive/missing runtime,
fixed/approval-bound work, private/ambiguous ownership and registered-role mismatch
or missing declared role. Test fixture agents now explicitly declare their
developer contract instead of relying on runtime alone. Initial eligibility and
existing failover regressions: **25 passed**. This is not complete compatibility:
project membership, required skills, reviewer independence, permissions and
reservation-time revalidation remain to implement/qualify before publication.

Added canonical project membership with validity dates, allowed runtime, required
skill grants, explicit unverified proficiency, current assignment and independent
review checks. Reproduced missing member/runtime/skill blockers and a permission
changed after selection (RED). Reservation now invokes the same checker with
fresh ORM reads. Eligibility/failover/mission recovery/cycle regressions passed:
**67 passed**. Added a separate-session permission race and author-as-reviewer
case. Baseline/target regressions found an unintended membership requirement for
an unchanged ad-hoc channel dispatch; corrected to preserve that source policy.
Final project-eligibility plus baseline/target suite: **24 passed**, affected lint
passed. Remaining: broader source-policy/permission and concurrent substitution
review, complete parallel target qualification, actual skill-content/runtime
capability resolution from the added operator requirements, and final review.

## Task 6: in progress

Executable answer continuation: reproduced blanket rejection of all replies and
missing source authorization at the canonical execution guard (RED). Pending
executable replies can now use ordinary guarded queue admission; completed
informational replies remain inert. Reply/diagnostic source authorizations are
refreshed and checked before execution. A source-scope edit also reproduced stale
continuation advice (RED); database context revisions now include the reply source,
linked answer question and source Moodle authorization. Freshness filters and
admission therefore invalidate the old advice. Combined triage/classification,
question/handoff and executor-recovery suite: **66 passed**, affected lint passed.
Recovery sweep tests reuse the existing isolated-queue fixture so unrelated test
records neither occupy their capacity nor get changed by simulated dispatches.
Nested/transitive source chains and source-specific continuation scopes still
need qualification before publication.

Reproduced a nested reply bypassing the top-level pending approval (RED).
Authorization checks now traverse the bounded source graph, refreshing each
ancestor and rejecting cycles/oversized unresolved context. Shared ancestors
are checked once and are not mistaken for cycles. Source-graph, triage,
classification and handoff regressions: **48 passed**. Canonical task baseline,
dependency and execution-evidence continuity across answer tasks still need
explicit qualification; source approval checks alone do not prove that contract.

Reproduced duplicate questions from concurrent identical keyed API requests (RED).
QuestionAskIn now supports a stable caller key; the route reuses existing
actor-scoped command locking/hashing/receipts and commits the question with its
receipt. The external runtime MCP ask tool requires a stable request key; legacy
API callers may still omit it and retain legacy semantics. Receipt retention
remains the existing replay window; durable post-retention replay qualification
remains open. No text-similarity deduplication was added.

Reproduced concurrent identical answers failing on duplicate notification keys
(RED). Core answer handling locks/rechecks the question and returns the existing
resume task for the same recorded answer; different answers/cancellation conflict.
Relay authorization remains before the core operation. Screen answer/cancel now
load the same locked question. Handoff and existing question suite: **13 passed**;
selected mission question/default consumers: **3 passed**. All transport is stubbed
or deferred; no live Telegram delivery was performed.

Remaining: executable reply admission/source authorization, consumer-ack crash
recovery, late/delayed transport, durable identity qualification, bridge/runtime
regressions and standalone service continuation proof.

Canonical continuation follow-up: reproduced lost Task/project identity
on an answered question (RED). The answer demand now retains the canonical
task/project, working path and carried mission context, remains executor-bound,
and allocates its own pending TaskExecution using a shared serialized allocator
also used by normal task dispatch. The prior attempt and evidence are preserved;
identical answer replay creates no additional attempt. Continuation dependency
and baseline guards were exercised, alongside the ordinary dispatch and question
regressions: **21 passed**, affected lint passed. Remaining before publication:
fresh allowlisted runtime context, late answers to terminal/reported work,
original-run uncertainty and final evidence/reporting end-to-end qualification.

Late-answer qualification: reproduced a new attempt being created after
canonical Task done/deployed/cancelled (RED). The question/answer is now retained
and its linked informational demand archived with an audit reason, without
scheduled execution, run identity, completed-attempt claim or new TaskExecution.
The canonical Task state and prior evidence remain intact. Task-row locking
protects the creation check; shared allocation and executor eligibility also
refuse terminal tasks. Canonical continuation, ordinary dispatch and question/
handoff regressions: **24 passed**, affected lint passed. Still open: reported/
verified source attempts awaiting review, prior-run uncertainty, preparation of
fresh allowlisted runtime context, and whether deferred attempt allocation at
the start boundary better preserves review continuity while the source is active.

## Task 7: in progress

Reproduced a mission question for one task hiding another independent idle task
(RED). The watchdog now resolves the question's actual dependent task IDs and
scopes task-specific deferrals; a recent explicit mission-wide defer remains a
valid hold. Unexplained idle findings include exact task IDs. New supervision
scenario plus existing cycle suite: **31 passed**, affected lint passed.
Remaining: an active independent task hiding other idle work, planning-stage
supervision, durable missing-cycle recovery, service/routine continuity, trusted
dossier evidence, end-to-end acceptance and publication/restore qualification.

Automatic manager activation remains outside the qualified scope until Task 7.

## Additional operator context

Read-only analysis of 40 recent coding-agent Messages and current launch adapters
is recorded in `2026-11-09-external-coder-execution-context.md`. Marcelo's criteria
are speed, quality and excellence in completed delivery. Proposed runtime skills
and structured delegation/parallelism intent complement Tasks 4–7. No live skill,
agent profile, execution permission or launch configuration changed in this analysis.

Continuation qualification: the canonical answer now rebuilds the current allowlisted
Task/mission prompt at reservation, preserves previous evidence and refuses uncertain
source runs. The real dispatch stub received Task scope plus the answer and reported
its own attempt. Admission/question/Task locks now share a consistent order. Combined
continuation, dispatch, handoff, question and recovery regressions: **33 passed**.

Atomic effects: reproduced a paused mission surviving a failed outer decision (RED),
then moved pause/reprocess/task-update/integration-queue effects under their existing
caller-owned transaction. Scheduler wake follows the completed outer commit. Cycle
and recovery suite: **39 passed**. Additional queue-rollback and delivery suite:
**18 passed**, including the planning-record migration round trip.

24x7: reproduced an active task hiding independent idle work (RED); supervision now
subtracts actual running/scheduled Task IDs before reporting unexplained work. Both
question-wait and running-task scenarios passed. Planning-stage missing-cycle
supervision and safe existing-routine recovery are being qualified.

Dossier integrity: reproduced registration accepting a nonexistent file (RED).
Registration now checks bounded regular-file bytes in the existing mission-scoped
Docs tree, requires the stored checksum and caller hash to match those bytes, and
rechecks the latest dossier before awaiting acceptance. Missing or changed content
blocks the transition. No arbitrary URL fetching or model evidence is trusted.

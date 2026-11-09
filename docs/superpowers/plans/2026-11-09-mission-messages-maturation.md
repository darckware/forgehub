# Mission, Messages and 24x7 Maturation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans with the native coordinator and independent bounded assignments already used in this work. Execute task-by-task; independent review precedes publication. This document plans hardening of the existing solution.

**Goal:** Keep authorized work accountable through verified delivery and acceptance despite quota, executor, event, transport or runtime failures.

**Architecture:** Preserve Mission/Task as the work-management source, Messages as the administrative dispatch lifecycle, 24x7 as aggregate supervision, and Pessoal as Marcelo's decision surface. Reuse the current dispatcher, command receipts, mission cycle, question/approval paths and durable analysis jobs. Labels remain read-only projections.

**Tech Stack:** FastAPI, SQLAlchemy/Alembic/PostgreSQL, existing host bridge/runtimes/ForgeRouter, React/TanStack Query/i18n.

**Spec:** `docs/superpowers/specs/2026-11-09-mission-messages-maturation.md`.

## Global constraints

- Strengthen the existing solution; no new general orchestrator, task registry, dispatcher or permission system.
- Keep canonical task, execution, attempt and message states distinct and linked by their existing IDs.
- Preserve original attempts, partial effects, delivery evidence, independent review and source-specific approvals.
- No agent gains authority from text, a label, a model recommendation or a free quota window.
- Fixed reviewers, privacy boundaries, executor-bound approvals and mission baselines remain binding.
- A lost event is recovered from persisted facts; an uncertain execution is reconciled before replay.
- Test only under `ENVIRONMENT=test`; no live Telegram messages or synthetic production tasks.
- Keep `MISSION_CYCLE_ENABLED=false` until the manager-specific qualification gate is satisfied.
- Document actual code/deployment state separately; a prepared implementation is not an enabled feature.

## Review focus

- Crash after host acceptance or a nested command commit: recover the same operation and its audit without replaying side effects (Tasks 3/6).
- Quota expires but an old automatic schedule or missing assignment strands authorized work (Task 2).
- Independent-looking tasks touch the same checkout/publication target, or a substitute violates its role/privacy/review contract (Task 5).
- Telegram/MCP redelivery or a late answer creates duplicate decisions, tasks or contradictory authorization (Task 6).
- A pending human decision receives generic or stale advice, or a diagnostic/archived message is mistaken for accepted delivery (Tasks 1/4/7).

## Baseline and delivery ledger

| Item | Prepared/implemented | Active at planning checkpoint |
|---|---|---|
| Mission registration selector fix and improved controls | Committed and published | Yes |
| Porthus #42232–35 reconciled to independently verified Aramis deliveries | Audited, replay veto and guarded archive | Yes; four archived |
| Durable Messages analysis, content/context freshness and fenced jobs | Committed | New maintenance disabled; ordinary workers restored |
| Delivery-aware failure diagnostics and feedback suppression | `d81933c`, tested | Not in staged `c86227f` artifact |
| Labels/legend/Pessoal links | Working tree, isolated backend and frontend/browser checks | Not published |
| Verified archival refinements | Working tree, domain regression checks | Not published |
| Contextual advice for real pending decisions | Gap G2 identified | Not complete |
| Automatic mission manager cycle | Existing guarded implementation | Disabled |

Checkpoint validation: backend full baseline 2,050 passed/21 skipped; later affected-domain checks include 44 triage/presentation and 51 delivery-consumer tests, plus isolated classifier and UI tests. These counts describe their recorded runs, not one final combined run of all current changes.

Publication is a separate operational gate: record actual image IDs/commits/flags before and after; retain backup/restore and rollback evidence. Explicitly restore or activate only the already-qualified existing flows, rather than leaving an undocumented disabled worker.

**Checkpoint continuity owner:** Aramis owns publication/recovery verification. The temporary
staging suspension was closed at `2026-11-09T16:59:31Z`: ordinary dispatch, completion polling and
reconciliation were restored on the same reviewed `c86227f` image, with backend health and frontend
proxy verified. Confirmed flags: `BACKGROUND_WORKERS_ENABLED=true`, `MESSAGE_TRIAGE_ENABLED=false`,
`MISSION_CYCLE_ENABLED=false`. This restores existing operation and does not activate new manager
autonomy. Any future validation suspension must name its owner, reason, and next review condition,
and end by verifying restored flags/health or an explicit operator-directed hold. A restart alone
is not evidence that workers resumed.

## Existing owners and files

| Area | Existing owner/files |
|---|---|
| Message admission and execution | `core/demand_workflow.py`, `core/demand_dispatch_guard.py`, `api/routes/demand.py`, `core/dispatch_signal.py` |
| Analysis and operator presentation | `core/message_triage*.py`, `core/message_classification.py`, `api/schemas/demand.py`, Messages/Personal frontend |
| Mission decisions and recovery | `core/mission_cycle.py`, `api/routes/mission_cycle.py`, `core/command_receipts.py`, `db/models/mission.py` |
| Work dependencies, roles and evidence | `core/task_dependencies.py`, `core/dispatch_targets.py`, `core/task_completion_guard.py`, `api/routes/mission_task.py` |
| 24x7 and questions/Telegram | `api/routes/operations.py`, `core/agent_questions.py`, `main.py`, existing operations frontend |
| Acceptance and dossier | `core/mission.py`, `core/mission_records.py`, `api/routes/mission_records.py` |

---

### Task 1: Qualify the prepared labels, legend and factual closure

**Files:** existing classification/schema/GET annotations; `frontend/src/lib/messageLabels.ts`, Messages UI/shared overlay/locales; `docs/product/messages-labels.md`; `app/tests/test_message_classification.py`, `app/tests/test_message_triage.py`.

**Interfaces:** preserve additive `DemandOut.message_labels`, executor wait metadata, `operator_destination` and `operator_decision`; preserve `classify_messages(db, demands)` and current analysis job APIs.

- [ ] Add regression: manual archive of an unverified failed attempt is tagged archived, never completed; source attempt remains unchanged.
- [ ] Add regression: a new executable `reply_to_id` continuation is not labeled completed before it runs. Completed informational returns remain distinct.
- [ ] Add regression: actual approval/question outranks quota, routes to the correct Pessoal group, and disappears after a valid answer/current authorization.
- [ ] Browser-test blocking questions attached to task, incubation and Moodle origins: the destination must expose the same question ID and its guarded answer control. Reuse the current question component; a metadata destination alone is insufficient. When a question blocks an approval, expose the answer path before presenting an unusable approval action.
- [ ] Distinguish an incubation awaiting its owning agent's decision from Marcelo's pending decision. The user-facing "sua decisão" label and Pessoal action require an actual operator decision; an owner-stage marker alone does not establish one.
- [ ] Verify authorized executor waits belong only to Execução, including agentless/system counters; active/uncertain/delivered work never becomes ready through labels.
- [ ] Finish only the bounded factual corrections and fixed catalog/legend documentation; do not change authority through GET serialization.
- [ ] Run classifier/triage domain tests, relevant frontend tests, complete frontend build/locales and desktop/mobile keyboard/browser verification; record results.
- [ ] Independently review and commit this read-only/operator-clarity slice with its exact source and publication status.

### Task 2: Prove and close authorized-wait/event recovery gaps

**Files:** `core/message_triage.py`, `api/routes/demand.py`, `core/agent_availability.py`, existing `core/dispatch_signal.py`; tests `app/tests/test_executor_wait_recovery.py`.

**Interfaces:** add `reconcile_queued_demand(db, demand, now) -> str` inside the existing Messages service only where needed. Outcomes are `waiting`, `ready`, `resolved`, `unchanged`; this helper does not launch a runtime. Existing reservation remains the sole start boundary.

- [ ] Write failing tests for a discarded wake signal, restart, quota reset, occupied executor release, and later compatible assignment to an unassigned authorized task.
- [ ] Run a recovery case with contextual/mission maintenance disabled and the dispatch wake deliberately discarded; concurrent periodic passes must still discover the persisted authorized work exactly once.
- [ ] Assert one persisted task and no new approval solely for a quota wait; unassigned work remains visible until a permitted assignment exists.
- [ ] Include an executable question-answer continuation with `reply_to_id`: let it follow the ordinary guarded queue, while completed informational replies stay inert. Do not blanket-reject all replies or grant the original task a missing authorization through its answer.
- [ ] Assert a deliberate future schedule is preserved; only an audited automatic quota postponement is eligible for earlier recovery after verified availability.
- [ ] Preserve runnable intent using existing message/schedule/assignment records. If automatic postponement needs provenance, record its original due time, reason and exact source version in the existing audit trail.
- [ ] Invoke reconciliation at the start of the existing `run_scheduled_dispatch_pass`, before its due+assigned selection. Scan bounded persisted executable waits independently of `scheduled_at`/`target_agent_id`, apply current authority/proof/uncertainty gates, commit recovered intent, then use the ordinary reservation path. The existing periodic caller is the guaranteed entry point; no model or new worker is required for this recovery.
- [ ] Revalidate delivery, current authorization, uncertainty, dependencies and assignment before returning ready; refresh analysis on changed facts.
- [ ] Run `ENVIRONMENT=test .venv/bin/pytest -q app/tests/test_executor_wait_recovery.py app/tests/test_agent_failover.py app/tests/test_dispatch_signal.py` from backend; require all green and one run identity under concurrent wake/sweep.
- [ ] Include standalone service/personal work without a mission: preserve its owner/reason/next reevaluation through restart, executor absence and later permitted assignment.
- [ ] Review and commit independently before changing manager autonomy.

### Task 3: Harden existing manager commands and mission event consumption

**Files:** `api/routes/mission_cycle.py`, `core/mission_cycle.py`, `core/command_receipts.py`, `api/schemas/mission_cycle.py`, existing `mission_task.py`/task command cores; tests `app/tests/test_mission_cycle_recovery.py`.

**Interfaces:** reuse `request_hash`, `begin_command`, `record_command` and existing actor-scoped command keys. Add request field `DecisionIn.expected_context_version: int | None`; require it for a new automatic manager effect while retaining documented human/legacy compatibility. Extend `request_mission_cycle(..., commit: bool = True)` so the periodic pass can commit its cursor and durable cycle request atomically; wake only after commit. Any recoverable decision phase belongs to the existing decision record.

- [ ] Reproduce G3/G4 with injected failures: after cursor calculation, after nested effect/receipt commit, and before final decision audit/context completion.
- [ ] Assert same actor/key/payload yields the same effect; changed task/executor/parameters returns 409; stale expected context refuses the command.
- [ ] Hash the complete immutable request, including path, task/action/parameters and the caller-supplied expected context version; never hash mutable freshly read server context as request identity. After current actor authorization, replay an identical completed receipt before checking whether the current context advanced. Validate expected context before a new effect; recover incomplete outer facts from the existing inner receipt/run instead of applying the action again.
- [ ] For database-only effects, commit effect/receipt/decision/audit together. For external starts, preserve the existing early durable run identity and explicitly recover the completion phase; never retain database locks during host/model calls.
- [ ] Commit the mission event cursor with the persisted request/rerun intent. A crash before commit leaves the event discoverable; a crash afterward leaves a recoverable cycle.
- [ ] Add a narrowly scoped migration only if the existing decision status constraint needs an explicit pending phase; preserve old rows/API compatibility and verify rollback on a restored test copy.
- [ ] Run recovery tests plus `app/tests/test_mission_cycle.py`; review before commit and keep automatic cycles disabled until Task 7.

### Task 4: Make the existing decision-aid button useful for real decisions

**Files:** `core/message_triage.py`, `core/message_triage_analysis.py`, existing Personal decision rendering; tests `app/tests/test_message_decision_aid.py`, `tests_unit/test_message_triage_analysis.py`.

**Interfaces:** retain **Analisar e encaminhar**, typed `TriageSuggestion`, current jobs and deterministic decision gates. Contextual advice may enrich summary/reason/recommendation only; it cannot change authorization, destination, selected action or task state.

- [ ] Reproduce a pending approval and blocking question being omitted from contextual model input.
- [ ] Supply bounded relevant request/question/context/evidence under the existing per-domain identity; keep untrusted content out of system instructions.
- [ ] Persist useful objective, requested decision, consequences/risks and recommendation when the provider succeeds. Preserve deterministic fallback and guarded human actions during outage.
- [ ] Test a model suggesting approve/resolve/queue cannot perform those actions; a changed source/answered question invalidates old advice; private contexts remain partitioned.
- [ ] Run decision-aid/analyzer tests and Personal UI tests; review and commit with no new approval flow.

### Task 5: Tighten contract-compatible reassignment and protected parallelism

**Files:** `core/agent_failover.py`, `core/dispatch_targets.py`, existing mission task eligibility/assignment helpers and registry models; tests `app/tests/test_executor_eligibility.py`.

**Interfaces:** one deterministic `executor_eligibility(db, demand, candidate_id) -> list[dict]` returns blocking reasons. Reuse it in suggestions, permitted substitution and reservation; no new agent pool or authority registry.

- [ ] Write failing cases for free-but-incompatible role, private identity mismatch, missing permission, author-as-reviewer, fixed executor and executor-bound approval.
- [ ] Reuse registered project membership, required skills, source policy and current approval/baseline checks. If compatibility facts are absent, retain the task in a reasoned wait rather than guessing from its body.
- [ ] Test two independent canonical tasks run concurrently; an unfinished dependency or shared protected checkout/branch/publication target blocks the conflicting task only.
- [ ] Preserve the current target-policy boundary: worktree/branch exclusivity is mission-scoped; production publication targets apply to all canonical tasks. An extension to standalone Messages is a separately identified policy decision, not an implicit change in this hardening slice.
- [ ] Require managers to declare dependencies/targets through existing task APIs; messages reference those records instead of maintaining another DAG.
- [ ] Run eligibility/failover/dependency/target regressions; independently review and commit.

### Task 6: Qualify cross-agent and Telegram continuity

**Files:** `core/agent_questions.py`, `api/routes/operations.py`, `api/schemas/operations.py`, existing `host-bridge/forgehub_messages_mcp.py`; tests `app/tests/test_agent_questions.py`, `app/tests/test_channel_handoff_recovery.py`.

**Interfaces:** preserve `origin_demand_id`, question identity, authorized relay, existing answer/resume behavior and feedback channels. Reuse command receipt hashing with a stable caller key where missing; do not deduplicate arbitrary work by textual similarity.

- [ ] Test Telegram/MCP request replay, delivery timeout, late answer, wrong relay, quiet-window delay, and concurrent repeated answer.
- [ ] Inject a pull-consumer crash after inbox acknowledgement but before recorded execution. Recover through the existing run/reservation/progress contract; retain original identity and block replay when the outcome is unknown. A consumed/read timestamp is neither successful execution nor proof that nothing started.
- [ ] Assert one canonical question/response task for one command identity; changed payload conflicts; a valid answer resumes only linked work and respects the existing scope/approval.
- [ ] Cover standalone personal/service work without a mission, including its Telegram answer and a delivered result suppressing obsolete diagnostics/feedback.
- [ ] Preserve agent charter responsibility, channel provenance and original task/run links through every handoff; acknowledgement alone never marks execution complete.
- [ ] Keep all transport tests isolated/stubbed, with zero real external messages; run existing question/feedback/bridge regressions.
- [ ] Review and commit the continuity slice without changing which agents are authorized to speak for Marcelo.

### Task 7: Close the loop through 24x7 supervision and accepted delivery

**Files:** `core/mission_cycle.py`, `core/mission.py`, `core/mission_records.py`, `api/routes/mission_records.py`, existing operations/mission views; tests `app/tests/test_mission_delivery_recovery.py`.

**Interfaces:** reuse `watchdog_findings`, `run_mission_cycle_watchdog`, `request_mission_cycle`, task review/evidence APIs, dossier and governed mission acceptance. 24x7 aggregates these same IDs and asks their owner to reevaluate; it does not maintain another task status.

- [ ] Test an idle active mission with open work, missing cycle, exhausted executor, unresolved human decision and recovered service; every wait has an owner/reason and a reevaluation path.
- [ ] Include a mission stalled during planning/P1–P8, with missing cycle and unanswered planning review/request. The current watchdog watches active/verifying only; extend its existing stage-aware supervision deliberately while preserving a recorded pause or legitimate human wait.
- [ ] Let safe missing-cycle recovery request the existing cycle once; preserve explicit pause/locks and escalate only real authority/resource decisions. Alerting alone is not recorded as recovered work.
- [ ] Run one isolated mission through independent parallel work, dependent work, quota wait, manager decision, human approval, correction, independent review, integration, dossier and acceptance.
- [ ] Assert a completed diagnosis, DONE report, manual archive or cancelled required task cannot substitute for proven approved acceptance criteria. Partial Moodle scope remains open.
- [ ] Verify applicable product/service criteria by their approved methods, exact artifact/version/content integrity, runtime health and rollback evidence. Never invent thresholds or auto-accept a mission.
- [ ] Negative tests: missing artifact checksum, forged matching caller metadata without trusted bytes, stale artifact/version, and evidence invalidated by approved-scope/content change must not establish dossier integrity or release acceptance. Reuse trusted stored-content/evidence verification; add only the bounded dossier guard needed when current metadata comparison is insufficient.
- [ ] Review the complete qualification dossier. Publish exact reviewed artifacts with tested backup/restore and independently verifiable recovery steps; record actual enabled flags.
- [ ] Enable only the qualified scope using existing controls; verify one real authorized flow and its state projections without synthetic production work. Keep unqualified manager autonomy disabled.

## Acceptance scenario index

| Scenario | Tasks proving it |
|---|---|
| Porthus lacked quota; Aramis already delivered | 1/2: delivery proof precedes reassignment, source archived with history |
| Authorized task waits for quota or a free executor | 1/2/5: Execução label, persistent intent, eligible reassignment/resume |
| Event/callback/worker is lost or restarted | 2/3/7: periodic reconciliation and recoverable commands |
| Parallel workers contend for the same target | 5: dependency and resource guards, one effective reservation |
| A real human decision spans large contexts | 4: existing button provides fresh bounded advice; human retains authority |
| Telegram/agent handoff repeats or arrives late | 6: canonical identities, relay policy and command replay |
| Runtime outcome is unknown | 2/3/5/7: original run identity preserved; no blind retry |
| All task runs finish but acceptance is incomplete | 7: mission remains open until evidence/review/dossier/acceptance |

## Review and execution boundary

The requested deliverable for this checkpoint is a written, independently reviewed maturation
plan. Review it against existing contracts and implementation evidence; separate confirmed gaps
from hypotheses needing reproduction. Record corrections and unresolved policy questions in
`docs/reports/2026-11-09-mission-messages-plan-review.md` before implementing a broader management
activation. Existing prepared UI/technical fixes remain distinguishable from that future activation.

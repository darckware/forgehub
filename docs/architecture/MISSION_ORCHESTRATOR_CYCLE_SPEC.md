# M0 — Orchestrator decision cycle (Operação 24x7) and multiple missions

**Status:** proposed (M0.SPEC). Decided by Marcelo on 2026-10-29: "na missão o agente precisa tomar
decisões, agendar tarefas na Operação 24x7 com o objetivo de finalizar as tarefas da melhor forma
possível" and "posso ter várias missões cadastradas" (04 §6–§7). Part of
[MCP_MISSION_TOOLS_SPEC.md](MCP_MISSION_TOOLS_SPEC.md); labels as defined there (§0.1). Proposed slice:
M0.8 (open decision D-M0-1). Onda 1 runs at **N0** (08); nothing here raises the level.

## 1. Principle

The cycle is the orchestrator **choosing** among actions that already exist as guarded routes. It
adds no executor and no bypass: Messages remains the only executor, every action passes the M0.6a/b
guards, the baseline approval and the publication gate. The backend computes the facts and the
candidate actions deterministically; the orchestrator agent (Athos, a Hermes agent on a free model —
treat its verdicts as proposals the guards re-check) picks, gives a reason, and calls the tool.

## 2. How each active mission gets a cycle

### 2.1 Scheduled trigger — reuse Operação 24x7 routines

On `ready → active` (main spec §3) the backend creates one `AgentRoutine`
[EXISTS model backend/app/db/models/operations.py:79] for the mission:
`agent_id = orchestrator_agent_id`, `kind = "coordination"` (already in `ROUTINE_KINDS`
[backend/app/db/models/operations.py:46]), `schedule = "*/30 * * * *"` (configurable per mission, min 15 min),
`deadline_minutes = 20`, `title = "Ciclo da missão <name>"`, `instructions` = fixed text that tells the
orchestrator to call `get_mission_cycle(project_id)` and act only through mission tools, plus a link
column [PROPOSED `agent_routines.mission_project_id` UUID FK projects, null] so the routine is found and
toggled with the mission. `run_routine_generation_pass` [EXISTS backend/app/api/routes/operations.py:239]
already turns each due occurrence into a self-addressed Messages Task for the agent and wakes the
dispatcher; `run_routine_sync_pass` [EXISTS :290] copies the outcome back. Paused/completed/cancelled
→ `enabled=false` (no deletion; runs keep history).

### 2.2 Event triggers [PROPOSED]

`request_mission_cycle(db, project_id, reason, source_ref)` in `core/mission_cycle.py` (new) is called
after commit (best effort, never inside the guarded transaction) on:

| Event | Hook point |
|---|---|
| task transitions (done/deployed/blocked/cancelled) | `update_task` [EXISTS backend/app/api/routes/task.py:388] and the completion guard call sites |
| execution reported/verified/failed | `report_task_execution` [PROPOSED], `run_evidence_verification_pass` [EXISTS backend/app/core/task_evidence.py:164] |
| review decided | `PATCH /orchestration/reviews/{id}` [EXISTS backend/app/api/routes/orchestration.py:496] |
| dispatch finished or failed | `_finalize_dispatch` [EXISTS backend/app/api/routes/demand.py:2092], `_fail_dispatch` [EXISTS :1664] |
| run deadline at 80 % / passed | `run_dispatch_timeout_pass` [EXISTS backend/app/api/routes/demand.py:1721] |
| executor availability returns | `agent_availability.unavailable_until` reached (§3.3) |
| Marcelo answered a blocking question | `POST /operations/questions/{id}:answer` [EXISTS backend/app/api/routes/operations.py:1124] |
| CR approved / baseline replaced | governed `:decide` `project_plan` branch [EXTEND backend/app/api/routes/governed_approval.py:64] |

It reuses the run-now path (`_materialize_occurrence` [EXISTS backend/app/api/routes/operations.py:195], as
`run_routine_now` [EXISTS :816] does) with `occurrence_at = now`. **Debounce:** at most one open cycle
per mission — if the mission's last cycle Messages Task is not terminal, the call only sets
`project_missions.cycle_rerun_requested = true` [PROPOSED column]; when that cycle finishes,
`run_routine_sync_pass` sees the flag and materializes one more. Events while the mission is paused or
the cycle is locked (§5) are recorded and dropped.

### 2.3 What one cycle does

1. The orchestrator calls **`get_mission_cycle(project_id)`** [PROPOSED MCP tool →
   `GET /api/v1/missions/{project_id}/cycle` PROPOSED], which returns: a `cycle_id` (the routine run id),
   the executions board (screen spec §3.2), and `proposals` — the deterministic candidate actions of §3,
   each with `action`, target, `reason_facts`, `autonomy_required`, and whether the caller may execute it
   at the mission's level.
2. For each action it takes, it calls the corresponding tool with `cycle_id`, `reason` (required,
   1..2000 chars) and an `idempotency_key`. The route records a `mission_decisions` row (§4) in the same
   transaction as the effect.
3. Proposals it does not take may be explicitly `defer`red with a reason (recorded, `status='deferred'`)
   — silence is allowed but visible as "não decidido" on the timeline.
4. It ends with the completion-report `STATUS:` line (existing contract, `core/completion_report.py`);
   `PARTIAL`/`BLOCKED` become a known failure of that cycle run (existing semantics), visible on the
   board, and the next scheduled cycle runs normally.

## 3. Actions

Columns: **N0** = allowed to the orchestrator in Onda 1; **N1–N3** = when the level would allow it
alone (informative; not enabled in M0); **Gates it cannot bypass**; **Undo/lock** (§5).

| Action | Deterministic proposal when | Tool / route | N0 | Higher levels | Gates it cannot bypass | Undo |
|---|---|---|---|---|---|---|
| **Dispatch** a ready task | task `ready` (screen §4), baseline current, executor free and available | `dispatch_task` → `POST /tasks/{id}/dispatch` [EXISTS backend/app/api/routes/task.py:946, EXTEND] | yes, explicitly per task (04 §1) | N2: system may dispatch low-risk tasks without the orchestrator | M0.6b baseline, mission state, dependencies, assignment+membership, target serialization, capacity, one-per-agent | before start: archive the demand (`decide_demand(archive)` [backend/app/core/demand_workflow.py:186]); after start: none (uncertain/`confirm_inactive` path only) |
| **Schedule** with `scheduled_at` | executor unavailable until T (§3.3), or a serialized target frees at a known time, or Marcelo's preferred window | `dispatch_task(scheduled_at=T)` | yes | — | same, evaluated at start time by `reserve_dispatch` | clear schedule = archive/restore demand before T |
| **Reassign** | executor unavailable > threshold (default 2 h) or failed twice on the same task, and another active member with an executor role is eligible | `assign_task` (main spec §5.5) | yes, only to existing eligible members, reason required | N1+: may propose new members; adding a member stays `mission.manage` | reviewer ≠ executor; nothing in flight; code roles only external runtimes; assignee is not in the baseline hash (D-M0-3) | reassign back |
| **Request review** | latest execution `verified` and no review | `request_task_review` (main §5.11) | yes | — | reviewer independent, `can_review` | cancel the review request (archive its message; review row `cancelled` [PROPOSED value in `REVIEW_STATUSES` backend/app/db/models/orchestration.py:59]) |
| **Refuse / return for correction** | review `changes_requested`, evidence failed, or criterion `failed` | `return_task_for_correction` (main §5.12) | yes, never on its own executed work; reason required | — | cannot mark done/accept; correction redispatch is a separate explicit dispatch | re-request review |
| **Reprocess** a known failure | demand `failed` (known), attempts < `retry_limit` | existing `POST /demands/{id}:reprocess` [EXISTS backend/app/api/routes/demand.py:687] with the orchestrator's `agt_` [EXTEND auth] | yes, within the existing budget | — | never for uncertain outcomes; `authorize_retry` (raising the budget) stays Marcelo's [backend/app/api/routes/demand.py:1190 is admin-only] | — (new attempt is recorded) |
| **Serialize shared targets** | two ready tasks share a worktree/branch/publish target | not a separate tool: `reserve_dispatch` already refuses the second (main §4.3); the orchestrator chooses the order by dispatching one and **scheduling** the other | yes (ordering) | — | the backend serialization itself cannot be turned off by the orchestrator | — |
| **Ask Marcelo** | decision above N0 (new member, CR, budget, deadline, retry budget, production publication, conflict `publish_missing_production`) or ambiguous facts | existing MCP `ask_marcelo` [EXISTS host-bridge/forgehub_messages_mcp.py:625] → `POST /operations/agent-questions` [EXISTS backend/app/api/routes/operations.py:1004] with `blocking=true` and `origin_demand_id` = cycle message | always | — | a blocking question already holds the linked work (`ensure_workflow_allowed` [backend/app/core/demand_workflow.py:78-92]) | Marcelo answers/cancels (`/operations/questions/{id}:answer|:cancel` [EXISTS :1124,:1139]) |
| **Pause mission** | mission blocked: all remaining tasks blocked/uncertain, or deadline passed, or budget exceeded | `POST /missions/{p}:transition` → `paused` with reason `blocked:<kind>` [PROPOSED] | only when blocked (04 §6) | — | resume, cancel, accept, plan approval are Marcelo's | Marcelo resumes |
| Approve plan / CR, accept mission, cancel mission, publish to production, raise autonomy, grant delegation | — | — | **never** | never by the cycle | baseline approval, acceptance (`human_only`), publication gate (M0.R/Hephaestus) | — |

### 3.1 Contention between missions

Proposals are computed across all active missions the orchestrator coordinates; when two of them want
the same agent, the proposal for the lower-priority mission is `schedule` (after the other's expected
end) or `wait`, never a parallel second run (one-per-agent rule [EXISTS `_agents_already_running`
backend/app/api/routes/demand.py:1638]).

### 3.2 Deadlines

A running execution past 80 % of `dispatch_deadline_at` yields a proposal "check progress" (read
agent activity; no action); past the deadline the existing timeout pass already fails it
(`DISPATCH_TIMEOUT_MINUTES`), after which "reprocess" or "reassign" is proposed.

### 3.3 Executor availability (quota) [PROPOSED]

`agent_availability(agent_id PK FK agents, unavailable_until timestamptz, reason String(200),
source_demand_id FK agent_demands null, recorded_by String(150))`. Written by:

- `_finalize_dispatch`/`_fail_dispatch` [backend/app/api/routes/demand.py:2092,1664] when the runtime output matches a
  deterministic, per-runtime usage-limit pattern (e.g. Claude Code "resets 3:30am", Codex quota errors;
  patterns versioned in `core/agent_availability.py` with fixtures from real outputs, timezone of the
  host) — on no match nothing is written (no guessing);
- Marcelo or the orchestrator manually (reason required).

Effects: `reserve_dispatch` treats the agent as busy until `unavailable_until` (item stays queued,
`AGENT_UNAVAILABLE`); the cycle proposes `schedule` at `unavailable_until + 5 min` for that agent's ready
tasks (the 2026-10-28 case: Porthus stopped at 00:15 with "resets 3:30am" → M0.SPEC rescheduled to
03:35 automatically, not on someone's memory). When the time passes, an event triggers a cycle (§2.2).

### 3.4 Continuation until the end of the mission [PROPOSED, Marcelo 2026-10-29]

Marcelo, 2026-10-29: "esse processo de monitoramento das execuções das tarefas é que precisa ter a
missão, para manter a continuação da execução até o final da missão". On 2026-10-28/29 Wave 1 ran
by hand (dispatch, watch, re-verify, request review, merge, dispatch the next task); four steps of that
loop are not covered above and are part of M0.8:

1. **Integrate.** A task whose review is `approved` is not finished while its branch is outside the
   mission's mainline. Action `integrate`: the executor (never the reviewer) merges the approved commit
   into the mainline (`develop`) by the existing git flow; a conflict returns the task to the executor
   with the conflicting files listed, and the integrated result is re-checked (validator/tests named in
   the task) before the next dependent task is dispatched. Integration never publishes: production stays
   behind the publication gate (§3, D-M0-2, D-M0-7). Decision row `action='integrate'`.
2. **Independent re-verification before review.** Before `request_review`, the cycle re-runs the
   evidence a task declares (typed verifiers of M0.6a: git, file, db, test command in the test
   environment) as a principal other than the executor, and, for tasks that touch an environment,
   compares an environment sentinel (row counts and id hashes of named tables) taken before dispatch and
   after delivery. A mismatch is `return`, not `request_review`.
3. **Infrastructure failure is not rejection.** A run or review that ends on a runtime/infra error
   (quota or usage limit, provider 4xx/5xx such as agy `INVALID_ARGUMENT`, permission auto-denied,
   timeout without output) is classified `infra_failure`: the cycle `reprocess`es once, then `schedule`s
   at the known reset time (§3.3) or reassigns the **same role** (a review stays a review by another
   independent reviewer). It never counts as `changes_requested` and never as the executor's failure.
4. **Watchdog of the cycle itself.** Every active mission must have a cycle run at least every
   `MISSION_CYCLE_MAX_GAP` (default 30 min) and, while not paused, either a task in flight, a task
   scheduled, or a recorded `defer`/`ask_marcelo` reason. A gap or an idle mission without a reason
   raises an Operação 24x7 alert (A.2 lost-routine path) and appears on the executions screen (M0.7).
   The mission only stops at `completed` (Marcelo's acceptance), `cancelled` or `paused`.

Planned tests: `test_approved_task_not_done_until_integrated`, `test_integration_conflict_returns_to_executor`,
`test_reverify_mismatch_returns_instead_of_review`, `test_infra_failure_reprocessed_not_rejected`,
`test_review_infra_failure_reassigned_to_independent_reviewer`, `test_idle_active_mission_without_reason_alerts`.

## 4. Decision record [PROPOSED table `mission_decisions`]

| Column | Note |
|---|---|
| id UUID PK | |
| mission_project_id FK projects | |
| cycle_id UUID null | routine run id; null for Marcelo's direct actions on the screen |
| action String(40) | CHECK in (`dispatch`,`schedule`,`reassign`,`request_review`,`return`,`reprocess`,`integrate`,`reverify`,`ask_marcelo`,`pause`,`defer`,`undo`,`lock`,`unlock`) |
| task_id, demand_id, review_id, question_id | nullable FKs to what the action touched |
| reason Text not null | required for every row |
| facts JSONB | the proposal's `reason_facts` the decision relied on (board snapshot hash + the specific values) |
| autonomy_level String(2) | level in force (N0) |
| actor_type, actor_id, actor_name | authenticated principal |
| authority_source, delegation_id | from `authorize_action` |
| status String(20) | CHECK in (`applied`,`refused`,`deferred`,`undone`) |
| refusal_code String(60) null | guard code when refused (the attempt is recorded too) |
| undone_by_decision_id FK self null | |
| idempotency_key String(150) | unique per actor |

Every row also emits an `AuditEvent(entity_type="mission", event_type="mission_decision_<action>")`
so the generic audit views see it. The screen's timeline (screen spec §3.2) reads both.

## 5. Where Marcelo undoes or locks

| Control | Route [PROPOSED] | Effect |
|---|---|---|
| Undo a decision | `POST /api/v1/missions/{p}/decisions/{id}:undo` (reason) | applies the inverse listed in §3 when still possible (e.g. archive a not-yet-started scheduled demand, reassign back); otherwise 409 `UNDO_NOT_POSSIBLE` with why (e.g. run already started → use investigate/confirm). Writes an `undo` decision |
| Lock the cycle (mission) | `POST /api/v1/missions/{p}/cycle:lock` `{until?, reason}` / `:unlock` | cycle keeps running read-only: `get_mission_cycle` returns proposals with `allowed=false`; every mission tool from the orchestrator → 409 `CYCLE_LOCKED`. Marcelo's own screen actions still work |
| Lock one task | `POST /api/v1/missions/{p}/tasks/{t}:lock-cycle` `{until?, reason}` / `:unlock-cycle` | the orchestrator cannot dispatch/schedule/reassign/return that task |
| Pause mission | main spec §3 | no dispatch, no cycle nagging |
| Revoke delegation | existing `POST /governed/authority-delegations/{id}:revoke` [EXISTS backend/app/api/routes/governed_approval.py:154] | immediate for the next call |

Locks are stored in [PROPOSED] `mission_cycle_locks(id, mission_project_id, task_id null, locked_by,
reason, locked_until null, released_at null)`. Only Marcelo (admin) can lock/unlock/undo in M0.

## 6. Multiple missions (04 §6)

### 6.1 Priority in agent contention

`project_missions.priority` (1 = most urgent, default 100). `run_scheduled_dispatch_pass` [EXISTS
backend/app/api/routes/demand.py:1854] currently orders due items only by `scheduled_at` [:1879]. [EXTEND, M0.8]: order by
`(effective_priority, scheduled_at)` where `effective_priority` = the mission's priority for demands
whose task belongs to a mission (via `origin_id → task → planning item/CR → project → project_missions`,
or the mission linked to the executor project — the **highest** priority of the missions it serves),
and 100 for every other demand (routines, ad-hoc tasks) — so non-mission work is not starved by
default. The existing selection loop then naturally gives the contested agent to the higher priority
(it marks the agent busy on the first pick [:1907-1908]). The global cap and one-per-agent rule are
unchanged. No aging in M0; the board's "Agentes disputados" panel shows work waiting > 2 h for a
contested agent so Marcelo can reprioritize (priority change = `PATCH /missions/{p}` [PROPOSED], admin,
audited).

### 6.2 Limit of active missions per orchestrator

Setting `MISSION_MAX_ACTIVE_PER_ORCHESTRATOR` [PROPOSED, `forgehub.config`/Settings → System defaults,
default 2, max 10]. `ready → active` is refused with 409 `ORCHESTRATOR_AT_CAPACITY` (listing its active
missions) when the orchestrator already has that many in `active`/`verifying`/`awaiting_acceptance`.
Paused missions do not count. Membership validation (main §5.2) also refuses naming an orchestrator who
is at capacity for a mission about to start.

### 6.3 Dependency between missions

[PROPOSED] `mission_dependencies(id, mission_project_id FK, depends_on_mission_project_id FK,
UNIQUE(pair), CHECK(different))`, registered while the mission is `draft`/`ready` by Marcelo or the
orchestrator (`mission.manage`); cycle detection with the same recursive-CTE + advisory-lock pattern as
`create_task_dependency` [EXISTS backend/app/api/routes/task.py:708-736]. `ready → active` is refused (409
`MISSION_DEPENDENCY_OPEN`) until every dependency is `completed`. A cancelled dependency blocks too
(Marcelo removes the dependency explicitly, audited). Completing a mission triggers a cycle for its
dependents.

### 6.4 Listing and filtering

Screen spec §8 (`GET /api/v1/missions` with state/orchestrator/agent/conflict filters, default sort
active → priority → deadline, "Agentes disputados" panel). The Cockpit shows missions in its tree via
`project_type='mission'`; the Athos briefing reads the same list endpoint.

## 7. Tool contracts added for the cycle [PROPOSED, M0.8]

| Tool | Route | Actor | Notes |
|---|---|---|---|
| `get_mission_cycle(project_id)` | `GET /api/v1/missions/{p}/cycle` | orchestrator (`mission.orchestrate`) | read; returns `cycle_id`, board, proposals; 409 `CYCLE_LOCKED` info flag (still returns data) |
| `defer_mission_proposal(project_id, cycle_id, proposal_id, reason, idempotency_key)` | `POST /api/v1/missions/{p}/decisions` (`action=defer`) | orchestrator | records a non-action |
| `pause_mission(project_id, reason, cycle_id, idempotency_key)` | `POST /api/v1/missions/{p}:transition` | orchestrator only with `reason` starting `blocked:` | resume is Marcelo's |
| `set_agent_unavailable(agent_id, until, reason, idempotency_key)` | `PUT /api/v1/agents/{id}/availability` | orchestrator, Marcelo | §3.3 |
| existing/proposed mission tools | main spec §5.5–§5.12 | — | all accept optional `cycle_id`; with it the decision row links to the cycle |

Errors, idempotency, audit and the disabled-flag rollback follow main spec §0.3–§0.6. Rollback of M0.8:
disable the mission routines (`enabled=false`) and set `MISSION_TOOLS_ENABLED=false`; decisions and
locks remain as history; the priority ordering change is a code revert behind the deploy gate.

## 8. Limits restated (04 §7)

- Every decision is recorded with a reason (§4); refusals are recorded too.
- Nothing bypasses baseline approval, the completion guard or the publication gate.
- N0 in Onda 1: the orchestrator decides only the rows marked "yes" in §3; everything else is a
  question to Marcelo.
- Marcelo can undo or lock any decision from the screen (§5).
- With several active missions each has its own cycle; agent contention resolves by priority (§6.1).

## 9. Planned tests

Backend `backend/app/tests/test_mission_cycle.py` (test database, simulated runner from T.3):

| Test | Proves |
|---|---|
| `test_routine_created_on_activation_and_disabled_on_pause` | one coordination routine per active mission; toggled, never deleted |
| `test_event_triggers_debounced` | burst of events → one open cycle + rerun flag → exactly one more cycle |
| `test_proposals_deterministic` | same fixture state → same proposals and order |
| `test_dispatch_from_cycle_goes_through_guards` | stale baseline / paused / target busy → refused, decision row `refused` with code |
| `test_schedule_on_quota_reset` | fixture output "resets 3:30am" → availability 03:30 → schedule 03:35; `reserve_dispatch` keeps it queued before |
| `test_unmatched_quota_text_writes_nothing` | no guessing |
| `test_reassign_never_makes_reviewer_executor` | refused |
| `test_orchestrator_cannot_accept_approve_cancel_or_raise_retry_budget` | each → 403 |
| `test_pause_only_when_blocked` | non-`blocked:` reason → 403; resume by agent → 403 |
| `test_every_decision_recorded_with_reason` | missing reason → 422; applied/refused/deferred rows exist |
| `test_undo_paths` | undo scheduled dispatch archives the demand; undo after start → 409 `UNDO_NOT_POSSIBLE` |
| `test_cycle_lock_blocks_tools_but_not_marcelo` | |
| `test_priority_ordering_in_scheduled_pass` | contested agent goes to the higher-priority mission; non-mission work keeps default 100 |
| `test_active_missions_limit_per_orchestrator` | third activation refused at default 2; paused not counted |
| `test_mission_dependency_cycle_and_gate` | cycle refused; dependent cannot activate until dependency completed |
| `test_n0_only` | any attempt to set level ≠ N0 refused |

Unit `backend/tests_unit/test_agent_availability_patterns.py`: each runtime's limit message fixture →
expected timestamp in host timezone; near-miss strings → no match.

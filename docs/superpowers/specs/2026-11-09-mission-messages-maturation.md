# Maturing the existing Mission, Messages and 24x7 workflow

**Status:** context consolidation and gap analysis requested by Marcelo; not a replacement architecture.
**Scope:** strengthen existing components, authority boundaries, recovery and evidence-based delivery.

## Responsibilities

| Component | Responsibility | Authoritative records |
|---|---|---|
| Mission and its designated manager | Objective, plan, task priority/dependencies, agent coordination, evidence assessment and next permitted action | ProjectMission, ProjectTask, TaskDependency, assignments, baseline, reviews, MissionDecision |
| Messages | Administrative execution lifecycle: queued work, reservation, dispatch, waits, run tracking, results and handoffs | AgentDemand and its run/result, delivery audit, analysis jobs/results |
| Operação 24x7 | Aggregate supervision of missions, tasks, executors, waits, health and recovery conditions; request the existing owner's reevaluation | Existing routines, mission cycle/watchdog, notifications and shared task/run IDs |
| Pessoal | Marcelo's actual authorization and decision requests, with context and the existing guarded actions | AgentQuestion and current source-specific approval/review records |

Do not create another general orchestrator, independent task queue, approval registry, agent identity,
or copy of task completion. Messages applies canonical task dependencies; prose alone does not
create an execution dependency. Standalone authorized service/personal work retains its existing
owner and source-specific rules without inventing a mission for every message.

## Required outcome

An authorized mission must be actively followed through delivery and acceptance. Every unresolved
task must remain identifiable with an owner, a factual state, a reason for waiting and a reevaluation
path. Lack of an event, quota or executor must not make it disappear. External failures may delay
delivery; they must produce accountable recovery/escalation rather than a false completion.

Mission completion means the approved result was delivered and its acceptance criteria were proven,
not merely that all runs returned DONE. Required review, integration, service checks, dossier and
Marcelo's acceptance remain binding.

## Operator experience already requested

- Keep authorized executor waits in existing Messages **Execução**, tagged **Aguardando executor**.
- Explain quota, occupied/unavailable/missing executor separately from a new authorization request.
- Use a fixed, localized label catalog; tentative duplication/obsolescence must remain tentative.
- A legend icon opens a right-side, keyboard-accessible panel documented by Messages group.
- Actual pending authorization/decision includes a link to the correct Pessoal destination:
  Tarefas dos agentes, Incubações or Aprovações Moodle.
- Preserve **Analisar e encaminhar** as the existing decision aid and operational analysis action.
  For a pending human decision it must summarize objective, context, evidence, consequences and
  recommendation, while keeping the actual decision and its guarded action with Marcelo.

## State invariants

1. `AgentDemand.dispatch_status` describes an attempt; `TaskExecution` describes execution and
   evidence; `ProjectTask.status` describes accepted task progress. Labels project those facts.
2. Reading/acknowledging a message does not prove execution. Diagnosis completion does not resolve
   the original problem. Archiving does not prove success.
3. Current verified delivery blocks duplicate execution, including derivative failure checks and
   obsolete feedback, even if contextual analysis is disabled.
4. Authorized work remains persisted across executor waits. Preserve its intended due time and
   current authorization; do not require a new approval merely because quota was exhausted.
   Executor-bound approvals and fixed reviewer/mission rules still govern reassignment.
5. Parallelism requires both canonical dependency eligibility and absence of protected resource
   conflicts. A free agent by itself does not establish task independence.
6. Every external start uses the existing durable reservation/run ID. A timeout, lost callback,
   missing runner record or expired lease does not prove there were no side effects.
7. Repeated commands with the same actor/key/payload replay once; different payload or stale
   context must conflict. Effects and their decision/audit/context records must recover coherently.
8. Events accelerate progress. Periodic database reconciliation recovers missed events and restarts.

## Reevaluation paths

| Wait | Reevaluate on | Periodic fallback | Governing owner |
|---|---|---|---|
| Quota | Fresh verified availability/reset | Current dispatcher/analysis sweep | Existing assignment/dispatch policy |
| Occupied executor | Recorded run terminates | Current dispatcher sweep | Dispatcher capacity guards |
| Missing/unavailable executor | Eligible assignment/configuration changes | Existing mission cycle and queued-work scan | Designated manager within reassignment authority |
| Dependency | Canonical predecessor is accepted complete | Current dependency/mission checks | Task domain and manager |
| Service failure | Verified recovery or diagnostic outcome | Bounded retry/recheck policy | Responsible agent and existing runtime policy |
| Human decision | Current approval/answer is recorded | Pending-decision reconciliation | Marcelo through Pessoal |
| Unknown execution | Existing run reconciliation and explicit investigation | Run/completion monitor | Existing uncertainty gate; no blind replay |
| Mission idle | Missing cycle/open-work condition detected | Existing watchdog, followed by accountable recovery | 24x7 supervises; mission owner reevaluates |

## Evidence-backed gaps found in this repository

| ID | Severity / scope | Current gap | Existing implementation anchor |
|---|---|---|---|
| G1 | P0 for uninterrupted dispatch | Runnable selection requires assigned executor plus non-null due schedule; executor-wait labels do not independently establish durable runnable intent | `api/routes/demand.py:run_scheduled_dispatch_pass`, `core/message_triage.py:_apply` |
| G2 | P0 for decision aid | Deterministically pending approval/questions bypass contextual model analysis; generic fallback is safe but not sufficient decision support | `core/message_triage.py:process_next_analysis` |
| G3 | P0 before automatic manager activation | Mission decision replay checks action/project, not complete payload; nested commits can precede final decision facts/audit/context | `api/routes/mission_cycle.py:decide`, `_apply` and nested routes |
| G4 | P0 for event-loss recovery | Mission cursor is committed before cycle request; a crash between the two can consume an event without scheduling its cycle | `core/mission_cycle.py:run_mission_cycle_pass` |
| G5 | P1 for correct reassignment | Plain Messages failover uses runtime/status/availability plus exclusions; it is not a full specialty/privacy/permission matcher | `core/agent_failover.py:substitute_for`, `can_switch` |
| G6 | P1 for safe parallel work | Canonical dependencies and protected targets exist, but standalone Messages do not automatically declare a business DAG or checkout/publication targets | `core/task_dependencies.py`, `core/dispatch_targets.py` |
| G7 | P1 for accountable recovery | Mission watchdog records alerts; an alert alone does not establish that the owning cycle will recover or that a task has a next action | `core/mission_cycle.py:watchdog_findings`, `run_mission_cycle_watchdog` |
| G8 | P1 for clear operator state | Read state, attempt state, accepted task progress and archive can be confused; archived unverified work must not be labeled completed | `core/message_classification.py`, DemandOut and Messages UI |
| G9 | P1 for multi-channel continuity | Agent questions can be created through Telegram/MCP handoffs without a command replay key; repeat delivery must not create another pending decision or executable response | `api/routes/operations.py:ask_question`, `core/agent_questions.py:create_question` |
| G10 | P0 before enabling the new triage admission gate | A new question-answer continuation can carry `reply_to_id`, but queue admission currently rejects every reply; classification can also label an unexecuted reply completed | `core/message_triage.py:_apply`, `core/agent_questions.py`, `core/message_classification.py` |
| G11 | P0 qualification scenario for pull consumers | Inbox pulling stamps acknowledgement before work starts; a consumer crash after acknowledgement needs explicit reconciliation, without treating acknowledgement as completion or blindly replaying unknown work | `api/routes/demand.py:list_pending_for_agent` |

These are targeted hardening items, not reasons to replace the existing architecture. G3/G4 must
be verified with injected crash/replay tests rather than assuming a duplicate run always occurs.
G11 likewise needs a consumer-crash scenario establishing which existing run/progress contract
recovers that handoff; an acknowledged item may already have side effects.

## Agent contracts and Telegram

Route work through the registered responsibility/skill/permission contract, not simply to an
agent whose quota is free. Keep the original message/task/run and the manager's decision linked
across Telegram, ForgeHub and executor handoffs. Ordinary chat is not an authorization or a new
executable task. Delivery acknowledgement is not execution evidence.

Replayed transport/agent requests need a stable command identity and payload binding. An answer
updates one registered question and resumes its linked work through the existing guarded flow.
Only the authorized relay may record the answer for its Telegram conversation. Preserve quiet
hours and retryable delivery; transport uncertainty must not be mistaken for business refusal.
Qualification uses stubs/isolated tests and must not send real Telegram messages.

## Quality and closure

Before acceptance, require approved criteria with an objective verification method, linked task
evidence, required independent review, integrated deliverable, and applicable runtime checks.
For a product, cover its approved functional/security/performance/accessibility criteria. For a
service, cover its approved operational behavior, health/recovery and rollback evidence. Do not
invent new contractual thresholds; attach measurable criteria to the current mission baseline.

The dossier must identify exact artifact/version/evidence checksums and be traceable to accepted
scope. An evidence hash supplied in metadata without trusted content verification is not enough
to claim independent verification. Acceptance remains the existing governed decision.

## Rollout and current status

Read-only labels/legend do not grant autonomy or activate a mission cycle. Qualify the existing
technical recovery and command gates first; activate management only through its existing feature
flag and authorization after the relevant acceptance tests pass.

At this planning checkpoint: mission form fix and four reconciled Porthus archives are live;
production remains the reviewed `c86227f` artifact. The temporary staging pause was closed on
2026-11-09 at 16:59:31 UTC: existing background workers were restored and health/proxy checked;
Messages triage maintenance and `MISSION_CYCLE_ENABLED` remain false. Repository `d81933c` contains further verified delivery-consumer
guards; labels/legend and archival refinements are prepared but not yet published. These are
publication-state facts, not claims that the complete manager pipeline is already running.

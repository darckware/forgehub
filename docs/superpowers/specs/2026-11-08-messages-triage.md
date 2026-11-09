# Messages analysis and operator decisions

Approved by Marcelo on 2026-11-08 after the queue audit and Personal screen review.

## Result

Personal agent work is an exception/decision console, not a raw error inbox. Keep the existing
Moodle/incubation/task workflows and add four operator views: `decision` (Sua decisão),
`processing` (Em tratamento), `waiting` (Aguardando), `resolved` (Resolvidas). Preserve legacy
views for links/API compatibility. Default to decision; a newly failed attempt awaits system
analysis rather than becoming a human decision automatically. Real approvals and blocking
operator questions remain visible even if analysis is unavailable.

The primary button is **Analisar e encaminhar**. It queues a durable asynchronous analysis
over all pending records in the selected agent/context scope, not only the visible page.
Progress survives navigation/reload. A bounded background worker uses the same engine on
new/changed work; it is disabled under test and never enables the mission cycle.

## Analysis and authority

This is the central operational decision layer for Messages across agent tasks, service
operations and development handoffs. It reuses approvals, task dependencies, mission rules,
capacity limits and the existing dispatcher; it creates no competing authority or runner.
Separate observation/context, advisory analysis, deterministic policy decision, authorization,
dispatch and outcome verification. Persist every automatic transition with its policy/version,
exact source, actor, evidence and outcome so the operator can explain or reverse presentation
changes without losing execution history.

Enable through `MESSAGE_TRIAGE_ENABLED` at controlled publication. When enabled, reservation
requires a fresh triage decision permitting queueing; unanalysed/changed work waits for analysis.
The analyzer cannot bypass a mission baseline, approval, source-specific authorization or
an active/uncertain attempt. A model outage leaves work visibly waiting, not silently executable.
Legacy behavior remains available only with the feature disabled for staged rollback.

Jobs use persistent leases and bounded batches/retries, coalesce duplicate requests and recover
after restart. Network/model calls hold no database row lock. Apply each decision under a fresh
row lock with version and context checks. Repeated jobs must not repeat actions, spawn recursive
diagnoses or emit external messages. Maintain audit history even when the latest analysis changes.

Use ForgeRouter's existing per-agent chat helper with typed JSON output. Analyze internal work
under Athos; private Maia/Lara work uses its own identity/key and separate prompt batches. Task
bodies/results are untrusted data, never instructions or authorization for the analyzer. Give
the model no tools. Bound context and replies, validate message IDs against the supplied set,
and preserve an understandable degraded state on provider failures. Similar wording produces
a suggestion, never proof of completion or permission to repeat an operation.

Persist source version, summary, reason, recommendation, category, related record, proposed
action and applied outcome. A changed source invalidates its analysis. The backend rechecks
authorization, uncertainty, live execution, dependencies and exact source version before any
mutation. A completed diagnostic does not by itself complete its original task.

Automatic actions: attach/retire informational self-feedback; reconcile a completed Moodle
proposal only if persisted completion and an accepted DONE report agree; resolve a message
with an independently verified delivery registered against its exact content; keep already
authorized due work in the existing dispatcher. Never reset an uncertain run, invent a run,
replay a partial Moodle operation, auto-approve a request, accept a ProjectTask without its
review, or derive authorization from quoted text. Keep attempt evidence when resolving work.

Add an admin-only delivery registration command with git evidence checked by the existing
host evidence verifier. This records work completed outside its original Messages dispatch,
including another executor, against the current message fingerprint. It does not claim the
old run succeeded. Future dispatch admission refuses work with a valid resolved delivery.

Quota: use a bounded, fresh native Codex rate-limit observation from the actual runner home,
only after its current authentication metadata timestamp, to supersede an older usage-limit
record. Unknown windows, exhaustion, stale samples or other runtimes never clear a limit.
Record the observation and clearance without credentials or transcript text.

## UI

Reuse canonical Button, Select, Input, Table, ConfirmDialog, Markdown, i18n and TanStack Query.
Each analyzed row carries a short summary, reason, recommended next action and understandable
source context. Hide raw instructor keys behind details. Human decisions show what changes and
retain existing guarded approval flows. Archive remains secondary. Show actual analysis loading,
progress, completion, empty, retryable error and stale states with stable geometry. Use pt-BR,
en and es. Preserve the Moodle approval panel and filters/URL state.

## API contract

- `POST /api/v1/demands/agent-work/analyze` `{agent_id?: UUID, context?: string}` -> 202 job.
- `GET /api/v1/demands/agent-work/analysis` same scope -> latest job or null.
- `GET /api/v1/demands/agent-work/analysis/{id}` -> job.
- Job: `{id,status:queued|running|completed|failed,total,processed,applied,summary,error,
  created_at,started_at,finished_at}`. Duplicate active requests return the active job.
- Existing agent-work item adds `operator_state:decision|processing|waiting|resolved`,
  `display_context:string`, `analysis:null|{category,summary,reason,recommendation,
  proposed_action,related_message_id,evidence_refs,analyzed_at,applied_action}`.
- `POST /api/v1/demands/{id}/delivery` admin-only:
  `{expected_updated_at,evidence_ref:"git:<sha>",summary,executor_id?,related_message_id?}`.
  Verify on the recorded host working directory, preserve content fingerprint and audit.

## Boundary and operational acceptance

An unavailable executor, provider wait, missing external information, new operator decision,
diagnostic completion, verified work delivery and uncertain process outcome are distinct facts.
Releasing one blocker does not remove the others. Suggested related work must be verified by
identity/authority/evidence before any closure; text similarity never grants this authority.
Agent reassignment retains the existing `can_switch` and specialty/permission rules; a fixed
reviewer cannot become the author through automatic failover. Incubation analysis is not
authorization to start its implementation.

Operational acceptance must demonstrate: a delivered item never reruns after quota recovery;
one scoped manual job processes beyond UI pagination; fresh incoming work is analyzed before
dispatch; duplicate starts produce one job/action; a stale result cannot change new content;
service and quota waits remain separate; only operator decisions occupy the default screen;
provider failure/restart is visible and recoverable; the whole chain is traceable in history.

## Verification

Real isolated DB tests for authority, stale/concurrent work, pagination-independent scope,
delivery proof/admission, partial Moodle preservation, self-notices and background shutdown.
Provider and native observation fixtures only; tests never contact live models or production.
Full backend/bridge/frontend suites, locale/build, strict UI audit, browser desktop/mobile and
one independent final review. Publish only the exact verified artifacts with backup/restore.

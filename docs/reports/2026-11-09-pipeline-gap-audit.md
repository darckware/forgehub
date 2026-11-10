# Additional pipeline gap audit

Scope: existing Mission/Messages/24x7 maturation, including coding-agent runtime
skills, delegation and verified learning. Static findings below are not claims
that an incident occurred in production. Existing G1–G11 remain in the spec;
this audit adds concrete blind spots and qualification scenarios.

| Finding | Evidence and consequence | Qualification / existing owner |
|---|---|---|
| Mission-wide question can hide unrelated idle tasks | `core/mission_cycle.py:watchdog_findings` suppresses idle finding if any pending question exists. Its query does not restrict the question to each open task. Independent work can be hidden behind one legitimate human wait. | Task 7: reproduce a mission with one questioned task and another eligible idle task; supervise each task's actual blocker. |
| Bounded quota scan lacks rotation | Current branch `run_scheduled_dispatch_pass` orders automatic future waits and takes the first 200 every pass. If those remain unchanged/waiting, a later item whose availability returned is never examined until earlier ordering changes. | Task 2: >200 persisted waits, later eligible item; bounded scans need fair continuation, not repeated first-page selection. This is a current WIP qualification gap. |
| Cancellation is recorded before termination is confirmed | `host-bridge/app.py:cancel_agent_run` sends SIGTERM to the process group and immediately stores cancelled/finished, without waiting for exit. A process ignoring TERM or an escaped descendant requires investigation; signaling alone does not prove inactivity. | Tasks 3/5/6: test TERM-resistant process group and descendant handling; retain uncertainty until exact process/run reconciliation. Do not kill live production processes for qualification. |
| Current instruction versus historical instruction is not structured | `core/demand_thread.py:build_thread_prompt` concatenates body and command instruction. Recent diagnostics carry original executor/reviewer instructions, as documented in the external coder analysis. | Tasks 4/6: explicit current objective/role plus bounded attributed history; verify no authority or executable instruction is inferred from quotations. |
| Skill grants do not prove usable capability | `_skill_gaps` compares required IDs with grants; prompt/run request does not establish that selected instructions are accessible and runtime-compatible. | Task 5/runtime skill extension: verify accessible content/version, required proficiency and effective tools; retain existing registry instead of inventing another catalog. |
| Child workers are not a structured launch resource | `AgentRunRequest` has mode, autonomy and parent limits but no declared child-role/parallelism allocation. Existing one-run-per-agent capacity does not count native child workers. | Runtime extension/Tasks 5–7: test child limits, shared budget, isolation, parent restart and final evidence aggregation. No assumption that every runtime supports the same features. |

## Additional scenarios requiring reproduction

- Service routine continuity: the routine model has an agent and optional mission
  link, which does not itself prove the associated service/product/customer.
  Qualify the actual service source, occurrence evidence and recovery ownership.
  A failed/missed/budget-skipped occurrence must remain an operational exception;
  the next successful run or a completed remediation task cannot silently erase it.
  Ongoing service health is distinct from task and product-version completion.
- Remote autonomy: qualify that the assigned runtime can discover and use its
  actual run-scoped remote tools, current machine grant and required skills.
  Pause/expiry/reassignment must not become an unexplained executor wait; unknown
  command outcomes must not trigger a blind replay. Preserve the existing
  automatic ForgeHub audit, per-run credential and no-private-key-to-agent policy.
  Already-authorized access must not create a redundant human approval for each
  technical step; existing action-specific approval rules remain authoritative.
- Workspace browser: the current implementation is a shared human/Athos CDP
  session with pointer/text/navigation and structured automation. Qualify actual
  external-CLI tool access, shared-page ownership under parallel tasks, human
  takeover, authenticated context privacy and uncertain data submissions. Reuse
  the existing browser and resource/identity contracts. Browser availability in
  Workspace does not by itself prove safe parallel use or access by every coder.

Implementation follow-up: the first-page quota starvation finding now has a
prepared fix and a 201-wait regression. Persisted least-recently-checked ordering,
bounded skip-locked selection and bookkeeping that preserves content freshness
passed the 32-test recovery suite after test-only migration rollback/re-upgrade.
This is source qualification evidence, not production release evidence.

- A human answer, source-scope edit, skill update, approval expiry or reassignment
  occurs while analysis/delegation is running. Recheck the effective current
  contract before effects/integration; capture the exact carried versions.
- Several actors classify the same work as duplicate or obsolete while a partial
  result exists. Reconcile canonical identity, scope and independently verified
  evidence; never deduplicate solely by text or a model's confidence.
- A reviewer approves artifact A, followed by a worker integrating or publishing
  artifact B. Bind review, integration, evidence and acceptance to exact content,
  including approved scope changes. This deepens existing Task 7 qualification.
- Learned instructions contradict the charter, leak private task context or are
  incompatible with a newer CLI. Verify provenance and permissions, review the
  proposed version and support rollback; no automatic authority expansion.
- A task repeatedly bounces among diagnosis, reassignment, review and correction.
  Preserve one canonical responsibility and a bounded reevaluation/escalation
  policy so repeated activity is not mistaken for progress.

## Priority and boundaries

### Service Factory development and autonomous routines

The existing factory plan already generalizes products into services and versions
into software versions or service cycles/contracts. Treat this as the existing
direction, not a new design. The operational completion gap is connecting that
direction consistently to current execution and evidence:

| Development/routine requirement | Current evidence | Maturation in existing flow |
|---|---|---|
| Start with a usable, authorized package | Factory plan describes automatic project preparation; current runtime request mainly carries prompt/mode/limits | Qualify actual opening-to-dispatch readiness rather than equating a documented template with provisioned context |
| Allocate qualified executor and independent reviewer | Mission plan evaluates membership/skills; plain Messages failover only filters runtime/status/capacity | Apply compatible assignment at reservation as well as proposal time; retain owner/reason when blocked |
| Delegate without losing canonical progress | Parent runs exist; native subagent roles/budgets are not structured launch input | Bound child packages and evidence, aggregate through the parent task; preserve existing project progress |
| Keep documentation synchronized with delivery | Documentation and artifacts exist as factory obligations | Link each affected document to the actual reviewed change/version; unresolved documentation is visible work |
| Follow recurring service obligations | Unique routine occurrence and demand linkage already exist; routine status mirrors the dispatch result and separately records evidence_received | Display attempt completion and verified service evidence distinctly; qualify service-source linkage and explicit missed/failed exceptions |
| Close the exact product/service version | Existing completion/review/integration guards and dossier API exist | Verify exact accepted scope/artifact and source documentation before release/cycle closure; do not infer closure from DONE or a later successful routine |

Autonomy should cover eligible planning, decomposition, assignment, execution,
verification, correction and progress recording within existing delegation.
Escalate actual scope/authority/resource decisions with contextual decision aid;
do not ask Marcelo to reconstruct every technical context. Every autonomous
routine needs an objective, authorized boundary, responsible owner, expected
evidence, schedule/trigger, retry/reconciliation path and stop/escalation condition.
Metrics should distinguish useful accepted delivery from repeated agent activity.

Generalization checkpoint: the current models already include `Product.kind`,
`Project.service_line_id` and the ServiceLine stages/documents/evidence catalog.
Do not rebuild those mechanisms based on an old planning status. A confirmed
downstream mismatch remains: `core/task_evidence.py:verify_evidence` recognizes
file/git/db references, while service-line evidence declarations can describe
other forms such as host execution. Catalog configuration alone therefore does
not prove end-to-end completion support for every line. Qualify each evidence
adapter and its semantic verification before claiming full service coverage;
do not accept an arbitrary string or row-existence check as service success.

Before broader autonomous activation, close false-terminal/replay risks, then
per-task supervision, fair queue recovery and contract-compatible assignment.
Qualify contextual runtime capabilities, controlled parallelism and learning
against those same boundaries. Existing Task 7 already covers planning-stage
supervision and trusted dossier integrity; those are not newly discovered here.

The target is accepted delivery with accountable exceptions. An external outage,
missing authority or legitimate human decision can prevent immediate completion;
the pipeline must preserve the work, owner, reason and next action, rather than
promise unconditional completion or fabricate success.

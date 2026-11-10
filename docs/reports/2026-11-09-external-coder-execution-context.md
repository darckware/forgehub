# Contextual execution for external coding agents

Requested outcome: fast execution, high quality and excellent delivered results.
This analysis extends the approved maturation plan; it does not activate new
permissions or introduce another orchestrator.

## Observed implementation

`backend/app/core/agent_runs.py:dispatch_agent_run` sends runtime, identity,
working directory, prompt, plan/execute mode, autonomy, time and budget limits.
`host-bridge/app.py:_agent_run_command` already has separate Claude, Codex and
agy branches. Those branches choose fixed argument patterns from mode/autonomy.
The request does not encode delegation, worker roles, parallelism, work isolation,
review strategy or a versioned runtime capability selection.

Autonomy currently selects CLI permission behavior. It does not itself describe
the authorized task scope, delegation strategy or acceptance obligations.
External CLIs use their native authentication/models under the existing policy.
That policy must survive contextual command construction.

## Messages inspected

Read-only sample: 40 latest task Messages addressed to Claude/Codex/agy runtimes.
No messages were consumed, edited, archived or dispatched for this analysis.

- #42178 names Aramis as executor and Dartan as reviewer in prose.
- #42180 describes a read-only independent review, exact commit and prohibited
  production actions. The runtime request has no structured reviewer mode.
- #42222 asks its executor to request review from Porthus, while the message
  itself targets Porthus. The inherited workflow therefore needs a factual
  author/reviewer check instead of interpreting those words as fresh authority.
- #42225 and #42182 are diagnostics addressed to Porthus that carry original
  implementation instructions. Original instructions must be recognizable as
  historical context, with the diagnostic's current objective and role explicit.
- #42184 records a reviewer substitution because of quota, preserving independence.

These examples establish ambiguous execution intent in the transport. They do
not prove which runtime flags were used by each historical run or that every
referenced task remains unresolved. Those require the exact run and delivery
records already covered by the maturation plan.

## Recommended maturation

Marcelo's intended coding-agent workflow is: understand the authorized delivery,
discover/read applicable skills, plan development, critique the proposed solution,
split it into bounded subtasks, delegate suitable work to native subagents,
integrate results, verify acceptance evidence and obtain required independent
review. The coding agent owns the integrated delivery. Mission management keeps
the approved scope and cross-agent dependencies; local decomposition does not
silently change them or create another source of canonical task state.

Each delegated package needs its objective, relevant context, prerequisites,
allowed files/isolated checkout, constraints, acceptance checks and expected
evidence. Delegate independent packages in parallel, order dependent packages,
and reconcile changes at integration. Keep a durable plan/result summary so
context reduction does not lose decisions, requirements or unfinished work.
Use the amount of decomposition appropriate to the task; trivial changes do not
benefit from an obligatory multi-worker pipeline.

Decomposition and delegation reduce context overload and provide opportunities
to detect mistakes. They do not guarantee elimination of hallucination: shared
assumptions and repeated model claims need external evidence and actual checks.

Use one runtime skill for each external CLI, with a common execution contract
and agent-specific charter overlays. The runtime skill documents supported
operating modes, native subagents, limitations, isolation, review and recovery.
It must be validated against the installed CLI version/help and maintained when
that version changes. Do not assume a Claude option exists in Codex or agy.

The manager selects structured intent through existing Mission/Task/Messages
records: objective, current role, dependencies, authorized autonomy, delegation
requested, maximum parallel workers, isolation targets, acceptance evidence,
reviewer requirements and execution limits. The skill informs this choice.
The existing runner validates supported capabilities and constructs an argument
list deterministically. A model must not generate an unrestricted shell command.
Record the selected intent, adapter/skill version and sanitized launch arguments
against the existing run identity for later explanation and recovery.

Allow native executor/reviewer/supervisor subagents where authorized and supported.
They remain descendants of the parent execution, sharing its scope and budgets;
they do not create new agent identities, credentials, quota or acceptance authority.
A local review improves quality but cannot replace a required independent review
by another eligible registered principal. Preserve the existing author/reviewer
and protected-target rules.

Independent canonical tasks may run concurrently through existing dependencies,
capacity and target reservation. Native parallel workers inside one run are a
different resource boundary and need their own bounded allocation and isolated
checkouts. Supervision must summarize child work under the parent run instead
of generating duplicate Messages for every internal exchange.

If a runtime cannot honor a requested feature, preserve the task and explain
the unsupported capability. Select an equivalent authorized strategy or eligible
runtime through the existing manager; never silently ignore the request.

## Integration into the approved plan

### Contextual skill discovery and verified learning

Marcelo additionally requires agents to discover applicable skills before acting,
and learn from verified outcomes to reduce hallucination. Existing required skill
rows (`core/task_skills.py`), agent grants and mission skill-gap proposals must
remain the source; do not add a competing capability inventory.

For each executable context, resolve the task's mandatory skills, relevant
authorized optional skills and the selected runtime skill. Check that the actual
skill contents are accessible, applicable and compatible with the installed
runtime, not just that an agent has a catalog grant. Load the needed instructions
before execution and record the selected skill identities/versions with the run.
Recheck applicability when scope, assignment, runtime or skill content changes.
An absent mandatory skill blocks admission through the existing skill-gap path;
an optional skill's absence alone must not stop otherwise qualified work.

Learning must distinguish an observation from a proven reusable procedure:
capture outcome and exact evidence; reproduce and review the lesson; propose a
versioned skill correction through the existing owner/security review; publish
the qualified version; then observe later executions and permit rollback if the
lesson proves wrong. Failed attempts, repeated assertions and model confidence
do not establish truth. Preserve private-context boundaries and remove secrets
from reusable material. Do not auto-install a skill from untrusted task content
or let learning grant permissions, change an acceptance criterion or approve the
author's own work.

Expose missing knowledge and uncertainty explicitly. Require sources and actual
artifact/run evidence for delivery claims, and verification appropriate to the
task before acceptance. This can reduce hallucinated commands and completion
claims; it cannot guarantee zero hallucination. Promotion and rejection should
use evidence, not an invented model-confidence threshold.

Task 4 supplies current objective and decision context. Task 5 validates role,
runtime capabilities and protected parallelism. Task 6 preserves identity and
provenance across handoffs. Task 7 verifies delivered artifacts, review and
acceptance. Runtime skill/catalog changes require the existing skill registry
and review process; no live agent profile has been changed by this analysis.

Evaluate success by accepted delivery and elapsed time, including queue wait,
execution, review and corrections; track duplicate execution, rework, stalled
tasks and resource use. Agree numerical targets from operational evidence,
instead of inventing thresholds or maximizing worker count.

## Installed runtime inventory, 2026-11-10

Read-only CLI inspection confirmed Codex 0.167.0, Claude Code 2.1.322 and agy
1.5.3. Codex exposes `exec --strict-config` and configurable sandbox modes;
Claude exposes native `--agents`, permission modes and `--max-budget-usd`; agy
exposes session `--settings`, `--mode` and `--sandbox`. This inventory establishes
installed interfaces, not qualified delegated execution. The canonical dispatch
request still needs T8's structured capability/skill contract before T9 can be
marked complete. No native model invocation or credential change was performed
for this inspection.

Deployment preflight also found a newer Maia backend release `fh-e836bc5`.
Integrate current develop changes before any mission release; do not restore an
older backend image as the new production artifact. Verified production flags:
workers=true, triage=false, mission_cycle=false, mission_tools=true. The tmux
scope remains active with OOMPolicy=continue. These are observations, not an
instruction to enable the manager.

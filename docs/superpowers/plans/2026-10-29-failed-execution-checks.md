# Failed execution checks implementation plan

**Goal:** Preserve failed execution evidence, create one linked diagnostic task, then archive the original attempt atomically.
**Approved design:** Marcelo approved a chain: original request → attempt → check → correction → conclusion. A check failure must stay blocked rather than generate another check.
**Architecture:** Add a server-owned unique source FK on Messages checks. A locked original and child creation share a transaction. Use the existing dispatch worker, sender ownership and working directory; checks diagnose and route corrections within the original authorization. Keep uncertain runner outcomes blocked for reconciliation. No additional scheduler/process or approval is introduced for ordinary work.
**Files:** model/schema + Alembic migration; `core/demand_failure_check.py`; demand finalization/known-start failures/completion reconciliation; Messages context links + locale/schema; regression tests.

## Constraints and decisions
- A check belongs to the original sender (fallback executor), never an invented agent.
- Preserve project/origin, command, requester, cwd, channel references, exact run ID, error, output and attachment references. Keep original records; links are RESTRICT against deletion.
- Preserve existing approval requirements. Do not reuse a prior approval hash for new content. Diagnostic tasks may not replay the failed work or send externally on their own.
- Checks have a structured server-owned source link; no subject-based loop detection.
- No checks for archived/consolidated work, unconfirmed run outcomes, or failed checks.
- Create the child before archive; rollback must undo both. Unique source prevents duplicates across workers/restarts.
- Reconcile existing non-archived known failures through the current completion pass, never by migration or automatic retry.

## Tasks
- [x] Add failing integration tests for context preservation, duplicate handling, rollback, no recursion, unknown outcomes and approval inheritance.
- [x] Add source link and migration; implement atomic handoff and connect existing finalizers.
- [x] Show bidirectional source/check navigation and failed-check pending state; protect linked history from cleanup.
- [x] Run focused backend/frontend tests, build, lint and local browser checks. Document limitations and production publication status.

## Outcome and limits
- Uses `failure_check_source_id`, unique and RESTRICT, rather than overloading informational reply links or Software Factory task identifiers.
- Recognized quota resets with explicit time/timezone schedule the same developer's check/continuation at reset + 5 minutes (or now if already elapsed). No guessed dates or arbitrary developer substitution. Unrecognized quota output goes to the requester's diagnostic; its instructions allow routing within Codex/Claude/agy with role/independence preserved.
- Existing source-specific approval, blocking-question and Moodle guards remain enforced at both dispatch and pending-inbox boundaries. Approving a scheduled check preserves its future reset time.
- Known historical failures are reconciled by the existing completion worker. Uncertain/stale outcomes remain blocked; failed checks require intervention and never spawn another check.
- Linked messages and their attachments cannot be deleted through the API; bulk UI cleanup excludes linked history.
- Validation: 96 related backend tests; full frontend suite 398 tests; frontend build and final TypeScript check; Ruff and diff checks; independent review with blocking findings resolved.
- Migration verified in the isolated test database. Production publication requires the additive migration before starting the new backend; see `docs/runbooks/MESSAGES_FAILURE_CHECKS.md`.

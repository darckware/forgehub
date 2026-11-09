# Messages triage implementation plan

> **For agentic workers:** Use superpowers:executing-plans for coordinated native execution;
> delegate the independent context analyzer/native observation and frontend tasks in parallel.

**Goal:** Automatically analyze and reconcile agent work, surfacing only genuine operator decisions.
**Architecture:** Durable jobs/results in the existing Messages domain; constrained contextual
analysis and deterministic backend authority/evidence gates; existing scheduler executes work.
**Tech Stack:** FastAPI, SQLAlchemy/Alembic/PostgreSQL, ForgeRouter, React/TanStack Query/i18n.
**Spec:** `docs/superpowers/specs/2026-11-08-messages-triage.md`.

## Global constraints

- Isolated worktree; preserve unrelated edits; tests only with ENVIRONMENT=test.
- No new approvals, execution identities or external communications inferred from text.
- Preserve uncertain/active runs and all attempt history. No mission-cycle activation.
- UI uses maintained primitives/tokens, URL filters, pt-BR/en/es and background job progress.
- The approved scope includes implementation, verification and exact-artifact publication.

## Review focus

- Untrusted text suggesting authorization, completion, another message ID or destructive actions.
- Deliveries/analysis becoming stale between observation, application and dispatch reservation.
- Duplicate jobs, partial progress, provider failures and process restart leaving work stranded.
- Cross-personal-context leakage and model requests receiving secrets or unrelated task contents.
- Resolving partial Moodle work or an original task merely because its diagnosis completed.

### Task 1 — Persistence, authority and job APIs (coordinator)

Files: new models/schemas/routes/core job worker and migration after e2c8d0b45e73;
extend demand_management, demand_dispatch_guard, main and tests.

- [x] RED isolated tests for job coalescing/scope, source versions, human decisions and stale deliveries.
- [x] Add `MessageAnalysisRun` and per-message `MessageTriageResult`; verified delivery is an audited
  event bound to `approval_fingerprint`, checked through `verify_on_host`.
- [x] Implement async job enqueue/status, analysis worker and deterministic apply guards.
- [x] Prove no replay/approval bypass, existing run preservation and disabled test background loops.
- [x] GREEN domain tests; record results and commit.

Interfaces: schemas `TriageSuggestion` and `AnalysisRunOut`; model JSON fields match the spec.
Core calls `analyze_messages(db, items, related, agents, availability)` and consumes typed proposals.

### Task 2 — Context analyzer and native availability (independent worker)

Files: `core/message_triage_analysis.py`, its unit tests; `host-bridge/native_availability.py`,
its tests. Coordinator registers the bridge endpoint.

- [x] RED malformed/unknown-ID/injected instructions and private-context batch tests.
- [x] Typed, bounded ForgeRouter analysis with per-domain identity, redaction and fail-closed replies.
- [x] RED fresh/exhausted/stale/unknown native Codex window/auth-change fixtures.
- [x] GREEN analyzer and bridge unit suites; report interfaces and evidence.

Interface: `analyze_messages(db, items:list[dict], related:list[dict], agents:list[dict],
availability:list[dict]) -> list[TriageSuggestion]`. Each item includes `analysis_agent`.
Native helper `observe_codex_availability(home:Path, now:datetime) -> dict` with
`available:bool|None, observed_at:str|None, reason:str`, never transcript or credentials.

### Task 3 — Operator workflow UI (independent worker)

Files: AgentTasksTab, useAgentTasksViewModel/useDemands, tests, personal locale catalogs,
DESIGN.md and UX-CONTRACT.md.

- [x] RED primary action, global scoped request, progress/refresh, decision-only defaults and failures.
- [x] Implement four operator views, analysis summary/recommendation and readable context.
- [x] Preserve guarded Moodle/approval details and secondary archive; update taste/UX contracts.
- [x] GREEN frontend suite, locale/build and relevant browser evidence.

### Task 4 — Integrate, review and publish (coordinator)

- [x] Integrate analyzer/native/UI, complete migration and background/provenance tests.
- [ ] Full suites and exact-artifact smoke; independent review approved after fixes; final publication checks running.
- [x] Register verified current deliveries; archive the four reconciled Porthus entries through the guarded API.
- [ ] Backup/restore, publish exact commits/bridge, verify automatic/manual paths, commit/push report.

Pre-flight: Tasks 2/3 consume Task 1 schema/API contract; these exact names are frozen above.
Ruling: use native coordination with two independent worker assignments, avoiding overlapping
edits or simultaneous DB suites. The already-approved product design needs no second approval.

### Task 5 — Messages labels and right-side legend (2026-11-09 user clarification)

User requires authorized work awaiting an executor to remain in the existing Execução folder,
with a clear tag. Pending human authorization/decision must show its actual destination in
Pessoal. The legend opens on the right and documents labels by Messages folder.

- [ ] Backend: batch read-only classification, fixed label keys, current quota/executor facts,
  cached-analysis freshness, exact delivery proof and operator destination; additive DemandOut.
- [ ] Frontend: rows/reading pane tags, consistent folder counts, accessible right-side legend,
  links to Pessoal, pt-BR/en/es and catalog documentation by group.
- [ ] Verify genuine executor wait never becomes another approval; uncertain/active/delivered
  work is not reclassified as ready merely by a label.

Owners: architecture worker owns new classification service/schema/GET annotations/tests;
UI worker owns Messages labels/legend/shared overlay/catalog/locales/frontend tests. Coordinator
owns verified archival, recovery regressions and integration/publication. No overlapping edits
or concurrent database suites.

### Task 6 — Durable flow and closure (coordinator)

- [ ] Regression: a persisted authorized task is discovered without receiving its wake event.
- [ ] Verified delivery/finished diagnostics leave the active inbox with an audit trail;
  diagnostic closure preserves an unresolved original task.
- [ ] Independent review of backend labels, UI legend and source/delivery lifecycle.
- [ ] Final build/test/restore, live analysis, guarded activation and publication report.

Flow contract: `docs/architecture/MESSAGES_ORCHESTRATION.md`. Reuse the existing dispatcher,
durable analysis jobs and periodic recovery; labels remain a presentation of current facts.

# Quota wait indicator implementation plan

**Goal:** Treat external runtime quota exhaustion as a persistent wait, preserving the same executor.
**Architecture:** Add nonterminal waiting_quota, nullable reset and binding metadata; reuse existing classification labels and dispatch guards. Quota waits preserve evidence and cannot fail/archive the work.
**Tech stack:** FastAPI, SQLAlchemy/Alembic, React/TypeScript, pytest/Vitest.
**Spec:** docs/superpowers/specs/2026-11-14-quota-wait-indicator-design.md (approved by Marcelo).
**Execution:** Selective backend executor, primary frontend implementation and homologation, independent whole-diff review for lifecycle safety. No merge/push/deploy without approval of final content.

## Tasks

- [x] Backend: add migration/model and API support for waiting_quota with optional reset. Add regressions for three runtimes and unknown resets before implementation. Recognize quota before failure handling; preserve run/output, identity and authorization. Separate quota attempts from work-failure retry budget.
- [x] Backend: scheduler resumes same-agent waits only with explicit reset and intact binding/authorization/effect guards. Unknown reset stays parked. Missions recognize waits and never dispatch duplicates; protected executions use owning guards. Test these boundaries and real failure behavior on isolated PostgreSQL only.
- [x] Backend: classification and work filters return waiting + quota label; triage, notifications and archive paths respect nonterminal wait. Historical archived records remain untouched. Update business rules and changelog with actual status.
- [x] Frontend: accept new state, reuse MessageLabels and existing stage badges, show reset/unknown reset in Messages and personal agent tasks, localize pt-BR/en/es, maintain DESIGN.md. Test state display and exclusion from errors/retention.
- [x] Verify: scoped backend regression suite, Ruff, Alembic head, frontend typecheck/build and meaningful Vitest tests, real browser at390/1440. Independently review dispatcher/mission/no-replay guarantees; fix and rerun relevant checks.

## Review focus

Unknown reset cannot retry, quota cannot consume ordinary failure budget, mission/review identity remains fixed, one-use approvals cannot replay, waiting runs never hold executor slots or trigger archived/completed presentation. Missing reset is explicit null, never guessed.

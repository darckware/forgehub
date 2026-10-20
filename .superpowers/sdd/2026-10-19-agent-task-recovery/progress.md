# SDD ledger — plan: docs/superpowers/plans/2026-10-19-agent-task-recovery.md

Scope: complete approved recovery and consolidation plans; user authorized implementation and delivery on 2026-10-20.
Pre-flight: existing dirty implementation on develop is the continuation workspace; retain it in place to preserve the authorized in-progress code.
Pre-flight: listing, single actions and bulk actions share AgentDemand and decision validation; existing route paths retained.
Ruling: retain the existing /decision endpoint for recovery/restore/drop instead of adding overlapping endpoints — compatibility and one validation path — cost if wrong: API alias later.
Ruling: structured failure/recovery categories are derived from stored evidence and returned by the management API; do not infer terminal resolution of historical runs — cost if wrong: future migration to persisted categories.
Task 1 complete: backend workflow, bounded management query, per-item bulk decisions, durable audit history, frontend and operator recovery are implemented. The full backend suite passed 950 tests (1 skipped); frontend passed 352 tests; build, full Ruff and Chromium checks passed. The approved code was deployed from commit `35ae489`; production API returned the five new incubation rows and schema `e6a1c8d3f9b2 (head)`. The 34-source consolidation applied atomically to summaries #39617–#39621 and passed post-commit DB assertions. A sanitized item-by-item report is in `docs/messages-passive-review-2026-10-20.md`.

Final review findings were fixed and verified with regressions: stale mutation/reservation races and group-only archival bypass now reject safely; ordinary retries preserve the previous run/error snapshot; the UI and backend share one uncertainty predicate. Timeout and bridge 404 outcomes remain blocked until reconciliation or typed operator confirmation.

Remaining operator decisions: the 12 uncertain historical runs need reconciliation or evidence-backed inactive confirmation; the five summaries remain pending incubation decisions. No old execution was restarted, marked complete, or individually discarded.

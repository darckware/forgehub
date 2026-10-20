# Messages resumption — 2026-10-20

## Implemented

- Protected dispatch reservations and all relevant edits with refreshed row locks; archived and unresolved runs continue to occupy capacity.
- Restored archived work without preserving a scheduled execution; it requires a fresh operator approval. Incubation restore starts a new decision cycle.
- Added a paginated server query for Agent Tasks with filtered counts, agent/context/date/search filters, and backend-provided allowed and blocked actions.
- Added per-item bulk archive/restore results, stale-update checks, durable run/result/error evidence, and linked source/history views.
- Added uncertainty recovery: an operator can record investigation evidence, then confirm inactivity by typing the exact run ID (or message number if no run ID exists). This does not execute work; retry requires a separate authorization and approval.
- Fixed the reviewer findings around stale dispatch races, group-only archive bypass, lost attempt evidence, and inconsistent uncertainty classification.

## Verification

- Full backend suite against `forgehub_messages_resume_v2_test`: **950 passed, 1 skipped**. The bridge used for tests is an isolated file-only server; it rejects message-send and runner routes.
- Frontend suite: **82 files, 352 tests passed**; `npm run build` passed.
- `backend/.venv/bin/ruff check app`: passed.
- Chromium headless at 1440px and 390px: no page errors and no horizontal overflow; investigation and inactive-confirmation actions appeared after selecting the task.
- The read-only production preview matched the approved five groups and all 34 source IDs: 15 agent-operations, 3 infrastructure, 6 backup, 9 security, 1 Maia/WhatsApp.

## Published and operational status

Published from commit `35ae489` (`0.1.0`). The production API is healthy, the current schema is `e6a1c8d3f9b2 (head)`, and a read-only API request returned the five new Incubation rows: **#39617–#39621**.

The approved consolidation completed in one transaction: all 34 selected originals are archived and linked; all five summaries remain unscheduled, pending incubations; five audit events were written; all 81 personal suggestions were preserved. The transaction asserted that source text, run ID, error, and attempt count were unchanged. The post-deploy API and database checks passed. The sanitized per-message triage report is [messages-passive-review-2026-10-20.md](messages-passive-review-2026-10-20.md).

The 12 uncertain historical results remain blocked until an operator reconciles them or confirms inactivity with evidence. The five summaries await human prioritization; no source was re-run, marked complete, or individually discarded by this consolidation.

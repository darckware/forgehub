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

## Operational status

The application is ready to publish. The approved five-summary consolidation has not yet been applied; its preview is saved at `/tmp/forgehub-messages-consolidation-preview-final.json`. Apply it after deployment, then verify all 34 originals are archived and linked, the five summaries are unscheduled incubations, and no personal suggestions or run evidence changed.

Other historical failures still need evidence-based review before any retry. No old run was restarted or marked complete as part of this work.

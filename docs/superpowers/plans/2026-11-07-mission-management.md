# Mission management continuation

Continuation of Marcelo's 2026-11-06 requests, recovered from the previous session on 2026-11-07.

## Scope and decisions

Complete the existing mission form and define how orchestration, roles and context connect to dispatch.
Keep the existing FastAPI mission domain and React pages. Do not create a second execution system.
Athos is suggested only when his active registry record is available; the administrator selects the
actual orchestrator. The backend creates its coordinator membership and protects it from release.
Other members receive a registered function and explicit responsibilities. Membership does not
assign a task: task assignment and independent reviewer selection remain in the execution board.

The removal operation is mission cancellation with a reason and confirmation. It preserves history,
documents and evidence, using the existing terminal state instead of adding destructive deletion.
Approved mission metadata remains protected; draft creation does not approve a plan or start agents.

## Implementation and verification

- [x] Recover and inspect the existing form, route/schema changes and tests, retaining unrelated edits.
- [x] Verify creation, metadata editing with row version, cancellation and terminal/read-only behavior.
- [x] Add inline team management through `POST /missions/{id}/members:apply`, with confirmation,
  responsibilities, review permission and reversible release. Keep idempotency keys on retries.
- [x] Include orchestrator and executor responsibilities in the allowlisted dispatch body and manifest.
- [x] Give reviewers the same scoped context, plus their execution evidence and decision route,
  with read-only instructions rather than executor completion instructions.
- [x] Keep pt-BR/en/es catalogs aligned, preserve design tokens and use shared confirmation controls.
- [x] Finish final browser/build/regression verification and record results in
  `docs/reports/2026-11-07-mission-management.md`.

Changed owners: `api/routes/mission.py`, `api/schemas/mission.py`, `core/mission_dispatch.py`,
`api/routes/mission_task.py`, `useMissionManagement.ts`, `missions/FormPage.tsx` and
`components/missions/MissionTeamEditor.tsx`. Tests live with the mission domain and pages.

## Context contract

Executor: task and plan, approved brief objective, baseline/task hash, linked acceptance criteria,
predecessor identities/statuses, mission orchestrator, member role/responsibilities, declared targets,
working path and task-specific correction reason. Reviewers receive the same slice, their own
membership and the reviewed execution summary/evidence. Each source is hashed in the audit manifest.
Both modes refuse context above 32 KiB. No broad memory/KB lookup or sibling result retrieval is added.
The form description remains project metadata; it does not substitute for an approved brief.

Runtime memory hooks remain governed separately by C.2.R/C.2b.R. Text fields are instructions, not
additional access grants. Code work still requires an eligible external runtime. Self-review remains
forbidden and human acceptance is unchanged.

## Delivery boundary

Local code and isolated verification only. No production mission is created or dispatched, no
production deployment is included, and the FileNest application is not changed by this continuation.

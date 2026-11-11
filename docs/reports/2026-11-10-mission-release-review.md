# Mission release review and recovery record

## Release addendum — 2026-11-11

The ten findings below were reproduced and fixed before release. Candidate
`8282579ea67a6f12e7c87d1a62f50b67fb06868c` was qualified with the full backend
regression (**2,175 passed, 21 skipped**), full frontend suite (**523 passed in
111 files**), 19 focused bridge tests, browser checks, and six tests against the
exact backend image. The broad bridge test run remains incomplete: its pytest
process hung after 31 passes and was interrupted, so it is not claimed as green.

The exact release and live state are recorded at
`/root/.forgehub/releases/mission-integration-8282579-retry1/release.json`:
backend `fh-fc67cea`, frontend `fh-8282579`, migration
`e6f2d4a89cb7`, `MISSION_CYCLE_ENABLED=false`,
`MESSAGE_TRIAGE_ENABLED=false`, `MISSION_TOOLS_ENABLED=true`,
`BACKGROUND_WORKERS_ENABLED=true`. Backup restoration and migration were tested
in a disposable Postgres. One initial rollout was automatically reverted after
an immediate backend health probe raced startup; the retry waited for HTTP 200
and published. The same tmux server and three pane PIDs were preserved.

This release closes the reviewed implementation slice, not the full maturation
plan. A read-only audit after deployment found that mission criteria can be
decided and accepted, but there is no criteria creation route yet (the code
defers criterion writes to M0.2). Tasks 8–12 and the broad bridge suite remain
open; automatic mission cycle and message triage stay disabled.

Reviewed `dfc46e6..d730841` in `feat/messages-triage`. The checkpoint is on
origin. It preserves Tasks 1–7, including governed acceptance, alongside the
terminal hotfix already deployed separately. Tasks 8–12 remain in the approved
plan. This review does not qualify those tasks or activate the manager.

The checkpoint's isolated backend suite finished with **2,147 passed, 21
skipped** in 497.33 s. An independent, read-only reviewer found the following
behavioral gaps that the suite did not cover. Candidate status: fixes required.

| Finding | Reproduction and correction in progress |
|---|---|
| Criterion reference could name missing/foreign evidence | RED `test_nonexistent_criterion_evidence_cannot_be_proven`; verify typed evidence in an actual linked attempt at criterion decision and acceptance. |
| Contract changed before submission could reuse old proof | RED `test_contract_changed_before_request_cannot_reuse_old_acceptance_proof`; compare each delivery with its approved baseline at both boundaries. |
| Task reopen raced final acceptance | RED `test_acceptance_serializes_with_task_reopening`; serialize delivery writes with snapshot validation and protect formally accepted tasks. Contradictory acceptance requests are also tested. |
| Cursor was overwritten by an ORM refresh | RED `test_successful_event_pass_advances_cursor_and_does_not_repeat`; lock before reading and commit cursor with durable intent. |
| Two command keys consumed the same context version | RED `test_different_commands_cannot_consume_the_same_context_version`; lock the mission before rechecking freshness; pending reservations fence other commands. |
| Mission-only reviewer of linked executor task was refused | RED `test_linked_task_can_use_mission_only_review_membership`; honor the exact review membership and allowed mission/task scope. |
| A review answer created a producer attempt | RED `test_answer_to_review_preserves_review_operation_without_executor_attempt`; retain review identity and original attempt. |
| Execution-link answer resumed contextual task instead of actual target | RED `test_answer_execution_link_uses_target_execution_and_retains_context`; use linked execution's task and preserve the source message. |
| Unscheduled authorized executor wait could be lost | RED `test_unscheduled_authorized_wait_recovers_without_analysis_or_event`; persist intent and recover periodically through existing guards. |
| Moodle question button opened no dialog | RED `keeps the question answer path visible in Moodle approvals`; share the existing answer dialog and verify exact question submission. |

Additional UI RED: a generic HTTP error obscured the acceptance refusal;
reuse the existing mission error formatter and preserve the typed reason.

The reviewer did not assess T8–T12, the already deployed terminal hotfix,
newer Maia commits on develop, or live rollout/restore. Those limits remain
explicit: the deploy must incorporate current develop, qualify migrations and
record rollback. Production flags observed: background workers enabled,
message triage disabled, mission cycle disabled, mission tools enabled.

Targeted fix pass: **135 backend tests passed** (`/tmp/fh-review-green.log`)
and **29 UI tests passed** (`/tmp/fh-review-ui-green.log`). The new waiter
index also covers unscheduled authorized work; the final migration exercise
must apply the exact updated index. Next: merge current Maia changes and
qualify the resulting candidate sequentially. Preserve
both the green checkpoint and this evidence of issues before any rollout.

## Criteria API and MCP release addendum — 2026-11-11

Commit `2d0eeab362af5476a38096c52c57340a95d127d0` adds governed GET/POST
mission criteria endpoints, MCP tools `get_mission_criteria` and
`create_mission_criterion`, and the mission detail UI. Creation requires
mission orchestrator/admin authority, an in-scope linked task, exactly one
eligible verifier, idempotency, and is locked after the first baseline. The
existing decision and human acceptance tools remain the final evidence gates.

The exact release receipt is `/root/.forgehub/releases/mission-criteria-2d0eeab/release.json`.
Backend and frontend images are `fh-2d0eeab`; the backend exact-image offline
checks and six evidence tests passed, source regressions were 2,178 backend
tests and 526 frontend tests, and the isolated backup restore succeeded. Live
health and frontend hash checks passed, anonymous auth returned 401, and the
same tmux server/panes were preserved. DB remained at `e6f2d4a89cb7`; no
migration replay was performed. Mission cycle and message triage remain off.

The global Codex ForgeHub Skill was **not installed**: the active session cannot
write `/root/.codex/skills/forgehub/SKILL.md`. Its v1.3.0 preview is at
`/tmp/forgehub-skill-1.3.0.md`, pending a session with that skill directory
enabled. The broad asynchronous host-bridge suite also remains incomplete, and
T8–T12 remain open; this release is not the full mission maturation delivery.

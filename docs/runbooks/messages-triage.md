# Messages: analysis, dispatch and recovery

## Operation

Personal → agent tasks/incubations opens **Sua decisão**. Only pending authorizations and
blocking registered questions enter this view. **Em tratamento** includes new/unanalysed work;
**Aguardando** contains analyzed blockers; **Resolvidas** retains delivered work. Legacy view
URLs and archive remain available. Moodle proposals retain their dedicated approval flow.

**Analisar e encaminhar** queues all eligible work for the selected agent/context, independently
of page, search and date filters. Reloading recovers the durable job. Duplicate active requests
coalesce. Progress already applied survives a provider outage or process restart.

Enable `MESSAGE_TRIAGE_ENABLED=true` after migration `e3d9a1c56f84`, bridge deployment and
delivery bootstrap. Background workers use the same engine; tests always disable background
workers. `MISSION_CYCLE_ENABLED` remains false. The analysis identity is Athos for internal work,
Maia/Lara for their private contexts. Model calls receive no tools or execution authority.

## Authority and evidence

Analysis cannot authorize, replay failed/partial operations, accept reviewed ProjectTasks or
promote incubations. Only new, authorized, context-complete work may enter the existing
dispatcher. Admission checks fresh source/context again inside the existing reservation lock.

Self informational returns become archived history linked to the original. Future execution
results stay on the original message when sender and executor are the same agent. This does
not prohibit executable self-assigned work.

Moodle resolution requires persisted finished/completed approval, exact message hash and DONE
report. Independent delivery uses admin-only `POST /api/v1/demands/{id}/delivery` with current
`expected_updated_at`, verified `git:<sha>`, summary and optional executor/related completed
message. Evidence is checked in the recorded working directory. Governed ProjectTask work must
use its existing evidence/review flow. Resolution never rewrites the old run or attempt.

Delivery audit is content-bound and vetoes dispatch even when triage is disabled. The newest
analysis cannot erase this veto. Editing the work's content requires new evidence/authorization.

## Recovery

Jobs are leased/fenced, renewed between batches and every 30 seconds during model calls. Expired
jobs resume pending items, with three bounded claims. A canceled worker drains its model task.
A provider failure preserves pending contextual items, while later deterministic evidence still
applies. Automatic failed-job retries are spaced by ten minutes; the operator can retry manually.

Linked questions, quota expiry, executor configuration, task dependencies, project/mission/
baseline versions, deliveries and related message versions invalidate analysis. Counts and rows
use the same materialized SQL classification; stale recommendations disappear until reanalysis.

The bridge's `/v1/agent-runs/availability` reads bounded native Codex session rate-limit metadata.
Only fresh positive observations after current auth metadata supersede older Codex usage-limit
records. Other runtimes, unknown windows and stale/exhausted observations preserve their limits.

For staged rollback set `MESSAGE_TRIAGE_ENABLED=false`; delivery vetoes remain. Return both
images and the bridge working directory to the recorded previous release if runtime rollback
is necessary. This additive migration may remain installed; do not remove audit or delivery
history to roll back presentation.

## Missions selector repair

The static `GET /api/v1/products/versions` must precede `/products/{product_id}`. Otherwise
`versions` is interpreted as a UUID and mission create/edit fails with 422. The regression
`tests_unit/test_mission_version_selector.py` checks real ASGI routing without database writes.
Mission status filters provide an explicit all-status choice; failed selectors identify the
missing dependency and retain separate retry/back actions.

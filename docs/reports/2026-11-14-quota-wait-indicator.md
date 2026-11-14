# Quota wait indicator — implementation and validation

## Approved behavior

Marcelo approved nonterminal quota waits for Codex, Claude Code and agy, with
the same executor retained until reset. Quota exhaustion is not a work failure
and does not authorize archiving or replaying effects. Historical archived
records are not automatically reopened.

## Implementation

- `waiting_quota` preserves the prior run/output and records the provider reset
  when known. Unknown reset remains null and cannot launch an automatic retry.
- Waiting is shared by Messages, personal agent tasks and chat delegations.
  Executor identity and timezone-bearing reset dates remain visible; missing
  reset is explicitly identified. Quota exits do not consume the work retry budget.
- Ordinary continuations use the same executor and normal dispatch guards.
  Protected continuations require effects review, evidence, exact prior run
  confirmation and the owning approval/task workflow before release.
- The scheduler, classification, triage and mission cycle recognize the wait;
  it does not occupy an execution slot, create failure diagnostics or trigger
  automatic archival. Independent review found and corrected presentation,
  effective-budget and queued-executor consistency gaps.

## Frontend verification

- `npm test -- --run src/hooks/useDemands.test.ts src/pages/demands/MessageLabels.test.tsx src/pages/demands/index.test.tsx src/pages/personal/AgentTasksTab.test.tsx src/components/chat/RunningPanel.test.tsx`: **76 passed**.
- `npm run build`: **passed**, including locale parity and TypeScript. Existing
  large-chunk/dynamic-import warnings remain.
- Chrome/CDP using only local synthetic fixtures, **390px and 1440px**: Messages
  row/detail, sender Athos versus executor Aramis/Porthus/Dartan, personal waiting
  table, known reset/timezone and unknown reset, no document overflow or writes:
  **passed** on the feature UI before integration. Script
  `/tmp/forgehub_quota_browser.py`; screenshots under `/tmp/forgehub-quota-browser/`.
- Premium static audit: **58 findings**, identical to the root-checkout baseline;
  **zero new findings**. Existing unrelated findings were not changed.

## Backend verification and database boundaries

Final integration homologation on the current `main` plus this feature:

- In `backend`, `ENVIRONMENT=test .venv/bin/pytest -q --tb=short app/tests/test_agent_failover.py app/tests/test_message_classification.py app/tests/test_executor_wait_recovery.py app/tests/test_demand_workflow.py app/tests/test_mission_cycle.py`: **90 passed in 47.85s** against the isolated database.
- The five targeted frontend suites: **76 passed**; `npm run build`: **passed**, including locale parity and TypeScript. Existing large-chunk/dynamic-import warnings remain.
- Ruff on changed Python modules/tests and both quota migration files: **passed**.
- `git diff --check`: **passed**.
- The first supervisor run found one regression: query-count budget became 11
  instead of at most 10. The query was combined with the existing agent batch
  without changing the test; final full run is green.
- Independent reviewer: **no BLOCKER/HIGH remaining**, including a final review
  and PostgreSQL compilation of the combined quota `EXISTS` query. Review was
  read-only and distinct from backend/frontend implementers.

All behavioral tests use `ENVIRONMENT=test` and isolated PostgreSQL on port 5439,
with the exclusive test lock. No production database tests, reset, stamp or
downgrade were performed.

The isolated database already carried concurrent revision `c3e5a7b9d1f2` from
`foundation-memory-audit`. Tests install this feature's additive schema under the
exclusive lock and leave that Alembic revision unchanged. For the current release
chain (`e5a7c9d1f3b4`), integration adds the no-op merge revision
`49707c727f82`, joining it with `d3f6a8b2c901`.

`ENVIRONMENT=test alembic heads`: sole integrated head `49707c727f82`.
`ENVIRONMENT=test alembic upgrade e5a7c9d1f3b4:head --sql`: **passed**; SQL
includes the quota schema change and merge revision, generated without connecting
to any database. The production migration has not been executed. Downgrade refuses
live quota waits to preserve run evidence.

## Publication

The integration candidate is `release/quota-wait-indicator`, based on current
`main` at `370ac7e`, with quota implementation `ba575a1` and migration merge
`49707c727f82`. Push, production migration and deploy await approval of this
reviewed integrated content.

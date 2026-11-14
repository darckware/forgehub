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
  **passed**. Script `/tmp/forgehub_quota_browser.py`; screenshots under
  `/tmp/forgehub-quota-browser/`.
- Premium static audit: **58 findings**, identical to the root-checkout baseline;
  **zero new findings**. Existing unrelated findings were not changed.

## Backend verification and database boundaries

Supervisor final homologation:

- In `backend`, `ENVIRONMENT=test /root/project/forgehub/backend/.venv/bin/pytest -q --tb=short app/tests/test_agent_failover.py app/tests/test_message_classification.py app/tests/test_executor_wait_recovery.py app/tests/test_demand_workflow.py app/tests/test_mission_cycle.py`: **90 passed in 48.41s**.
- Ruff on all changed Python modules/tests and the new module/migration: **passed**.
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
exclusive lock and leave that Alembic revision unchanged. This does not establish
merged migration-chain compatibility with the concurrent branch.

`ENVIRONMENT=test alembic heads`: sole head `d3f6a8b2c901` on this branch.
`ENVIRONMENT=test alembic upgrade b8e2c4a6d1f9:d3f6a8b2c901 --sql`:
**passed**, SQL generated without connecting to production. Downgrade refuses
live quota waits to preserve run evidence.

## Publication

Implementation is isolated in `fix/quota-wait-indicator`; merge, push, production
migration and deploy require approval of the reviewed final content.

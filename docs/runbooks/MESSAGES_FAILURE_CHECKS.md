# Messages failure-check operations

Last updated: 2026-10-29

Architecture and boundaries: [Messages](../architecture/MESSAGES.md#failed-execution-checks-2026-10-29).
Migration: `e83c1a7d29b4`, additive nullable FK/index/check on `company.agent_demands`.
The current develop chain is `e4b8c1d7a9f3` → `f2c7a4e9b1d3` (merged M0.0 mission base) → `e83c1a7d29b4`; an installation still on the first revision must apply both successors.

## Rollout

1. Validate backend dispatch/check/workflow/evidence/retention tests against `ENVIRONMENT=test`, frontend tests/build, Ruff and `git diff --check`.
2. Commit and push the reviewed changes. Capture current backend/frontend image IDs and production Alembic revision; take a private PostgreSQL custom-format backup and verify its table of contents. Never store dump contents or credentials in the repository.
3. Apply `e83c1a7d29b4` against the ForgeHub production database before starting the new backend. The old application tolerates the nullable additive column. Use the deployed migration toolchain and existing Vault-backed Compose workflow; do not change other applications' databases.
4. Run `./scripts/deploy.sh`. This builds images using the committed SHA/version/build timestamp and publishes the backend/frontend with `scripts/compose-vault.py`. It does not itself run Alembic migrations.
5. Verify backend health, frontend response, production revision and committed build metadata. Check aggregate diagnostic/source counts, absence of duplicate source links and links retaining exact run IDs. Existing eligible failures will be handed to checks by the completion worker; do not manually run or replay those tasks again.
6. Confirm the source/check UI links and scheduled time. A known quota reset schedules after reset + five minutes; absent/unrecognized dates remain diagnostic work, not an inferred reset.

## Recovery

- Keep exact run IDs, evidence and attachment rows/files. A runner 404, network timeout or stale state never proves that a process has stopped.
- Failed checks remain blocked for intervention; they do not recursively generate checks. Use existing investigation/approval controls and confirm the exact runner identity before any uncertain retry.
- Source/current approval, blocking questions, Moodle permissions, dependencies and capacity remain gates. An approval must not advance a scheduled reset.
- To roll back application images, restore the recorded backend/frontend images using the existing Compose configuration. The additive database column is compatible with old application code; leave it in place to preserve links. Do not downgrade the schema or restore a backup over new executions without a separate reconciliation plan.
- Historical archived/consolidated records are not revived. Linked source/check messages and attachments are protected from deletion; archive is the supported presentation operation.

## Verification evidence

Release validation: 96 related backend tests and 398 frontend tests passed; Ruff and diff checks passed.

- Related backend release suite: dispatch, contingency, Messages, retention, evidence, execution guards and diagnostic checks.
- Frontend: execution classification, source/check navigation, pending states, full Vitest suite and production build.
- Browser: local mocked source/check navigation in both directions, retained error/output, reset schedule, desktop and narrow viewport.
- Independent review findings about pending-inbox authorization, old-failure starvation, source blocking questions, future-schedule preservation and attachment retention were corrected and covered by regression tests.

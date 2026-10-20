# Client Reports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Generate persistent reviewed client reports and expose tenant-scoped read access.
**Architecture:** Immutable HTML/JSONB snapshots in company; admin workflow plus separate hashed read credentials. Darckware is the authenticated customer frontend.
**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL, Alembic, React/Vite, TanStack Query.
**Spec:** docs/superpowers/specs/2026-09-14-client-reports-design.md

## Global Constraints

- UUID/TimestampMixin and company schema; no cross-database access or foreign keys.
- HTML only, all dynamic values escaped; no invented support-hour balances.
- Internal admin access; external per-client hashed clr_ credentials; cross-client resources return 404.
- No automatic sending, external execution or live database testing.
- Use dedicated test configuration `/tmp/forgehub-pending-test-env` and `/tmp/forgehub-pending-venv/bin/python`.

### Task 1: Persistent reports and scoped API

**Files:**
- Create backend/app/db/models/client_report.py, backend/app/api/schemas/client_report.py.
- Create backend/app/core/client_reports.py, backend/app/core/client_read_auth.py.
- Create backend/app/api/routes/client_report.py, backend/app/api/routes/client_access.py.
- Create backend/alembic/versions/<revision>_add_client_reports.py.
- Modify backend/app/db/models/__init__.py and backend/app/main.py.
- Tests: backend/app/tests/test_client_reports.py, backend/app/tests/test_client_access.py.

**Interfaces:** produce the exact HTTP contracts in the spec. Core function `generate_client_report(db, client_id, period_start, period_end, *, kind, irregularity_id=None, generated_by_user_id=None)` returns ClientReport; `run_monthly_report_pass(db_factory, now=None)` isolates each client's transaction and returns number created. Auth dependency `get_client_read_credential` returns ClientReadCredential.

- [ ] Add regression fixtures with two clients, workstations, irregularities and an admin. Assert schema/API absence first, then implement models/migration. Migration descends from current `5a8c1e7d9f20`; verify actual head before writing.
- [ ] Write meaningful generation regressions, including these invariants (adapt fixture names):

```python
first = await generate_client_report(db, client.id, date(2026, 8, 1), date(2026, 8, 31), kind="monthly")
again = await generate_client_report(db, client.id, date(2026, 8, 1), date(2026, 8, 31), kind="monthly")
assert again.id == first.id
assert "<script>" not in first.html_content
assert "&lt;script&gt;" in first.html_content
```

- [ ] Implement snapshot queries/escape/HTML, monthly conflict handling and audit. Validate interval and client/incident in route and core as needed.
- [ ] Add admin routes and read-credential issuance/revocation. Verify responses never include token_hash; only issuance contains plaintext.
- [ ] Add external routes/middleware carve-out and tests:

```python
headers = {"Authorization": f"Bearer {client_a_token}"}
response = await http.get(f"/api/v1/client-access/clients/{client_b.id}/reports", headers=headers)
assert response.status_code == 404
response = await http.get(f"/api/v1/client-access/clients/{client_a.id}/reports/{draft.id}/download", headers=headers)
assert response.status_code == 404
```

- [ ] Add hourly poll registration using existing lifecycle pattern; test pass directly with injected time/factory and no lifespan production loop.
- [ ] Apply migration to dedicated PostgreSQL only; run both new test files, relevant auth/ingestion/client-route regressions, Ruff and diff check. Record commands/results. Commit scoped files.

### Task 2: Internal report workflow

**Files:** frontend/src/hooks/useClientReports.ts; frontend/src/pages/clients/[id].tsx; frontend/src/pages/clients/client-reports.tsx; frontend/src/pages/clients/client-reports.test.tsx; frontend/src/i18n/locales/{pt-BR,en,es}/clients.json; DESIGN.md as required by UI skill.

**Interfaces:** consume exact Task 1 HTTP contracts through frontend/src/lib/api.ts. Produce report list and generation/review/download actions inside client detail, with occurrence query parameter supported.

- [ ] Read existing design context and required frontend skills; preserve established components/layout.
- [ ] Write React Testing Library tests for empty/loading/error, generation payload, monthly validation, download, reviewed/unreviewed transition, permission gating and duplicate submission.
- [ ] Implement hooks and component using current TanStack Query conventions; invalidate client report list after mutations. Blob download includes bearer via shared client and revokes object URL.
- [ ] Wire component and translations for pt-BR/en/es; keep operational implementation details out of product copy. UI cannot imply hourly data exists.
- [ ] Run focused tests, npm run build and inspect rendered page if browser available; document screenshot limitation otherwise. Commit.

### Task 3: Integrate and document

- [ ] Review complete diff against spec and resolve findings. Preserve any unrelated worktree changes.
- [ ] Add runbook with admin generation/review/credentials, environment setup for server-side consumer, and tests/rollout requirements.
- [ ] Integrate sequentially with Messages changes to main.py and host bridge; rerun covering tests when merged changes affect behavior.
- [ ] Update central finalization ledger and docs/PENDENCIAS.md with exact revision/evidence. Do not label deployment or Darckware consumer complete until those separate tasks are verified.

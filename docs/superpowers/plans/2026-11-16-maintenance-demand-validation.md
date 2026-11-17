# Maintenance Demand Validation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure a maintenance demand that stops for human correction is visible in the correct Personal queue, opens from Messages at the same record, and has a repeatable execution/correction checklist.

**Architecture:** Backend classification remains authoritative. The frontend maps `operator_decision` and destination to the owning tab and label: authorization → Aprovações, correction/reconciliation → Decisões, question → Respostas, incubation → Incubações. Personal queue predicates and badges remain disjoint.

**Tech Stack:** React, TypeScript, i18next, Vitest, FastAPI, SQLAlchemy, pytest.

**Spec:** `docs/superpowers/specs/2026-11-08-messages-triage.md`; current implementation is in `frontend/src/hooks/useAgentTasksViewModel.ts`, `frontend/src/pages/personal/AgentTasksTab.tsx`, and `backend/app/core/demand_management.py`.

## Global Constraints

- Keep Tarefas defaulted to `processing`; do not put approvals or blocking questions in Decisões.
- Incubações retain their own guarded decision flow.
- Preserve old `workView=decision` links by resolving them to Decisões.
- A failure does not automatically dispatch or approve work; an operator action still uses the existing confirmation dialog.
- Do not mutate a real maintenance demand during validation; use isolated fixtures.

## Review Focus

1. `correction` and `reconciliation` from `agent_tasks` must resolve to Decisões.
2. `authorization` from `agent_tasks` and `moodle_approvals` must resolve to Aprovações.
3. A blocking question with an ID must open the exact card in Respostas.
4. Incubation decisions must remain in Incubações, including old links.
5. A correction action must not occur when the confirmation is cancelled.

## Task 1: Finish and preserve the separated Personal queues

**Files:**
- Review: `frontend/src/hooks/useAgentTasksViewModel.ts`, `frontend/src/pages/personal/AgentTasksTab.tsx`, `frontend/src/pages/personal/AgentTasksTab.test.tsx`.
- Review: `backend/app/core/demand_management.py`, `backend/app/tests/test_demand_management.py`, `backend/app/tests/test_demand_management_views.py`.

- [x] Add the Decisões tab and default Tarefas to `processing`.
- [x] Exclude pending task authorizations and blocking questions from the Decisions list; retain Incubações in its own group.
- [x] Verify existing action confirmation remains in the Decisions flow.
- [x] Re-run focused queue tests after routing changes and verify counts and rows use identical predicates (`AgentTasksTab.test.tsx`, backend predicate/view tests).

## Task 2: Fix Messages destinations and labels

**Files:**
- Modify: `frontend/src/lib/messageLabels.ts`.
- Modify: `frontend/src/pages/demands/MessageLabels.tsx`.
- Test: `frontend/src/lib/messageLabels.test.ts`.
- Test: `frontend/src/pages/demands/index.test.tsx`.
- Modify: `frontend/src/i18n/locales/{pt-BR,en,es}/demands.json`.

- [x] **Step 1: Write failing routing tests.** Update the correction/reconciliation case to expect `workTab=decisions`; add a destination-label assertion for Decisões. Keep authorization, questions, and incubations mapped to their existing tabs.
- [x] **Step 2: Run the focused tests and confirm they fail because `agent_tasks` is hard-coded to Aprovações.**
- [x] **Step 3: Implement minimal destination and label mapping.** Authorization stays in Aprovações; correction/reconciliation open Decisões; questions open Respostas; Incubações and Moodle retain their respective tabs. Use localized labels from `demands.json`.
- [x] **Step 4: Re-run the focused tests and `npm run i18n:check`; final combined frontend verification passed 91 tests.**

## Task 3: Prove the maintenance demand lifecycle

**Files:**
- Create: `docs/runbooks/maintenance-demand-validation-checklist.md`.
- Review: `frontend/src/pages/demands/index.test.tsx`, `frontend/src/pages/personal/AgentTasksTab.test.tsx`, and backend queue tests.

- [x] Add the checklist steps below to the runbook with explicit expected results and evidence fields (demand number, source status, destination tab, action, final status).
- [x] Verify with an isolated correction fixture that the Messages link opens the same demand in Decisões; the decision tabs/counts stay separated by their backend predicates.
- [x] Verify authorization, question, and incubation fixtures each open their separate tabs.
- [x] Verify cancelling the confirmation leaves the item unchanged and no decision request is sent; backend action rules are covered by the isolated queue tests.
- [x] Run focused frontend tests (91 passed), the SQL predicate and catalog tests (2 passed), the two isolated backend view tests (2 passed in the previous checkpoint), locale check, frontend build, Ruff, and `git diff --check`.
- [ ] Check the UI at 390 px and 1440 px if an allowed local preview/browser path is available; prior browser path was blocked by the sandbox.

**Operator checklist content:**

1. From Messages, identify whether the row is in Incubação or Execução and read its status label.
2. For **Precisa de correção** or **Reconciliação pendente**, follow the Pessoal link and confirm it opens Decisões with the same demand number and subject.
3. Confirm the row is not also counted in Aprovações or Incubações; record the visible count and row.
4. Open the demand details, review the failure/evidence, choose an allowed correction action, and inspect the confirmation before deciding.
5. Cancel once in the test fixture and confirm no state or dispatch change; then confirm only in the isolated fixture and record the resulting state/history.
6. Repeat routing checks for an authorization, a blocking question, and an incubation; expect Aprovações, Respostas, and Incubações respectively.
7. Record test environment, demand fixture ID, queue, action, result, and any blocked step. Never use a production demand as a test fixture.

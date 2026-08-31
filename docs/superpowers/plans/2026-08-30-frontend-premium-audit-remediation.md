# Frontend Premium Audit Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the ForgeHub frontend premium audit from 154 errors to zero while preserving existing workflows and completing the Agent Activity integration.

**Architecture:** Establish one durable UX contract and machine-readable ownership manifest, then fix repeated violations at their shared owners or through bounded mechanical migrations. Treat the premium audit as the regression test for static contracts and retain the existing Vitest/build/browser checks for runtime behavior.

**Tech Stack:** React 18, TypeScript, Tailwind CSS, Vitest, Vite, frontend-design-premium audit tooling.

**Spec:** `DESIGN.md`, `docs/specs/PRD.md`, `docs/reference/BUSINESS_RULES.md`, and `docs/plans/2026-08-29-agent-activity-continuity-design.md` from commit `4b11de3`.

## Global Constraints

- Existing runtime CSS variables remain the canonical visual-token source.
- Native select and date popups remain accepted platform-owned variants; do not invent a new authored listbox/calendar in this migration.
- Forms use application-owned validation via `noValidate`; existing schema/manual handlers remain authoritative.
- Product textareas use `resize: none`; existing height, rows, and scroll behavior remain intact.
- False affordances are removed or connected to real behavior; no unimplemented control remains enabled.
- No domain transitions, permissions, retention rules, or destructive behavior are changed.

---

### Task 1: Record canonical frontend ownership

**Files:**
- Create: `UX-CONTRACT.md`
- Create: `premium-ui.json`
- Modify: `DESIGN.md` only if a verified durable rule is missing

**Interfaces:**
- Produces: canonical ownership for `Select/Listbox`, `Date`, `Form`, `Scrollbar`, `Toast`, and `CRUD`.
- Consumes: existing shared primitives under `frontend/src/components/ui/`, runtime tokens in `frontend/src/index.css`, and existing route/domain behavior.

- [ ] **Step 1: Preserve the failing audit evidence**

Run: `python <premium-skill>/scripts/audit_project.py . --mode report --output /tmp/forgehub-premium-audit.json`

Expected: 154 findings grouped under six rule IDs.

- [ ] **Step 2: Create the UX contract and manifest**

Record native select/date ownership, `ConfirmDialog` as the shared confirmation owner, application-owned form validation, global scrollbar ownership, existing inline/live-region feedback, and project commands `npm test -- --run` plus `npm run build`.

- [ ] **Step 3: Verify contract resolution**

Run: `python <premium-skill>/scripts/audit_project.py . --mode report --no-write`

Expected: all 62 `ownership.native-*-undecided` findings are gone and no contract/map findings appear.

### Task 2: Harden shared controls and global scrolling

**Files:**
- Modify: `frontend/src/components/ui/button.tsx`
- Modify: `frontend/src/components/ui/textarea.tsx`
- Modify: `frontend/src/components/ui/confirm-dialog.tsx`
- Modify: `frontend/src/components/ui/confirm-dialog.test.tsx`
- Modify: `frontend/src/index.css`

**Interfaces:**
- Produces: explicit shared-button action forwarding, non-resizable textareas, accessible modal behavior, and standards-based plus WebKit scrollbar styling.
- Consumes: existing `ButtonProps`, `TextareaProps`, CSS semantic variables, and localized confirmation copy.

- [ ] **Step 1: Use the current audit and focused tests as failing evidence**

Run: `npm test -- --run src/components/ui/confirm-dialog.test.tsx`

Expected: dialog tests cover rich context, disabled confirmation, focus containment, inert background, Escape, and focus restoration.

- [ ] **Step 2: Implement shared-owner fixes**

Add `resize-none` to the shared textarea recipe, make action forwarding explicit in the shared button markup, and add `scrollbar-color` plus `scrollbar-width` to the global application surface.

- [ ] **Step 3: Verify shared owners**

Run: `npm test -- --run src/components/ui/confirm-dialog.test.tsx`

Expected: PASS.

### Task 3: Migrate forms and textarea consumers

**Files:**
- Modify: the 28 TSX form owners and 60 textarea call sites enumerated in `/tmp/forgehub-premium-audit.json`.

**Interfaces:**
- Produces: every product form declares `noValidate`; every literal/shared textarea call site declares `resize-none` without changing its value, handler, rows, or height.
- Consumes: existing submit handlers and shared `Textarea` component.

- [ ] **Step 1: Apply bounded mechanical form migration**

Add `noValidate` to every audited opening `<form>` tag and do not alter handlers or validation logic.

- [ ] **Step 2: Apply bounded mechanical textarea migration**

Add `resize-none` to every audited textarea class, replacing `resize-y` where present; add a class only when none exists.

- [ ] **Step 3: Run the static regression test**

Run: `python <premium-skill>/scripts/audit_project.py . --mode report --no-write`

Expected: no `form.novalidate-missing` or `form.textarea-resize-missing` findings.

### Task 4: Remove false affordances

**Files:**
- Modify: `frontend/src/pages/project-scope/index.tsx`
- Modify: `frontend/src/pages/cockpit/index.tsx`
- Modify: `frontend/src/components/ui/button.tsx`

**Interfaces:**
- Produces: link-styled navigation without nested interactive controls, no enabled mock release action, and a statically traceable shared button action boundary.

- [ ] **Step 1: Correct each audited control at its behavior boundary**

Render project navigation as a styled `Link`, remove the unimplemented cockpit action, and preserve consumer-provided button events in the shared owner.

- [ ] **Step 2: Verify no false affordance remains**

Run: `python <premium-skill>/scripts/audit_project.py . --mode strict --no-write`

Expected: zero findings and exit 0.

### Task 5: Full regression and integration

**Files:**
- Modify: implementation files only when verification reveals a reproducible regression.

**Interfaces:**
- Produces: a verified `feature/agent-activity-continuity` branch ready to integrate into `develop`.

- [ ] **Step 1: Run frontend verification**

Run: `cd frontend && npm test -- --run`

Run: `cd frontend && npm run build`

Expected: all tests pass and build exits 0; existing bundle-size warnings may remain.

- [ ] **Step 2: Run backend feature and lint verification**

Run: `cd backend && .venv/bin/pytest app/tests/test_agent_activity.py -v`

Run: `cd backend && .venv/bin/ruff check app`

Expected: PASS.

- [ ] **Step 3: Exercise the live browser flow**

Verify `/agent-activity` at desktop and narrow widths, loading/empty/degraded states through tests, agent selection, canonical links, monitoring confirmation/cancel/failure/success, keyboard focus, and reduced motion.

- [ ] **Step 4: Commit and integrate**

Commit the audit remediation and Agent Activity UI, merge `feature/agent-activity-continuity` into `develop`, restart `./dev.sh` from the primary checkout, and recheck health.

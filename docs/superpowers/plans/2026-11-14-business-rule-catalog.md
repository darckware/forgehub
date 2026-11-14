# ForgeHub Business Rules Catalog Plan

> **For agentic workers:** Use `superpowers:executing-plans` to continue this documentation task section by section. Do not infer intended behavior from outdated specs.

**Goal:** Create a traceable Portuguese catalog of ForgeHub business rules so agents can follow current behavior and identify when a change needs a decision or implementation adjustment.

**Architecture:** Add `docs/business_rules/README.md` as the guide and index, with separate domain files for identity and authority, agents and Messages, Factory and delivery, missions and orchestration, remote operations, Auditor and operations, and data/integrations. Each rule states the behavior, enforcement status, and implementation/test/documentation sources. Existing references remain in place and are linked rather than silently replaced.

**Tech Stack:** Markdown; FastAPI/SQLAlchemy implementation and tests as evidence sources.

**Spec:** User request in the current session; repository authority hierarchy in `docs/README.md`.

## Global Constraints

- Record current behavior from code, migrations, and tests; label goals and unresolved mismatches separately.
- Cite exact repository paths and line numbers where practical; name tests that cover critical behavior.
- Never turn a proposal, historical document, or unmerged worktree into an implemented rule.
- Preserve existing canonical documents and cross-link them; do not move or overwrite them as a shortcut.
- Write in Brazilian Portuguese for agents implementing changes.

## Review Focus

- A rule documented as implemented must be backed by current code or migration, not an old PRD.
- A disabled feature must remain distinguishable from an active capability.
- Conflicting documents must be listed as a gap with the code-backed current behavior.
- Cross-domain permissions, lifecycle transitions, rollback, and audit evidence must not disappear in the split.
- Every rule update must say which implementation and tests need revisiting when behavior changes.

---

### Task 1: Inventory and source hierarchy

- [x] Inspect repository documentation map, existing business-rule reference, route/model domains, and current branch baseline.
- [x] Collect independent read-only inventories for identity/remote access, agent/Messages lifecycle, and Factory/operations/Auditor.
- [x] Reconcile findings with current `main` only; exclude unmerged worktrees.

### Task 2: Build the rule catalog

- [x] Create a short README with the authority hierarchy, status labels, domains, and update procedure.
- [x] Create domain guides with stable rule IDs, imperative behavior, status, implementation sources, and tests.
- [x] Link existing business-rule, architecture, runbook, model, and help references rather than copying them wholesale.

### Task 3: Accuracy review

- [x] Search for uncovered route/model domains and compare each rule against current code and tests.
- [x] Record confirmed contradictions and known implementation gaps as `GAP`, never as active rule.
- [x] Complete independent read-only review; fix material findings.
- [x] Check links, paths, line references, and `git diff --check`.

### Task 4: ForgeHub release control design

- [x] Record the chosen scope: the ForgeHub app itself, under `Controle do Sistema`.
- [x] Define context, categories, SemVer policy, auditability, and separation from deploy.
- [x] Obtain approval of the design (Marcelo, 2026-11-14).
- [ ] First complete previous remote-access/Messages corrections and Auditor review, as Marcelo requested with his approval.
- [ ] Then create the release-control implementation plan and separate code worktree.

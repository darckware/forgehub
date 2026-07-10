# ForgeHub — Context Brief (CONTEXT BRIEF)

Canonical artifact for the **Contextualização** pipeline stage (`docs/BUSINESS_RULES.md` §10). Captures the business context that precedes — and should be cited by — the PRD, rather than letting that context live only in conversation history.

## 1. Problem statement

Teams running software delivery with AI agents have no single system of record tying a feature/bug/task back to *why* it exists, *which* product/version/project it belongs to, *who* (or which agent) executed it, and *what evidence* proves it was done — let alone gating that work behind mandatory artifacts and approvals. Without that chain, agent-driven work is unauditable and ungoverned: nothing stops a feature from shipping without a PRD, a stage from completing without its required artifacts, or an agent from quietly rewriting a finalized module.

## 2. Stakeholders

- **Marcelo D. Ferreira** — owner/product lead; defines scope, approves planning, decides triage outcomes.
- **AI agents** (e.g. Archimedes, and Hermes Foundation sub-agents/skills) — execute tasks, produce artifacts, and must read governance state (`is_locked`, required artifacts, gates) before acting.
- **Future ForgeHub users** — any team adopting ForgeHub to plan/govern their own product delivery, not just this repository's own development.

## 3. Why ForgeHub is its own pilot

Rather than write fictional sample data, ForgeHub's own development (this session's real work: vault path fix, sidebar grouping, traceability hardening, documentation, P1 bug fixes, artifact-type/lock/structure modeling) is registered as a live Product → Project → Pipeline → PlanningItem → Task → Artifact chain. This keeps the model honest: every entity in the pilot traces to a real file, commit, or decision instead of a placeholder.

## 4. Constraints

- Stack is fixed per `docs/TECHNOLOGY.md` (FastAPI/SQLAlchemy/Postgres backend, React/Vite/shadcn frontend) — not open for re-litigation per project.
- Business rules live at the API layer, not as DB triggers (`CLAUDE.md`).
- Cross-domain FKs are string-form/lazy; no cross-module ORM imports.
- `is_locked` (Artifact, ProjectStructureNode) is advisory, not a filesystem permission — see `docs/BUSINESS_RULES.md` §8.

## 5. Success criteria for this phase

- Every entity created in the pilot links back to product/version/project/planning/pipeline/owner/status/audit-trail (core invariant, `CLAUDE.md`).
- The Contextualização stage's required artifact (this document) exists and is approved before the Documentação stage's PRD is treated as complete.

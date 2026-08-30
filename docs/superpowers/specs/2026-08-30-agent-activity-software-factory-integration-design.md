# Agent Activity and Software Factory Integration Design

**Date:** 2026-08-30  
**Status:** Approved by Marcelo  
**Scope:** Agent Activity operational read model, pre-project conception visibility, version closure consistency, integration, deployment

## Objective

Finish Agent Activity as ForgeHub's operational view of agent work across the complete Software Factory lifecycle. Work performed during Conception must be visible before a `Project` exists, then remain traceable after approval creates one or more delivery projects. Version publication must represent readiness of the whole `ProductVersion`, including every project under that version.

## Architectural decision

Agent Activity remains a projection over canonical ForgeHub records. It must not create a second project, task, execution, conception, approval, or release state machine.

A pre-project conception is represented as an operational context with `context_kind="conception"`, sourced from `DevelopmentRequest`, `ProductConcept`, and the current `ConceptRevision`. It is not represented by a synthetic `Project` row. Once `AuthorizeDeliveryPlanning` creates delivery projects, the read model exposes the canonical project identifiers alongside the originating conception identifiers so history can cross the transition without rewriting old events.

The existing `forge-agent-activity/v1` response may be extended additively. Existing consumers keep their current project fields; new nullable conception/context fields supply the pre-project case.

## Canonical ownership and identity

| Concern | Canonical owner | Agent Activity projection |
| --- | --- | --- |
| Intake | `DevelopmentRequest` | title, type, status, requester, product, canonical route |
| Conception | `ProductConcept` and current `ConceptRevision` | conception identity, review state, current revision, linked agents/messages/approval |
| Approval | governed approval request and decision | pending/decided state and canonical link |
| Delivery authorization | `AuthorizeDeliveryPlanning` result | transition from conception context to one or more real projects |
| Project work | `Project`, planning items, tasks, assignments, executions | project/task/owner/current action |
| Version readiness | `ProductVersion` plus every project and task under it | aggregate blocking state, project-level breakdown, publish eligibility |

Stable activity keys include the source type and source UUID. They never derive identity from titles. Historical conception events keep conception keys after projects are created.

## Read-model changes

Introduce an additive operational-context shape:

- `context_kind`: `conception | project`;
- `context_id`: canonical UUID for the context kind;
- `product_id` and `product_name`;
- nullable `development_request_id`, `concept_id`, and `concept_revision_id`;
- nullable `project_id`, `project_name`, and `working_directory_path`;
- `canonical_path`;
- `status`, `title`, `created_at`, and `updated_at`.

Agent rows, flow items, incidents, message edges, and timeline events may reference a context. Project-specific fields remain nullable for pre-project work. The backend derives links only from structured identifiers such as `product_id`, request/concept references, approval subject references, message `project_id`, assignments, and executions. It must not parse free-form message prose to manufacture relationships.

The unfiltered topology shows active conceptions when canonical evidence connects an agent to the conception through a structured request, approval, or message context. A project filter continues to show only that project. A conception filter shows its intake, approval, communication, and transition events plus the projects created from it.

## User interface

The existing continuity-first layout remains authoritative:

- topology: agents, conceptions, projects, shared resources, and real relationships;
- current-flow board: conception items use the same deterministic operational stages as other sources while retaining `source_type` and source status;
- severity inbox: conception blockers and pending approvals appear with canonical links;
- selected-agent inspector: current context labels whether work is in Conception or Delivery;
- history: the planning lane preserves intake, submission, decision, and delivery-authorization events before project execution events.

Conception nodes are visually distinct by label and icon, not color alone. Their accessible name includes product, conception title, and status. No drag interaction is required to understand them; all topology relationships have a textual equivalent.

Loading, empty, stale, partial-source, error, keyboard, reduced-motion, narrow viewport, and long-content behavior follows `DESIGN.md`, `UX-CONTRACT.md`, and the approved Agent Activity designs.

## Version closure correction

Publication is a `ProductVersion` operation. The backend publish command already checks unfinished tasks across every project belonging to the version and returns a structured blocking list. The frontend must match that invariant before the confirmation dialog opens.

When a version is selected, the page computes and displays:

- every project under the version;
- terminal and pending task counts per project;
- aggregate version totals;
- a blocking list grouped by project;
- publish eligibility only when the version has at least one task and every task across every project is terminal.

Selecting a project may focus its detail, but it must not weaken the version-wide gate. If no version exists, direct project closure remains scoped to the selected project. The publish button uses the shared disabled/busy behavior and provides an inline explanation when unavailable. The backend remains the final authority and its `409` blocking response stays recoverable in the UI.

## Integration strategy

The Agent Activity feature branch is completed and verified in its existing isolated worktree. Existing uncommitted changes are treated as user/agent work and are preserved. Changes are separated into reviewable commits: operational read model, operational views, conception integration, version-closure correction, and verification/documentation.

After the feature branch passes its focused checks, it is integrated into `develop` together with the current Software Factory changes. Conflicts are resolved by preserving the newer Software Factory workflows while retaining Agent Activity's canonical read-model contract. No broad reset, checkout, or deletion is used to reconcile the worktrees.

## Error handling and authority

- Missing optional telemetry marks only that source degraded; durable database records remain visible.
- Missing conception/project relationships remain explicitly unknown rather than inferred from text.
- Monitoring requests stay idempotent and permission checked.
- Conception approval and delivery authorization continue through Governance; Agent Activity does not approve or authorize them.
- Publishing remains explicit, permanent, and server validated.
- Push and deployment occur only after local verification. Post-deploy health and authenticated route smoke checks are required before completion is reported.

## Tests and verification

Backend tests cover:

- pre-project conception serialization;
- additive context references on agents, flow items, incidents, and timeline events;
- conception-to-multiple-project transition without duplicate history;
- structured-link-only aggregation;
- project and conception filtering;
- version publication blocked by a pending task in any sibling project;
- successful publication completing every project only after all version tasks are terminal.

Frontend tests cover:

- schema parsing for conception and project contexts;
- topology, flow, inspector, and history rendering for a conception without a project;
- transition rendering after delivery authorization;
- version-wide totals and grouped blockers;
- publish control disabled by a pending sibling-project task;
- loading, empty, error, partial degradation, keyboard, focus restoration, reduced motion, and narrow layout.

Final verification includes Ruff, focused and full backend tests, focused and full frontend tests, TypeScript/Vite build, the premium UI audit, authenticated browser smoke tests for Agent Activity and Version Closure, push, deployment, health checks, and post-deploy smoke tests.

## Deployment and rollback

Use the repository's established deployment path and record the exact revision deployed. Apply database migrations only if the final implementation introduces schema changes; the preferred additive read-model implementation requires none.

Before deployment, capture current service status and revision. After deployment, verify backend health, frontend availability, authenticated Agent Activity data, conception visibility, version-wide closure blocking, and existing Software Factory navigation. If a health or smoke check fails, stop promotion and use the established recoverable deployment rollback path; do not rewrite shared git history or remove user changes.

## Acceptance criteria

- Agent Activity is buildable and deployable from committed source; no referenced component is missing.
- An active conception can appear before any `Project` exists without creating a synthetic project.
- Approval and delivery authorization connect that conception to all created projects while preserving history.
- Agent Activity shows structured project/conception ownership, communication, blockers, approvals, and source freshness.
- Version Closure cannot present a version as publishable while any task in any sibling project is unfinished.
- Backend and frontend agree on the version-wide publication invariant.
- Existing Software Factory changes are preserved and reviewed for compatibility.
- Commit, push, deploy, and post-deploy verification complete with auditable revision evidence.

## Non-goals

- Automatic conception approval, delivery authorization, agent reassignment, version publication, or deployment.
- Synthetic project records for pre-project work.
- A second activity/workflow persistence model.
- Parsing free-form agent messages as authoritative ownership or lifecycle state.
- Redesigning unrelated ForgeHub screens during this integration.

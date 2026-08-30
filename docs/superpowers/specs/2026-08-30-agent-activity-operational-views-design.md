# Agent Activity Operational Views Design

**Date:** 2026-08-30  
**Status:** Approved  
**Scope:** Agent Activity topology, current-flow board, and continuity history

## Objective

Make Agent Activity explain the live ecosystem without conflating current work with historical events. The page will expose three complementary projections of the same canonical ForgeHub records:

1. an interactive topology of agents, projects, the shared database, and real communications;
2. a current-flow board that answers where each operational item is now;
3. a swimlane history that answers what happened, when, and in which processing lane.

No new workflow, project store, task store, or execution state machine is introduced. Every visual object and relationship must be derived from existing records in the `company` schema or from the configured `company_postgres` resource.

## Product semantics

The existing horizontal “Continuity timeline” is an event log, not a queue. It currently combines messages, executions, checkpoints, approvals, and notifications into visually identical cards. The redesign must preserve those facts while making their different meanings explicit.

### Topology

- Agent nodes represent registered `Agent` records.
- Each agent node uses the registered `avatar_data_url`; `AgentAvatar` supplies initials when no valid image exists.
- Project nodes represent existing `Project` records connected to visible agents.
- A solid agent-to-project relationship means the agent owns a current task execution for that project.
- A dashed agent-to-project relationship means an active `ProjectAgentMembership` exists but no current execution is owned by that agent in the project.
- The database node represents `company_postgres`, with `company` shown as its application schema. It is a resource representation, not a new database record.
- Project-to-database relationships express the repository invariant that ForgeHub application records are persisted in the shared `company` schema.
- Directed agent-to-agent edges continue to represent actual `AgentDemand` message records only.
- Visual relationships must have a text equivalent in the topology relationship list and must never be inferred from mere visual proximity.

Projects visible in the unfiltered topology are limited to projects with current work or active memberships among visible agents. When a `project_id` filter is active, that project remains visible even if it currently has no execution.

### Current-flow board

The board is a read-only operational projection. It groups heterogeneous canonical records into a small display taxonomy while retaining the original source type and status on each card.

Display stages:

1. `incoming` — new/read messages or newly admitted work;
2. `planning` — incubation and planned project work;
3. `queued` — dispatched, ready, assigned, or pending work awaiting execution;
4. `executing` — running or in-progress work;
5. `verifying` — reported/verified work awaiting a final outcome;
6. `completed` — completed, done, or deployed work;
7. `attention` — failed, blocked, degraded, or approval-dependent work;
8. `archived` — archived or cancelled records retained for traceability.

These stage names are view-model classifications, not persisted statuses. Each item exposes `source_type`, `source_id`, `source_status`, canonical path, title, timestamps, and available agent/project/task/execution identifiers. Mapping rules are deterministic and covered by backend tests. Records must appear once in the board; an attention condition takes precedence over a normal in-flight stage.

### Continuity history

Historical events are grouped into semantic lanes:

- communication — messages and notifications;
- planning — planning/incubation transitions when present;
- execution — task execution lifecycle events;
- checkpoint — progress and recovery evidence;
- governance — approvals and governed decisions.

Time runs left to right. Events within a lane are sorted by their actual timestamps and stable keys. Selecting an agent or project emphasizes related events without hiding unrelated system context. Cards show a compact title, time, canonical source type/status, and link to the source record. Horizontal scrolling is allowed, but cards retain a readable minimum width and do not compress into the narrow columns shown by the prior design.

## Interaction design

The topology header gains an “Organize” action with a layout icon. Activating it recalculates deterministic positions for every visible node and clears saved manual positions for the current topology scope.

Agent, project, and database nodes can be repositioned with pointer dragging. Keyboard users can focus a node and move it with arrow keys; Shift plus an arrow uses a larger step. Dragging must not accidentally activate node selection. Positions are clamped inside the canvas.

Manual positions are stored only in browser `localStorage`, under a versioned key scoped by the active project filter. Persistence contains node identifiers and normalized coordinates only—never operational payloads. New or removed nodes are reconciled with deterministic defaults. Reduced-motion preferences disable packet travel and animated reorganization.

The page provides explicit “Fluxo atual” and “Histórico” view controls below the topology. The chosen view may persist locally. It does not mutate server state.

## Read-model contract

The existing `/api/v1/agent-activity` response remains additive and keeps `forge-agent-activity/v1` because existing fields and meanings remain compatible.

Add:

- `ActivityAgentOut.avatar_data_url: str | None`;
- `projects: list[ActivityProjectOut]`;
- `resources: list[ActivityResourceOut]`;
- `topology_relations: list[ActivityTopologyRelationOut]`;
- `flow_items: list[ActivityFlowItemOut]`;
- `ActivityTimelineEventOut.lane` and `source_status`.

`ActivityProjectOut` contains project identity, canonical path, and lifecycle status. `ActivityResourceOut` contains a stable key, kind, label, detail, and availability derived from read-model source health. `ActivityTopologyRelationOut` uses stable keys and typed endpoints with kinds `current_work`, `membership`, and `persistence`. Message communication remains in `message_edges` so its richer dispatch and response semantics are preserved.

`ActivityFlowItemOut` contains a stable key, display stage, source identity/status, title, timestamps, canonical path, and nullable relation identifiers. The backend owns normalization so all clients receive identical operational semantics.

## Layout and visual language

- Preserve the existing calm, dark mission-control language defined by `DESIGN.md` and `UX-CONTRACT.md`.
- Use compact bordered surfaces, semantic status colors, and text labels in addition to color.
- Do not add decorative KPI cards or nonfunctional controls.
- Keep the topology usable from mobile widths through wide desktop displays; on constrained widths, pan/scroll is preferable to overlapping nodes.
- Edge types are distinguished by label and stroke pattern, not color alone.
- All copy is supplied in English and Brazilian Portuguese locale files.

## Accessibility

- Every graph relationship has a readable list representation.
- Nodes are real buttons or links with visible focus, selected state, type, and status in their accessible names.
- Keyboard repositioning is announced through an `aria-live` status message.
- “Organize” is reachable by keyboard and announces completion.
- The flow board uses headings and lists; it must not require drag-and-drop to understand or change state.
- The history uses lane headings and ordered lists.
- Motion honors `prefers-reduced-motion`.

## Empty, loading, and degraded states

- No agents: show the existing empty-state guidance and the database resource only when its source is known.
- Agent without current work or membership: show the agent unconnected, with “No current project”.
- Project without active execution under a project filter: show the project and its allocation relationships, if any.
- No flow items: explain that no operational items exist in the selected window.
- No history events: retain the explicit empty history message.
- Unavailable source: keep verified records visible, mark source health, and do not manufacture missing relationships.

## Verification

- Backend unit and API tests cover avatar serialization, membership/current-work precedence, project/resource nodes, relation keys, flow-stage normalization, project filtering, and history lanes.
- Frontend schema tests reject malformed graph and flow payloads.
- View-model tests cover deterministic layout, coordinate clamping, saved-position reconciliation, and stage/lane ordering.
- Component/page tests cover avatar fallback, project/database nodes, solid/dashed relationship text, pointer and keyboard movement, Organize reset, view switching, and accessible labels.
- Run the focused frontend and backend suites, full frontend test/build, full backend test suite, Ruff, and the premium strict audit.
- Perform a browser smoke test in development mode at the Agent Activity route.

## Out of scope

- Editing task, message, execution, membership, or project state from these views.
- Creating a second pipeline or duplicating canonical records.
- Persisting graph coordinates in PostgreSQL.
- Automatic inference that an agent is working on every project where it has membership.
- Historical analytics, duration charts, or throughput forecasting.
